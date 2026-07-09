from uft2uipath.ast import ConversionStatus
from uft2uipath.parser.test_parser import TestParser


def test_parse_test_with_components():
    raw = {
        "name": "Simple Browser Test",
        "description": "BPT test with browser components",
        "parameters": [
            {
                "name": "Browser",
                "value": "Edge",
                "datatype": "String",
                "direction": "In",
            }
        ],
        "components": [
            {
                "name": "Browser_Start_QWERTZ",
                "steps": [
                    {
                        "name": "Open browser",
                        "action": "Click",
                        "target": "EdgeIcon",
                    }
                ],
            },
            {
                "name": "Browser_Close_QWERTZ",
                "steps": [
                    {
                        "name": "Close browser",
                        "action": "Click",
                        "target": "CloseButton",
                    }
                ],
            },
        ],
    }

    test_case = TestParser().parse(raw)

    assert test_case.name == "Simple Browser Test"
    assert len(test_case.parameters) == 1
    assert len(test_case.components) == 2
    assert test_case.components[0].name == "Browser_Start_QWERTZ"


def test_test_collects_component_issues():
    raw = {
        "name": "Test With Unsupported Step",
        "components": [
            {
                "name": "CustomComponent",
                "steps": [
                    {
                        "name": "Unsupported",
                        "action": "UnknownAction",
                    }
                ],
            }
        ],
    }

    test_case = TestParser().parse(raw)

    assert test_case.components[0].steps[0].status == ConversionStatus.UNSUPPORTED
    assert len(test_case.issues) == 1