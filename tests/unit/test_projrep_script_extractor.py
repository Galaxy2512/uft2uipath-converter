from uft2uipath.parser.projrep_script_extractor import (
    ProjRepScriptExtractor,
)


def test_extract_utf8_uft_script(tmp_path):
    folder = tmp_path / "ProjRep" / "000" / "000" / "000" / "001"
    folder.mkdir(parents=True)

    source_file = folder / "803"

    source_file.write_bytes(
        b"\x00\x01binary metadata\x00"
        b'Browser("Demo").Page("Login")'
        b'.WebEdit("Username").Set "Admin"\n'
        b'Browser("Demo").Page("Login")'
        b'.WebButton("Submit").Click'
    )

    result = ProjRepScriptExtractor().extract(source_file)

    assert result is not None
    assert result.object_id == 1803
    assert result.encoding == "utf-8"
    assert "Browser(" in result.text
    assert ".Set" in result.text
    assert ".Click" in result.text
    assert "Browser(" in result.signatures


def test_return_none_when_file_contains_no_uft_code(tmp_path):
    source_file = tmp_path / "100"
    source_file.write_bytes(b"ordinary binary metadata")

    result = ProjRepScriptExtractor().extract(source_file)

    assert result is None