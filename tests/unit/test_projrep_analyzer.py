from uft2uipath.analyzer.uft.projrep_analyzer import ProjRepAnalyzer


def test_projrep_analyzer_finds_script_and_component_name(tmp_path):
    projrep = tmp_path / "ProjRep" / "000" / "000" / "000" / "001"
    projrep.mkdir(parents=True)

    source = (
        'BrowserStart_QWERTZ\n'
        'Browser("Demo").Page("Login").WebButton("Submit").Click'
    )

    (projrep / "803").write_text(source, encoding="utf-8")

    results = ProjRepAnalyzer().analyze(
        tmp_path / "ProjRep",
        component_names=["BrowserStart_QWERTZ"],
    )

    assert len(results) == 1

    evidence = results[0]

    assert evidence.object_id == 1803
    assert "Browser(" in evidence.signatures
    assert ".Click" in evidence.signatures
    assert evidence.component_names == ["BrowserStart_QWERTZ"]
    assert "BrowserStart_QWERTZ" in evidence.text_preview