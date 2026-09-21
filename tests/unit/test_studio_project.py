# Tests script_generation.project.migrate_project, which assembles a full
# UiPath Studio project (project.json, generated test/workflow XAML files,
# optional zip package) from an example manifest+bindings fixture, including
# template compatibility checks and the `migrate-project` CLI command.
import json
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from uft2uipath.script_generation.emitter import q, UI, X
from uft2uipath.script_generation.project import migrate_project, project_metadata

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/workflow_generation"


def build(tmp_path, make_zip=False):
    return migrate_project(
        EXAMPLE / "manifest.json", EXAMPLE / "target-bindings.json",
        tmp_path / "MigrationPreview", make_zip=make_zip,
    )


def test_project_registers_generated_test_files(tmp_path):
    output, _ = build(tmp_path)
    data = json.loads((output / "project.json").read_text())
    assert data["targetFramework"] == "Windows"
    assert data["expressionLanguage"] == "CSharp"
    assert data["designOptions"]["outputType"] == "Tests"
    cases = data["designOptions"]["fileInfoCollection"]
    assert len(cases) == 2
    for case in cases:
        assert case["testCaseType"] == "TestCase"
        assert output.joinpath(*case["fileName"].split("\\")).is_file()
    assert (output / data["main"]).is_file()


def test_studio_xaml_contains_explicit_csharp_nodes(tmp_path):
    output, _ = build(tmp_path)
    root = ET.parse(output / "Workflows/Component_10.xaml")
    assert root.find(".//" + q("CSharpValue")) is not None
    reference = root.find(".//" + q("CSharpReference"))
    assert reference.text == "exists_1"
    type_into = root.find(".//" + q("TypeInto", UI))
    assert "Text" not in type_into.attrib
    assert type_into.find(".//" + q("CSharpValue")).text == "in_User"
    exists = root.find(".//" + q("UiElementExists", UI))
    assert exists.find(".//" + q("Target", UI)).attrib["Selector"].startswith("<html")
    for scope in root.findall(".//" + q("BrowserScope", UI)):
        assert scope.attrib["Selector"].startswith("<html")
        for target in scope.findall(".//" + q("Target", UI)):
            assert target.attrib["Selector"].startswith("<webctrl")
    for element in root.iter():
        assert not any(v.startswith("[") and v.endswith("]") for v in element.attrib.values())


def test_zip_contains_project_tests_and_source_evidence(tmp_path):
    output, archive = build(tmp_path, make_zip=True)
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert "project.json" in names
        assert "Tests/Test_1.xaml" in names
        assert "Data/Analysis/Sources/component_10.source" in names
        assert package.read("project.json") == (output / "project.json").read_bytes()
    report = json.loads((output / "generation-report.json").read_text())
    assert report["studio_project"]["studio_load_verified"] is False
    assert report["blocked_test_count"] == 2


def test_existing_archive_is_not_overwritten(tmp_path):
    archive = tmp_path / "MigrationPreview.zip"
    archive.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        build(tmp_path, make_zip=True)
    assert archive.read_bytes() == b"keep"
    assert not (tmp_path / "MigrationPreview").exists()


@pytest.mark.parametrize("change", [
    {"targetFramework": "Legacy"},
    {"expressionLanguage": "VisualBasic"},
])
def test_incompatible_template_is_rejected(tmp_path, change):
    template = project_metadata("Example", [])
    template.update(change)
    path = tmp_path / "template.json"
    path.write_text(json.dumps(template))
    with pytest.raises(ValueError):
        project_metadata("Target", [], path)


def test_project_cli_generates_openable_file_layout(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "uft2uipath", "migrate-project",
         str(EXAMPLE / "manifest.json"), "--bindings", str(EXAMPLE / "target-bindings.json"),
         "--out", str(tmp_path / "Project"), "--zip"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Open in Studio:" in result.stdout
    assert (tmp_path / "Project.zip").is_file()
