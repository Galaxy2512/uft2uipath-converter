from uft2uipath.parser.project_inspector import ProjectInspector


def test_project_inspector(tmp_path):

    (tmp_path / "Folder").mkdir()

    (tmp_path / "Folder" / "Test.xml").write_text("abc")

    inspector = ProjectInspector()

    info = inspector.inspect(tmp_path)

    assert info["project_name"] == tmp_path.name
    assert info["directories"] == 1
    assert info["files"] == 1