"""
Inspect raw bytes around a known UFT statement in one ProjRep file.

Purpose
-------
This script helps determine whether two text fragments are:

- part of the same original VBScript statement, or
- separate serialized values joined during extraction.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SOURCE_FILE = (
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

SEARCH_TEXT = (
    'WebEdit("username_WebEdit").Set'
)


def main() -> None:
    """
    Find the target statement and print bytes around it.
    """

    data = SOURCE_FILE.read_bytes()
    search_bytes = SEARCH_TEXT.encode("utf-8")

    offset = data.find(search_bytes)

    if offset < 0:
        print("Search text was not found.")
        return

    # Include bytes before and after the found statement.
    start = max(0, offset - 100)
    end = min(len(data), offset + 300)

    region = data[start:end]

    print(f"Source file: {SOURCE_FILE}")
    print(f"Match offset: {offset}")
    print()

    print("=" * 80)
    print("HEX")
    print("=" * 80)

    for relative_offset in range(0, len(region), 16):
        chunk = region[relative_offset:relative_offset + 16]

        hex_values = " ".join(
            f"{byte:02X}"
            for byte in chunk
        )

        ascii_values = "".join(
            chr(byte) if 32 <= byte <= 126 else "."
            for byte in chunk
        )

        absolute_offset = start + relative_offset

        print(
            f"{absolute_offset:08X}  "
            f"{hex_values:<48} "
            f"{ascii_values}"
        )

    print()
    print("=" * 80)
    print("UTF-8 TEXT")
    print("=" * 80)
    print(region.decode("utf-8", errors="replace"))

    print()
    print("=" * 80)
    print("LATIN-1 TEXT")
    print("=" * 80)
    print(region.decode("latin1", errors="replace"))


if __name__ == "__main__":
    main()