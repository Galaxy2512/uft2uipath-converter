from uft2uipath.ast import ConversionStatus
from uft2uipath.report.conversion_report import ConversionReport


def test_conversion_report_success_rate():
    report = ConversionReport(project_name="Migration_BPT", total_tests=10)

    report.add_status(ConversionStatus.SUCCESS)
    report.add_status(ConversionStatus.PARTIAL)
    report.add_status(ConversionStatus.FAILED)

    assert report.success == 1
    assert report.partial == 1
    assert report.failed == 1
    assert report.converted == 2
    assert report.success_rate == 20.0