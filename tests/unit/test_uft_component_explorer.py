from uft2uipath.analyzer.uft.component_explorer import UftComponentExplorer


def test_component_explorer_classifies_uft_files(tmp_path):
    action_folder = tmp_path / "Action0"
    repository_folder = tmp_path / "ObjectRepository"

    action_folder.mkdir()
    repository_folder.mkdir()

    (action_folder / "Script.mts").write_text(
        'Browser("Demo").Navigate "https://example.com"',
        encoding="utf-8",
    )

    (action_folder / "Resource.mtr").write_text(
        "resource data",
        encoding="utf-8",
    )

    (repository_folder / "Local.tsr").write_bytes(b"repository")
    (tmp_path / "Default.cfg").write_text("config", encoding="utf-8")
    (tmp_path / "Data.xlsx").write_bytes(b"excel")

    result = UftComponentExplorer().inspect(tmp_path)

    assert result.total_files == 5
    assert len(result.by_category("script")) == 1
    assert len(result.by_category("action_resource")) == 1
    assert len(result.by_category("object_repository")) == 1
    assert len(result.by_category("configuration")) == 1
    assert len(result.by_category("data_table")) == 1