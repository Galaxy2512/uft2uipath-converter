from uft2uipath.alm.ptd_reader import PtdReader


def test_ptd_reader_extracts_printable_strings(tmp_path):
    ptd = tmp_path / "TEST_!000001.ptd"

    # Binary-like content:
    # - null bytes
    # - printable text
    # - binary separators
    ptd.write_bytes(
        b"\x00\x01Simply_BPT_TestCase\x00\x00BUSINESS-PROCESS\x01Passed"
    )

    values = PtdReader().read_strings(ptd)

    assert "Simply_BPT_TestCase" in values
    assert "BUSINESS-PROCESS" in values
    assert "Passed" in values