from uft2uipath.parser.step_entity_parser import StepEntityParser


def test_parse_component_step():
    row = {
        "CS_STEP_ID": "100",
        "CS_STEP_ORDER": "3",
        "CS_STEP_NAME": "Navigate",
        "CS_DESCRIPTION": "Navigate to website",
        "CS_EXPECTED": "Website opened",
    }

    step = StepEntityParser().parse(row)

    assert step.id == 100
    assert step.order == 3
    assert step.name == "Navigate"
    assert step.description == "Navigate to website"
    assert step.expected_result == "Website opened"