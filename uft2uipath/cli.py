from __future__ import annotations
import argparse, tempfile, zipfile
from pathlib import Path
from uft2uipath.qcp.extractor import QcpExtractor
from uft2uipath.qcp.reader import QcpModelReader
from uft2uipath.uipath.project import UiPathProjectWriter

def main() -> None:
    p = argparse.ArgumentParser(description="Convert ALM/UFT BPT QCP exports to UiPath Test Project scaffolds")
    p.add_argument("qcp", help="Path to .qcp file")
    p.add_argument("--out", default="Migration_BPT_UiPath_TestProject", help="Output project folder")
    p.add_argument("--zip", action="store_true", help="Also create .zip next to output folder")
    args = p.parse_args()
    qcp = Path(args.qcp)
    with tempfile.TemporaryDirectory() as td:
        extracted = QcpExtractor().extract(qcp, Path(td)/"qcp")
        model = QcpModelReader().read(extracted, qcp)
        out = UiPathProjectWriter().write(model, args.out)
    if args.zip:
        zip_path = out.with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in out.rglob("*"):
                if f.is_file(): zf.write(f, f.relative_to(out.parent))
        print(f"Created {zip_path}")
    print(f"Created {out}")

if __name__ == "__main__":
    main()
