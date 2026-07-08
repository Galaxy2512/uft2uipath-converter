from __future__ import annotations
import shutil, subprocess, zipfile
from pathlib import Path

class QcpExtractor:
    """Extracts ALM/QC .qcp files.

    Some QCP exports are valid ZIPs but Python's zipfile can fail on ALM-specific metadata.
    We first try zipfile, then fall back to 7-Zip on Windows or unzip on Unix-like systems.
    """
    def extract(self, qcp_path: str | Path, output_dir: str | Path) -> Path:
        qcp_path = Path(qcp_path)
        output_dir = Path(output_dir)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(qcp_path) as zf:
                zf.extractall(output_dir)
            return output_dir
        except Exception as zip_error:
            seven_zip = shutil.which("7z") or shutil.which("7z.exe")
            if seven_zip is None:
                possible = Path(r"C:\Program Files\7-Zip\7z.exe")
                if possible.exists():
                    seven_zip = str(possible)
            if seven_zip:
                subprocess.run([seven_zip, "x", str(qcp_path), f"-o{output_dir}", "-y"], check=True)
                return output_dir

            unzip = shutil.which("unzip")
            if unzip:
                subprocess.run([unzip, "-q", str(qcp_path), "-d", str(output_dir)], check=True)
                return output_dir

            raise RuntimeError(
                "QCP extraction failed with Python zipfile and no fallback extractor was found. "
                "Install 7-Zip and ensure 7z.exe is available in PATH. "
                f"Original error: {zip_error}"
            )
