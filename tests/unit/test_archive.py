# Unit tests for ArchiveExtractor (uft2uipath/qcp/extractor.py): covers
# extracting a .qcp archive (a zip file) into a folder and verifying its
# contained files are unpacked to disk.
import zipfile

from uft2uipath.qcp.extractor import ArchiveExtractor


def test_extract_archive(tmp_path):

    archive = tmp_path / "demo.qcp"

    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("hello.txt", "world")

    folder = ArchiveExtractor().extract(archive)

    assert folder.exists()
    assert (folder / "hello.txt").exists()