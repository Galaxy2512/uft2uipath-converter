from uft2uipath.analyzer.uft.script_locator import UftScriptLocator


def test_script_locator_finds_utf8_uft_code(tmp_path):
    script_file = tmp_path / "component.dat"

    script_file.write_bytes(
        b'\x00\x01Browser("Demo").Page("Login").WebButton("Submit").Click'
    )

    matches = UftScriptLocator().search(tmp_path)

    signatures = {match.signature for match in matches}

    assert "Browser(" in signatures
    assert "Page(" in signatures
    assert "WebButton(" in signatures
    assert ".Click" in signatures