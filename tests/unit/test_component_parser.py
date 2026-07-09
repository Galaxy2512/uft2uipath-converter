from uft2uipath.ast import ConversionStatus
from uft2uipath.parser.component_parser import ComponentParser


def test_parse_component_with_steps_and_parameters():
    raw = {
        "name": "Browser_Start_QWERTZ",
        "description": "Starts browser",
        "parameters": [
            {
                "name": "Browser",
                "value": "Edge",
                "datatype": "String",
                "direction": "In",
            }
        ],
        "steps": [
            {
                "name": "Open browser",
                "action": "Click",
                "target": "EdgeIcon",
            }
        ],
    }

    component = ComponentParser().parse(raw)

    assert component.name == "Browser_Start_QWERTZ"
    assert len(component.parameters) == 1
    assert component.parameters[0].name == "Browser"
    assert len(component.steps) == 1
    assert component.steps[0].action == "Click"


def test_component_collects_step_issues():
    raw = {
        "name": "UnsupportedComponent",
        "steps": [
            {
                "name": "Custom unsupported step",
                "action": "UnknownAction",
            }
        ],
    }

    component = ComponentParser().parse(raw)

    assert component.steps[0].status == ConversionStatus.UNSUPPORTED
    assert len(component.issues) == 1