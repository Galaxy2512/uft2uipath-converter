from uft2uipath.analyzer.db_xmlmap_explorer import DbXmlMapExplorer


def test_db_xmlmap_explorer_analyzes_tags_and_attributes(tmp_path):
    xml = tmp_path / "db_xmlmap.xml"
    xml.write_text(
        '<Scheme><Table Name="TEST"><Column Name="TS_NAME"/></Table></Scheme>',
        encoding="utf-8",
    )

    result = DbXmlMapExplorer().analyze(xml)

    assert result.root_tag == "Scheme"
    assert result.total_elements == 3
    assert result.tags["Table"] == 1
    assert result.tags["Column"] == 1
    assert result.attributes["Name"] == 2