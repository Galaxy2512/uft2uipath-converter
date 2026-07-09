from uft2uipath.analyzer.project_analyzer import ProjectAnalyzer


def test_project_analyzer_returns_summary(tmp_path):
    (tmp_path / "A.xml").write_text("<Root><Child/></Root>", encoding="utf-8")
    (tmp_path / "B.txt").write_text("hello", encoding="utf-8")

    analysis = ProjectAnalyzer().analyze(tmp_path)

    assert analysis.total_files == 2
    assert analysis.extensions[".xml"] == 1
    assert analysis.extensions[".txt"] == 1
    assert analysis.xml_roots["Root"] == 1
    assert len(analysis.largest_files) == 2