from uft2uipath.discovery.discovery_report import DiscoveryReportBuilder


def test_discovery_report_builds_summary(tmp_path):
    (tmp_path / "Tests").mkdir()
    (tmp_path / "Data").mkdir()

    (tmp_path / "Tests" / "Test.xml").write_text(
        '<Test name="Demo"><Step/></Test>',
        encoding="utf-8",
    )
    (tmp_path / "Data" / "Input.csv").write_text("a,b,c", encoding="utf-8")

    report = DiscoveryReportBuilder().build(tmp_path)

    assert report.total_files == 2
    assert report.categories["xml"] == 1
    assert report.categories["data_table"] == 1
    assert len(report.xml_files) == 1
    assert report.xml_files[0].root_tag == "Test"
