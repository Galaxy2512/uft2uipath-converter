from uft2uipath.parser.alm_reader import AlmReader


def test_reader_returns_dictionary(tmp_path):
    (tmp_path / "Test.xml").write_text("<test/>")

    result = AlmReader().read(tmp_path)

    assert "tests" in result
    assert len(result["tests"]) == 1