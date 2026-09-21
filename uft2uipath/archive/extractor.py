# Extracts UFT/ALM archive packages (.qcp or .zip files) into a temporary
# directory, tolerating corrupt zip "extra field" metadata that would
# otherwise make Python's zipfile module refuse to read the archive.
from pathlib import Path
import tempfile
import zipfile


class ArchiveExtractor:
    """Extracts .qcp/.zip exports into a new temporary directory."""
    def extract(self, archive: str | Path) -> Path:
        """Extract the archive and return the directory it was extracted to."""
        archive = Path(archive)

        if not archive.exists():
            raise FileNotFoundError(archive)

        temp_dir = Path(tempfile.mkdtemp(prefix="uft2uipath_"))

        original_decode_extra = zipfile.ZipInfo._decodeExtra

        def safe_decode_extra(self, filename_crc):
            """Accept entries whose zip extra field is corrupt instead of failing the archive."""
            try:
                original_decode_extra(self, filename_crc)
            except zipfile.BadZipFile as exc:
                if "Corrupt extra field" in str(exc):
                    self.extra = b""
                else:
                    raise

        zipfile.ZipInfo._decodeExtra = safe_decode_extra

        try:
            with zipfile.ZipFile(archive, "r") as z:
                z.extractall(temp_dir)
        finally:
            zipfile.ZipInfo._decodeExtra = original_decode_extra

        return temp_dir