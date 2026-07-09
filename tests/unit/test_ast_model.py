from uft2uipath.ast import (
    BusinessComponent,
    ConversionStatus,
    Project,
    Step,
    StepType,
    UftTestCase,
)


def test_create_project_ast():
    step = Step(
        name="Open browser",
        type=StepType.ACTION,
        action="open_browser",
        target="Edge",
    )

    component = BusinessComponent(
        name="Browser_Start_QWERTZ",
        steps=[step],
    )

    test_case = UftTestCase(
        name="Simple browser test",
        components=[component],
    )

    project = Project(
        name="Migration_BPT",
        tests=[test_case],
    )

    assert project.name == "Migration_BPT"
    assert project.tests[0].components[0].name == "Browser_Start_QWERTZ"
    assert project.tests[0].components[0].steps[0].type == StepType.ACTION
    assert project.tests[0].status == ConversionStatus.SUCCESS