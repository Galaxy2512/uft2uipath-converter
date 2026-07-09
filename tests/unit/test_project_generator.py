import json

from uft2uipath.ast import Project
from uft2uipath.generator.project_generator import UiPathProjectGenerator


def test_generate_uipath_project(tmp_path):
    project = Project(name="Migration_BPT")

    output = UiPathProjectGenerator().generate(project, tmp_path)

    assert output.exists()
    assert (output / "project.json").exists()
    assert (output / "Main.xaml").exists()

    data = json.loads((output / "project.json").read_text(encoding="utf-8"))

    assert data["name"] == "Migration_BPT"
    assert data["projectType"] == "TestAutomation"