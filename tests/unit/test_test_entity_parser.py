from uft2uipath.parser.test_entity_parser import TestEntityParser


def test_parse_test_entity_row():
    row = {
        "TS_TEST_ID": "102",
        "TS_NAME": "Fully_BPT_TestCase",
        "TS_STATUS": "Maintenance",
        "TS_TYPE": "BUSINESS-PROCESS",
        "TS_EXEC_STATUS": "Passed",
        "TS_DESCRIPTION": "Demo BPT test",
    }

    test_case = TestEntityParser().parse(row)

    assert test_case.id == 102
    assert test_case.name == "Fully_BPT_TestCase"
    assert test_case.alm_status == "Maintenance"
    assert test_case.test_type == "BUSINESS-PROCESS"
    assert test_case.execution_status == "Passed"
    assert test_case.raw == row