# Unit tests for ActivityGenerator (uft2uipath/generator/activity_generator.py):
# covers generating UiPath XAML for a supported UFT action (Click) and for an
# unsupported action, which should render as a TODO placeholder that preserves
# the original UFT action name.
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