
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCE_ROOT = (
    PROJECT_ROOT
    / "samples"
    / "extracted"
    / "Migration_BPT"
)

DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "output"
    / "project_scan"
)


UFT_MARKERS: dict[str, tuple[str, ...]] = {
    "uft_script": (
        "Option Explicit",
        "Reporter.ReportEvent",
        "ExitTest",
        "Browser(",
        "Desktop.",
        "Window(",
        "Dialog(",
        "SwfWindow(",
        "JavaWindow(",
        "WpfWindow(",
    ),
    "object_repository_reference": (
        "WebEdit(",
        "WebButton(",
        "WebElement(",
        "WebList(",
        "WebCheckBox(",
        "WebRadioGroup(",
        "Page(",
        "Browser(",
    ),
    "parameter_reference": (
        "Parameter(",
        "DataTable(",
        "Environment(",
    ),
    "control_flow": (
        "If ",
        "Then",
        "Else",
        "End If",
        "For ",
        "Next",
        "Do ",
        "Loop",
        "While ",
        "Wend",
        "Select Case",
        "End Select",
    ),
    "function_or_sub": (
        "Function ",
        "End Function",
        "Sub ",
        "End Sub",
    ),
}


TEXT_EXTENSIONS = {
    ".txt",
    ".xml",
    ".json",
    ".ini",
    ".cfg",
    ".config",
    ".vbs",
    ".qfl",
    ".tsr",
    ".csv",
    ".html",
    ".htm",
    ".js",
    ".css",
    ".properties",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class FileRecord:
    relative_path: str
    absolute_path: str
    parent_directory: str
    name: str
    suffix: str
    size_bytes: int
    sha256: str

    is_text: bool
    detected_encoding: str | None
    printable_ratio: float | None
    line_count: int | None

    categories: list[str]
    matched_markers: dict[str, list[str]]

    text_preview: str | None
    error: str | None


@dataclass(frozen=True)
class DirectoryRecord:
    relative_path: str
    file_count: int
    total_size_bytes: int


@dataclass(frozen=True)
class ProjectSummary:
    source_root: str
    scan_timestamp_utc: str

    directory_count: int
    file_count: int
    total_size_bytes: int

    text_file_count: int
    binary_file_count: int
    error_count: int

    uft_script_candidate_count: int
    object_repository_reference_count: int
    parameter_reference_count: int
    control_flow_count: int
    function_or_sub_count: int

    top_level_directories: list[str]


def configure_console() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace",
        )


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def calculate_printable_ratio(text: str) -> float:
    if not text:
        return 1.0

    printable_count = sum(
        1
        for character in text
        if character.isprintable()
        or character in "\r\n\t"
    )

    return printable_count / len(text)


def normalize_line_endings(text: str) -> str:
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def decode_file(data: bytes) -> tuple[str, str] | None:
    """
    Pokušava prepoznati tekstualne ProjRep i druge projektne datoteke.

    utf-8-sig uklanja UTF-8 BOM.
    utf-16 pokušaji su važni za Windows/UFT datoteke.
    latin-1 je fallback jer može dekodirati svaki bajt,
    ali rezultat prihvaćamo samo ako je dovoljno čitljiv.
    """
    candidates = (
        "utf-8-sig",
        "utf-8",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "cp1250",
        "cp1252",
        "latin-1",
    )

    best_result: tuple[str, str, float] | None = None

    for encoding in candidates:
        try:
            decoded = data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue

        normalized = normalize_line_endings(decoded)
        ratio = calculate_printable_ratio(normalized)

        if best_result is None or ratio > best_result[2]:
            best_result = (
                normalized,
                encoding,
                ratio,
            )

        if ratio >= 0.98:
            break

    if best_result is None:
        return None

    text, encoding, printable_ratio = best_result

    if printable_ratio < 0.85:
        return None

    return text, encoding


def find_markers(text: str) -> dict[str, list[str]]:
    folded_text = text.casefold()
    result: dict[str, list[str]] = {}

    for category, markers in UFT_MARKERS.items():
        matched = [
            marker
            for marker in markers
            if marker.casefold() in folded_text
        ]

        if matched:
            result[category] = matched

    return result


def classify_file(
    path: Path,
    text: str | None,
    matched_markers: dict[str, list[str]],
) -> list[str]:
    categories: list[str] = []

    if text is None:
        categories.append("binary")
        return categories

    categories.append("text")

    suffix = path.suffix.casefold()

    if suffix in TEXT_EXTENSIONS:
        categories.append("known_text_extension")

    if "uft_script" in matched_markers:
        categories.append("uft_script_candidate")

    if "object_repository_reference" in matched_markers:
        categories.append("contains_object_references")

    if "parameter_reference" in matched_markers:
        categories.append("contains_parameter_references")

    if "control_flow" in matched_markers:
        categories.append("contains_control_flow")

    if "function_or_sub" in matched_markers:
        categories.append("contains_function_or_sub")

    if "<" in text and ">" in text:
        stripped = text.lstrip()

        if stripped.startswith("<?xml") or stripped.startswith("<"):
            categories.append("xml_candidate")

    return categories


def build_preview(
    text: str,
    maximum_length: int = 500,
) -> str:
    compact = text.strip()

    if len(compact) <= maximum_length:
        return compact

    return compact[:maximum_length] + "\n...[truncated]"


def scan_file(
    source_root: Path,
    path: Path,
) -> FileRecord:
    relative_path = path.relative_to(source_root)

    try:
        data = path.read_bytes()
        decoded = decode_file(data)

        text: str | None = None
        encoding: str | None = None
        printable_ratio: float | None = None
        line_count: int | None = None
        preview: str | None = None
        matched_markers: dict[str, list[str]] = {}

        if decoded is not None:
            text, encoding = decoded
            printable_ratio = calculate_printable_ratio(text)
            line_count = len(text.splitlines())
            preview = build_preview(text)
            matched_markers = find_markers(text)

        categories = classify_file(
            path=path,
            text=text,
            matched_markers=matched_markers,
        )

        return FileRecord(
            relative_path=relative_path.as_posix(),
            absolute_path=str(path.resolve()),
            parent_directory=relative_path.parent.as_posix(),
            name=path.name,
            suffix=path.suffix,
            size_bytes=len(data),
            sha256=calculate_sha256(path),
            is_text=text is not None,
            detected_encoding=encoding,
            printable_ratio=printable_ratio,
            line_count=line_count,
            categories=categories,
            matched_markers=matched_markers,
            text_preview=preview,
            error=None,
        )

    except Exception as exception:
        return FileRecord(
            relative_path=relative_path.as_posix(),
            absolute_path=str(path.resolve()),
            parent_directory=relative_path.parent.as_posix(),
            name=path.name,
            suffix=path.suffix,
            size_bytes=path.stat().st_size if path.exists() else 0,
            sha256="",
            is_text=False,
            detected_encoding=None,
            printable_ratio=None,
            line_count=None,
            categories=["error"],
            matched_markers={},
            text_preview=None,
            error=f"{type(exception).__name__}: {exception}",
        )


def build_directory_records(
    source_root: Path,
    files: list[FileRecord],
) -> list[DirectoryRecord]:
    statistics: dict[str, dict[str, int]] = {}

    for directory in source_root.rglob("*"):
        if directory.is_dir():
            relative = directory.relative_to(source_root).as_posix()
            statistics[relative] = {
                "file_count": 0,
                "total_size_bytes": 0,
            }

    statistics.setdefault(
        ".",
        {
            "file_count": 0,
            "total_size_bytes": 0,
        },
    )

    for file_record in files:
        file_path = Path(file_record.relative_path)
        parent = file_path.parent

        while True:
            relative_parent = parent.as_posix()

            if relative_parent == "":
                relative_parent = "."

            statistics.setdefault(
                relative_parent,
                {
                    "file_count": 0,
                    "total_size_bytes": 0,
                },
            )

            statistics[relative_parent]["file_count"] += 1
            statistics[relative_parent]["total_size_bytes"] += (
                file_record.size_bytes
            )

            if parent == Path("."):
                break

            parent = parent.parent

    return [
        DirectoryRecord(
            relative_path=relative_path,
            file_count=values["file_count"],
            total_size_bytes=values["total_size_bytes"],
        )
        for relative_path, values in sorted(statistics.items())
    ]


def count_category(
    files: list[FileRecord],
    category: str,
) -> int:
    return sum(
        1
        for file_record in files
        if category in file_record.categories
    )


def build_summary(
    source_root: Path,
    files: list[FileRecord],
    directories: list[DirectoryRecord],
) -> ProjectSummary:
    top_level_directories = sorted(
        path.name
        for path in source_root.iterdir()
        if path.is_dir()
    )

    return ProjectSummary(
        source_root=str(source_root.resolve()),
        scan_timestamp_utc=datetime.now(timezone.utc).isoformat(),
        directory_count=len(directories),
        file_count=len(files),
        total_size_bytes=sum(
            file_record.size_bytes
            for file_record in files
        ),
        text_file_count=sum(
            1
            for file_record in files
            if file_record.is_text
        ),
        binary_file_count=sum(
            1
            for file_record in files
            if not file_record.is_text
            and file_record.error is None
        ),
        error_count=sum(
            1
            for file_record in files
            if file_record.error is not None
        ),
        uft_script_candidate_count=count_category(
            files,
            "uft_script_candidate",
        ),
        object_repository_reference_count=count_category(
            files,
            "contains_object_references",
        ),
        parameter_reference_count=count_category(
            files,
            "contains_parameter_references",
        ),
        control_flow_count=count_category(
            files,
            "contains_control_flow",
        ),
        function_or_sub_count=count_category(
            files,
            "contains_function_or_sub",
        ),
        top_level_directories=top_level_directories,
    )


def write_json(
    destination: Path,
    payload: Any,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def write_files_csv(
    destination: Path,
    files: list[FileRecord],
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with destination.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        writer = csv.writer(csv_file)

        writer.writerow(
            [
                "relative_path",
                "parent_directory",
                "name",
                "suffix",
                "size_bytes",
                "sha256",
                "is_text",
                "detected_encoding",
                "printable_ratio",
                "line_count",
                "categories",
                "uft_markers",
                "object_reference_markers",
                "parameter_markers",
                "control_flow_markers",
                "function_or_sub_markers",
                "error",
            ]
        )

        for file_record in files:
            writer.writerow(
                [
                    file_record.relative_path,
                    file_record.parent_directory,
                    file_record.name,
                    file_record.suffix,
                    file_record.size_bytes,
                    file_record.sha256,
                    file_record.is_text,
                    file_record.detected_encoding or "",
                    (
                        f"{file_record.printable_ratio:.4f}"
                        if file_record.printable_ratio is not None
                        else ""
                    ),
                    file_record.line_count or "",
                    "; ".join(file_record.categories),
                    "; ".join(
                        file_record.matched_markers.get(
                            "uft_script",
                            [],
                        )
                    ),
                    "; ".join(
                        file_record.matched_markers.get(
                            "object_repository_reference",
                            [],
                        )
                    ),
                    "; ".join(
                        file_record.matched_markers.get(
                            "parameter_reference",
                            [],
                        )
                    ),
                    "; ".join(
                        file_record.matched_markers.get(
                            "control_flow",
                            [],
                        )
                    ),
                    "; ".join(
                        file_record.matched_markers.get(
                            "function_or_sub",
                            [],
                        )
                    ),
                    file_record.error or "",
                ]
            )


def write_script_candidates(
    output_directory: Path,
    files: list[FileRecord],
) -> None:
    candidates = [
        file_record
        for file_record in files
        if "uft_script_candidate" in file_record.categories
    ]

    write_json(
        output_directory / "uft_script_candidates.json",
        [
            asdict(candidate)
            for candidate in candidates
        ],
    )

    paths = "\n".join(
        candidate.relative_path
        for candidate in candidates
    )

    if paths:
        paths += "\n"

    (
        output_directory
        / "uft_script_candidate_paths.txt"
    ).write_text(
        paths,
        encoding="utf-8",
    )


def print_summary(summary: ProjectSummary) -> None:
    print("=" * 80)
    print("QCP PROJECT SCAN")
    print("=" * 80)
    print(f"Source: {summary.source_root}")
    print(f"Directories: {summary.directory_count}")
    print(f"Files: {summary.file_count}")
    print(f"Total size: {summary.total_size_bytes} bytes")
    print(f"Text files: {summary.text_file_count}")
    print(f"Binary files: {summary.binary_file_count}")
    print(f"Errors: {summary.error_count}")
    print()
    print(
        "UFT script candidates: "
        f"{summary.uft_script_candidate_count}"
    )
    print(
        "Files with object references: "
        f"{summary.object_repository_reference_count}"
    )
    print(
        "Files with parameter references: "
        f"{summary.parameter_reference_count}"
    )
    print(
        "Files with control flow: "
        f"{summary.control_flow_count}"
    )
    print(
        "Files with functions/subs: "
        f"{summary.function_or_sub_count}"
    )
    print()
    print(
        "Top-level directories: "
        + ", ".join(summary.top_level_directories)
    )
    print("=" * 80)


def main() -> None:
    configure_console()

    parser = argparse.ArgumentParser(
        description=(
            "Skenira extracted QCP projekt i izrađuje "
            "neutralni inventar za Semantic razinu."
        )
    )

    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
        help="Korijenski direktorij extracted QCP projekta.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Direktorij za rezultate skeniranja.",
    )

    args = parser.parse_args()

    source_root = args.source.resolve()
    output_directory = args.output.resolve()

    if not source_root.exists():
        raise FileNotFoundError(
            f"Projektni direktorij ne postoji: {source_root}"
        )

    if not source_root.is_dir():
        raise ValueError(
            f"Izvorna putanja nije direktorij: {source_root}"
        )

    paths = sorted(
        path
        for path in source_root.rglob("*")
        if path.is_file()
    )

    files: list[FileRecord] = []

    for index, path in enumerate(paths, start=1):
        relative_path = path.relative_to(source_root)

        print(
            f"[{index}/{len(paths)}] "
            f"{relative_path.as_posix()}"
        )

        files.append(
            scan_file(
                source_root=source_root,
                path=path,
            )
        )

    directories = build_directory_records(
        source_root=source_root,
        files=files,
    )

    summary = build_summary(
        source_root=source_root,
        files=files,
        directories=directories,
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    complete_manifest = {
        "summary": asdict(summary),
        "directories": [
            asdict(directory)
            for directory in directories
        ],
        "files": [
            asdict(file_record)
            for file_record in files
        ],
    }

    write_json(
        output_directory / "project_manifest.json",
        complete_manifest,
    )

    write_json(
        output_directory / "project_summary.json",
        asdict(summary),
    )

    write_json(
        output_directory / "directories.json",
        [
            asdict(directory)
            for directory in directories
        ],
    )

    write_files_csv(
        output_directory / "files.csv",
        files,
    )

    write_script_candidates(
        output_directory=output_directory,
        files=files,
    )

    print()
    print_summary(summary)
    print()
    print(f"Output: {output_directory}")
    print(
        "Manifest: "
        f"{output_directory / 'project_manifest.json'}"
    )
    print(
        "CSV inventory: "
        f"{output_directory / 'files.csv'}"
    )
    print(
        "Script candidates: "
        f"{output_directory / 'uft_script_candidates.json'}"
    )


if __name__ == "__main__":
    main()
