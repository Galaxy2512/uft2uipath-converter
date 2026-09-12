import xml.etree.ElementTree as ET

from uft2uipath.ast import (
    BusinessComponent, ConversionStatus, Project, Step, UftTestCase,
)
from uft2uipath.generator.activity_generator import ActivityGenerator
from uft2uipath.generator.project_generator import UiPathProjectGenerator


UI = "http://schemas.uipath.com/workflow/activities"
WF = "http://schemas.microsoft.com/netfx/2009/xaml/activities"


def parse_activity(step):
    return ET.fromstring(
        f'<Root xmlns:ui="{UI}">{ActivityGenerator().generate(step)}</Root>'
    )[0]


def test_activity_xml_preserves_special_characters():
    value = 'A&B <tag> "quoted"\nnext'

    for action, attribute in (
        ("Type Into", "Text"),
        ("Log Message", "Message"),
    ):
        element = parse_activity(
            Step(name=value, action=action, value=value)
        )
        assert element.attrib["DisplayName"] == value
        assert element.attrib[attribute] == value

    element = parse_activity(
        Step(
            name=value,
            status=ConversionStatus.UNSUPPORTED,
            raw={"action": value},
        )
    )
    assert element.attrib["Text"] == "Unsupported UFT action: " + value


def test_activity_xml_preserves_zero_and_empty_values():
    for action, attribute in (
        ("Type Into", "Text"),
        ("Log Message", "Message"),
    ):
        for value in (0, False, ""):
            element = parse_activity(
                Step(name="Example", action=action, value=value)
            )
            assert element.attrib[attribute] == str(value)


def test_project_xml_namespace_and_workflow_reference(tmp_path):
    component = BusinessComponent(
        name="Login & Check",
        steps=[Step(name='Click "OK" & continue', action="Click")],
    )
    project = Project(
        name="Demo & Test",
        tests=[UftTestCase(name="Test", components=[component])],
    )

    output = UiPathProjectGenerator().generate(project, tmp_path)
    root = ET.parse(output / "Main.xaml").getroot()

    sequence = root.find(f"{{{WF}}}Sequence")
    assert sequence.attrib["DisplayName"] == project.name

    invoke = root.find(f".//{{{UI}}}InvokeWorkflowFile")
    assert invoke is not None
    assert invoke.attrib["DisplayName"] == component.name

    reference = invoke.attrib["WorkflowFileName"]
    assert reference == "Workflows\\Login & Check.xaml"

    workflow = output.joinpath(*reference.split("\\"))
    assert workflow.is_file()
    ET.parse(workflow)
