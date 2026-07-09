import json

from uft2uipath.ast import BusinessComponent, Project, Step, UftTestCase
from uft2uipath.generator.project_generator import UiPathProjectGenerator


def test_generate_uipath_project(tmp_path):
    project = Project(
        name="Migration_BPT",
        tests=[
            UftTestCase(
                name="Simple Test",
                components=[
                    BusinessComponent(
                        name="Browser_Start_QWERTZ",
                        steps=[
                            Step(name="Click Edge", action="Click"),
                        ],
                    )
                ],
            )
        ],
    )

    output = UiPathProjectGenerator().generate(project, tmp_path)

    assert output.exists()
    assert (output / "project.json").exists()
    assert (output / "Main.xaml").exists()
    assert (output / "Workflows" / "Browser_Start_QWERTZ.xaml").exists()

    data = json.loads((output / "project.json").read_text(encoding="utf-8"))

    assert data["name"] == "Migration_BPT"
    assert data["projectType"] == "TestAutomation"

    main = (output / "Main.xaml").read_text(encoding="utf-8")
    workflow = (output / "Workflows" / "Browser_Start_QWERTZ.xaml").read_text(
        encoding="utf-8"
    )

    assert "InvokeWorkflowFile" in main
    assert "Browser_Start_QWERTZ.xaml" in main
    assert "ui:Click" in workflow