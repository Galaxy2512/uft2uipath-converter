
"""
Analyze the extracted ProjRep folder and create a human-readable report.

This script is used only for investigation and reverse engineering.
It is not part of the production converter pipeline.
"""

from pathlib import Path
import sys


# --------------------------------------------------------
# Add project root to Python path.
#
# The script is located in:
#     scripts/analyze_projrep.py
#
# The project package is located in:
#     uft2uipath/
#
# Adding the project root allows Python to import the
# uft2uipath package when this file is executed directly.
# --------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# IMPORTANT:
# This import must come after the project root is added
# to sys.path.
from uft2uipath.analyzer.uft.projrep_analyzer import ProjRepAnalyzer


# --------------------------------------------------------
# Paths
# --------------------------------------------------------

PROJREP_FOLDER = (
    PROJECT_ROOT
    / "samples"
    / "extracted"
    / "Migration_BPT"
    / "ProjRep"
)

OUTPUT_FILE = PROJECT_ROOT / "projrep_analysis.txt"


# --------------------------------------------------------
# Known ALM/UFT Business Components
#
# These names are used as evidence when searching ProjRep
# objects. Finding a component name inside a ProjRep file
# may help us establish the COMPONENT -> ProjRep mapping.
# --------------------------------------------------------

COMPONENTS = [
    "BrowserStart_QWERTZ",
    "BrowserClose_QWERTZ",
    "BrowserNavigate_QWERTZ",
    "CheckWebsite_QWERTZ",
    "LoginWebsite_QWERTZ",
    "ReadExcelAddressData_QWERTZ",
    "AdminWebsiteSelectUserRole_QWERTZ",
    "AdminWebsiteCheckUserRole_QWERTZ",
]


def main() -> None:
    """
    Analyze the ProjRep directory and create a text report.
    """

    # ----------------------------------------------------
    # STEP 1
    # Validate that the extracted ProjRep directory exists.
    # ----------------------------------------------------

    if not PROJREP_FOLDER.exists():
        raise FileNotFoundError(
            f"ProjRep folder was not found: {PROJREP_FOLDER}"
        )

    # ----------------------------------------------------
    # STEP 2
    # Analyze all ProjRep files for UFT signatures and
    # known Business Component names.
    # ----------------------------------------------------

    results = ProjRepAnalyzer().analyze(
        PROJREP_FOLDER,
        COMPONENTS,
    )

    # ----------------------------------------------------
    # STEP 3
    # Build a human-readable investigation report.
    # ----------------------------------------------------

    report: list[str] = []

    report.append("=" * 80)
    report.append("PROJREP ANALYSIS")
    report.append("=" * 80)
    report.append("")
    report.append(f"ProjRep folder: {PROJREP_FOLDER}")
    report.append(f"Relevant files: {len(results)}")
    report.append("")

    for item in results:
        report.append("=" * 80)
        report.append(f"FILE: {item.relative_path}")
        report.append(f"OBJECT ID: {item.object_id}")
        report.append(f"COMPONENTS: {item.component_names}")
        report.append(f"SIGNATURES: {item.signatures}")
        report.append("")
        report.append("PREVIEW")
        report.append("-" * 80)
        report.append(item.text_preview or "")
        report.append("")

    # ----------------------------------------------------
    # STEP 4
    # Save the report in the project root.
    # ----------------------------------------------------

    OUTPUT_FILE.write_text(
        "\n".join(report),
        encoding="utf-8",
    )

    print(f"Relevant files found: {len(results)}")
    print(f"Report written to: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
