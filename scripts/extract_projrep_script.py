from __future__ import annotations

import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCE = (
    PROJECT_ROOT
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

DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "output"
    / "projrep_803_extracted.vbs"
)


def read_script(source: Path) -> str:
    """
    Čita UFT/VBScript sadržaj iz ProjRep datoteke.

    utf-8-sig:
    - čita UTF-8
    - automatski uklanja BOM ako postoji
    """
    raw = source.read_bytes()

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    return normalize_line_endings(text)


def normalize_line_endings(text: str) -> str:
    """
    Interno normalizira sve završetke redaka na LF.
    """
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def validate_script(text: str) -> list[str]:
    """
    Vraća dijagnostičke poruke o pronađenom sadržaju.

    Ovo još nije potpuna validacija VBScript/UFT sintakse.
    """
    messages: list[str] = []

    if not text.strip():
        messages.append("Skripta je prazna.")
        return messages

    known_markers = (
        "Option Explicit",
        "Browser(",
        "Reporter.ReportEvent",
        "Parameter(",
        "ExitTest",
    )

    found_markers = [
        marker
        for marker in known_markers
        if marker.casefold() in text.casefold()
    ]

    if found_markers:
        messages.append(
            "Pronađeni UFT/VBScript markeri: "
            + ", ".join(found_markers)
        )
    else:
        messages.append(
            "Upozorenje: nisu pronađeni poznati UFT/VBScript markeri."
        )

    return messages


def write_script(destination: Path, text: str) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # newline="" sprječava Python da dodatno mijenja završetke redaka.
    with destination.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        file.write(text)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Izvlači čisti UFT/VBScript sadržaj "
            "iz ProjRep datoteke."
        )
    )

    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Izvorna ProjRep datoteka.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Odredišna .vbs datoteka.",
    )

    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()

    if not source.exists():
        raise FileNotFoundError(
            f"Izvorna datoteka ne postoji: {source}"
        )

    if not source.is_file():
        raise ValueError(
            f"Izvorna putanja nije datoteka: {source}"
        )

    script = read_script(source)
    diagnostics = validate_script(script)

    write_script(
        destination=output,
        text=script,
    )

    print(f"Source: {source}")
    print(f"Output: {output}")
    print(f"Characters extracted: {len(script)}")
    print(f"Lines extracted: {len(script.splitlines())}")

    for diagnostic in diagnostics:
        print(f"- {diagnostic}")


if __name__ == "__main__":
    main()