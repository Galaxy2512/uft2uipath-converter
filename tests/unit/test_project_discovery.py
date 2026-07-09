from uft2uipath.discovery.project_discovery import ProjectDiscovery


def test_discovery_finds_and_categorizes_files(tmp_path):
    (tmp_path / "Tests").mkdir()
    (tmp_path / "Components").mkdir()
    (tmp_path / "Data").mkdir()

    (tmp_path / "Tests" / "Test.xml").write_text("<test/>")
    (tmp_path / "Components" / "Component.xml").write_text("<component/>")
    (tmp_path / "Data" / "Input.xlsx").write_text("fake excel")

    result = ProjectDiscovery().discover(tmp_path)

    assert result.total_files == 3
    assert len(result.by_category("xml")) == 2
    assert len(result.by_category("data_table")) == 1