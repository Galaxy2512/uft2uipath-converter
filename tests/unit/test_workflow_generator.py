from uft2uipath.ast import BusinessComponent, Step
from uft2uipath.generator.workflow_generator import WorkflowGenerator


def test_generate_component_workflow(tmp_path):
    component = BusinessComponent(
        name="Browser_Start_QWERTZ",
        steps=[
            Step(name="Click Edge", action="Click"),
        ],
    )

    file_path = WorkflowGenerator().generate_component_workflow(
        component,
        tmp_path,
    )

    assert file_path.exists()
    assert file_path.name == "Browser_Start_QWERTZ.xaml"

    content = file_path.read_text(encoding="utf-8")

    assert "Browser_Start_QWERTZ" in content
    assert "<Sequence" in content
    assert "ui:Click" in content