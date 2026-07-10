
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "extracted"
    / "Migration_BPT"
    / "ProjRep"
    / "000"
    / "000"
    / "000"
    / "001"
    / "803"
)


@dataclass(frozen=True)
class TextRegion:
    start: int
    end: int
    data: bytes

    @property
    def length(self) -> int:
        return self.end - self.start


def is_text_byte(value: int) -> bool:
    """
    Prihvaća:
    - tab
    - CR/LF
    - standardne ASCII znakove
    - proširene Latin-1 znakove
    """
    return (
        value in (9, 10, 13)
        or 32 <= value <= 126
        or 160 <= value <= 255
    )


def find_text_regions(data: bytes, minimum_length: int) -> list[TextRegion]:
    regions: list[TextRegion] = []
    start: int | None = None

    for index, value in enumerate(data):
        if is_text_byte(value):
            if start is None:
                start = index
        else:
            if start is not None:
                if index - start >= minimum_length:
                    regions.append(
                        TextRegion(
                            start=start,
                            end=index,
                            data=data[start:index],
                        )
                    )
                start = None

    if start is not None and len(data) - start >= minimum_length:
        regions.append(
            TextRegion(
                start=start,
                end=len(data),
                data=data[start:],
            )
        )

    return regions


def decode_region(region: TextRegion) -> str:
    try:
        return region.data.decode("utf-8")
    except UnicodeDecodeError:
        return region.data.decode("latin-1", errors="replace")


def normalize_control_characters(text: str) -> str:
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\t", "    ")
    )


def print_region(index: int, region: TextRegion) -> None:
    decoded = decode_region(region)
    normalized = normalize_control_characters(decoded)

    print("=" * 100)
    print(
        f"REGION {index} | "
        f"START: {region.start} (0x{region.start:08X}) | "
        f"END: {region.end} (0x{region.end:08X}) | "
        f"LENGTH: {region.length}"
    )
    print("=" * 100)
    print(normalized)
    print()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    parser = argparse.ArgumentParser(
        description=(
            "Ispisuje čitljive tekstualne regije "
            "iz ProjRep binarne datoteke."
        )
    )

    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Putanja do ProjRep datoteke.",
    )

    parser.add_argument(
        "--min-length",
        type=int,
        default=20,
        help="Minimalna duljina tekstualne regije u bajtovima.",
    )

    parser.add_argument(
        "--contains",
        type=str,
        default=None,
        help="Prikaži samo regije koje sadrže navedeni tekst.",
    )

    args = parser.parse_args()

    source: Path = args.source.resolve()

    if not source.exists():
        raise FileNotFoundError(
            f"Datoteka ne postoji: {source}"
        )

    if not source.is_file():
        raise ValueError(
            f"Putanja nije datoteka: {source}"
        )

    if args.min_length < 1:
        raise ValueError(
            "--min-length mora biti veći od 0."
        )

    data = source.read_bytes()
    regions = find_text_regions(
        data=data,
        minimum_length=args.min_length,
    )

    print(f"Source file: {source}")
    print(f"File size: {len(data)} bytes")
    print(f"Text regions found: {len(regions)}")
    print()

    displayed = 0

    for index, region in enumerate(regions, start=1):
        decoded = decode_region(region)

        if (
            args.contains
            and args.contains.casefold() not in decoded.casefold()
        ):
            continue

        print_region(index, region)
        displayed += 1

    if displayed == 0:
        print(
            "Nije pronađena nijedna odgovarajuća "
            "tekstualna regija."
        )


if __name__ == "__main__":
    main()
