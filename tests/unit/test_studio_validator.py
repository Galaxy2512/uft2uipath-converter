import json
import xml.etree.ElementTree as ET

from uft2uipath.script_generation.emitter import UI, document, q, write_xaml
from uft2uipath.script_generation.project import project_metadata
from uft2uipath.studio_validation import validate_project


def write_project(root):
    (root / "Tests").mkdir(parents=True)
    (root / "Workflows").mkdir()
    metadata = project_metadata("Fixture", [{"test_id": 5}])
    (root / "project.json").write_text(json.dumps(metadata), encoding="utf-8")

    main, _ = document("Main", {})
    write_xaml(root / "Main.xaml", main)

    test, sequence = document("Test_5", {})
    ET.SubElement(sequence, q("InvokeWorkflowFile", UI), {
        "WorkflowFileName": "Workflows\\Action_1.xaml",
    })
    write_xaml(root / "Tests" / "Test_5.xaml", test)

    action, _ = document("Action_1", {})
    write_xaml(root / "Workflows" / "Action_1.xaml", action)


def test_static_validator_accepts_generated_project_structure(tmp_path):
    root = tmp_path / "project"
    write_project(root)

    report = validate_project(root)

    assert report["static_validation_passed"] is True
    assert report["studio_load_verified"] is False
    assert report["executable_verified"] is False
    assert report["errors"] == []
    assert "project.json" in report["checked_files"]
    assert "Tests/Test_5.xaml" in report["checked_files"]


def test_static_validator_reports_missing_registered_test(tmp_path):
    root = tmp_path / "project"
    write_project(root)
    (root / "Tests" / "Test_5.xaml").unlink()

    report = validate_project(root)

    assert report["static_validation_passed"] is False
    assert any(error["code"] == "missing_registered_test" for error in report["errors"])


def test_static_validator_reports_broken_workflow_reference(tmp_path):
    root = tmp_path / "project"
    write_project(root)
    (root / "Workflows" / "Action_1.xaml").unlink()

    report = validate_project(root)

    assert report["static_validation_passed"] is False
    assert any(error["code"] == "broken_workflow_reference" for error in report["errors"])


def test_static_validator_reports_invalid_xaml(tmp_path):
    root = tmp_path / "project"
    write_project(root)
    (root / "Workflows" / "Action_1.xaml").write_text("<Activity>", encoding="utf-8")

    report = validate_project(root)

    assert report["static_validation_passed"] is False
    assert any(error["code"] == "invalid_xaml_xml" for error in report["errors"])
