import zipfile

from uft2uipath.qcp.extractor import ArchiveExtractor


def test_extract_archive(tmp_path):

    archive = tmp_path / "demo.qcp"

    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("hello.txt", "world")

    folder = ArchiveExtractor().extract(archive)

    assert folder.exists()
    assert (folder / "hello.txt").exists()