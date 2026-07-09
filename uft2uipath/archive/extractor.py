from pathlib import Path
import tempfile
import zipfile


class ArchiveExtractor:
    def extract(self, archive: str | Path) -> Path:
        archive = Path(archive)

        if not archive.exists():
            raise FileNotFoundError(archive)

        temp_dir = Path(tempfile.mkdtemp(prefix="uft2uipath_"))

        original_decode_extra = zipfile.ZipInfo._decodeExtra

        def safe_decode_extra(self, filename_crc):
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