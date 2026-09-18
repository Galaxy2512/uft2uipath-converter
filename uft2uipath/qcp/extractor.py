# Unpacks a UFT/ALM ".qcp" or ".zip" archive into a fresh temporary directory
# so the rest of the pipeline can read its contents as plain files.

from pathlib import Path
import tempfile
import zipfile


class ArchiveExtractor:
    """
    Extracts a QCP archive into a temporary directory.
    """

    def extract(self, archive: str | Path) -> Path:

        archive = Path(archive)

        if not archive.exists():
            raise FileNotFoundError(archive)
        if archive.suffix.lower() not in [".qcp", ".zip"]:
            raise ValueError(f"Unsupported archive type: {archive.suffix}")

        temp_dir = Path(tempfile.mkdtemp(prefix="uft2uipath_"))

        with zipfile.ZipFile(archive, "r") as z:
            z.extractall(temp_dir)

        return temp_dir
