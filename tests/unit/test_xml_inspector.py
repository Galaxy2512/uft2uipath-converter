from uft2uipath.discovery.xml_inspector import XmlInspector


def test_xml_inspector_reads_root_and_count(tmp_path):
    xml_file = tmp_path / "Test.xml"
    xml_file.write_text(
        '<Test name="Demo"><Step/><Step/></Test>',
        encoding="utf-8",
    )

    result = XmlInspector().inspect(xml_file)

    assert result.root_tag == "Test"
    assert result.attributes["name"] == "Demo"
    assert result.element_count == 3