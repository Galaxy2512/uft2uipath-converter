"""
Extract and parse one real ProjRep UFT script.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from uft2uipath.parser.projrep_script_extractor import (
    ProjRepScriptExtractor,
)
from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser


def main() -> None:
    """
    Parse the ProjRep object previously identified as 1803.
    """

    source_file = (
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

    extracted = ProjRepScriptExtractor().extract(source_file)

    if extracted is None:
        print("No UFT script found.")
        return

    parsed = UftVbScriptParser().parse(extracted.text)

    print(f"Object ID: {extracted.object_id}")
    print(f"Encoding: {extracted.encoding}")
    print(f"Operations: {len(parsed.operations)}")
    print()

    for operation in parsed.operations:
        print(type(operation).__name__)
        print(operation)
        print("-" * 80)


if __name__ == "__main__":
    main()