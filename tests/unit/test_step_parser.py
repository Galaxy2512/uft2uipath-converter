# Tests StepParser.parse_action, which maps a known UFT action (e.g. Click) to
# a successful ACTION step, and falls back an unrecognized action to an
# unsupported "Manual Action Placeholder" step with a recorded issue.
from uft2uipath.ast import ConversionStatus, StepType
from uft2uipath.parser.step_parser import StepParser


def test_parse_known_action():
    step = StepParser().parse_action(
        name="Click login",
        action="Click",
        target="LoginButton",
    )

    assert step.type == StepType.ACTION
    assert step.action == "Click"
    assert step.status == ConversionStatus.SUCCESS


def test_parse_unsupported_action():
    step = StepParser().parse_action(
        name="Custom action",
        action="UnknownAction",
    )

    assert step.action == "Manual Action Placeholder"
    assert step.status == ConversionStatus.UNSUPPORTED
    assert len(step.issues) == 1