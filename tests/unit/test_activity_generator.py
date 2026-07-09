from uft2uipath.ast import ConversionStatus, Step
from uft2uipath.generator.activity_generator import ActivityGenerator


def test_generate_click_activity():
    step = Step(name="Click Login", action="Click")

    xaml = ActivityGenerator().generate(step)

    assert "ui:Click" in xaml
    assert "Click Login" in xaml


def test_generate_unsupported_todo_activity():
    step = Step(
        name="Custom Step",
        action="Manual Action Placeholder",
        status=ConversionStatus.UNSUPPORTED,
        raw={"action": "CustomUftAction"},
    )

    xaml = ActivityGenerator().generate(step)

    assert "TODO" in xaml
    assert "CustomUftAction" in xaml