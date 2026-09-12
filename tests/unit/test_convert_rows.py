import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from uft2uipath.convert_rows import convert_rows

DEMO = Path(__file__).resolve().parents[2] / "examples" / "decoded_alm_demo.json"


def write_source(tmp_path, mutate=None):
    payload = json.loads(DEMO.read_text(encoding="utf-8"))
    if mutate:
        mutate(payload)
    source = tmp_path / "rows.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    return source


def test_convert_rows_cli_generates_review_scaffold(tmp_path):
    source = write_source(tmp_path)
    parent = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-m", "uft2uipath", "convert-rows",
         str(source), "--out", str(parent)], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    output = parent / "DemoMigration"
    for file in output.rglob("*.xaml"):
        ET.parse(file)
    model = json.loads((output / "Data/migration_model.json").read_text())
    steps = model["project"]["tests"][0]["components"][0]["steps"]
    assert [s["name"] for s in steps] == ["Enter username", "Check login result"]
    assert all(s["status"] == "unsupported" for s in steps)
    assert len(model["source_tables"]["COMPONENT_STEP"]) == 2
    report = json.loads((output / "Reports/ConversionReport.json").read_text())
    assert report["executable_verified"] is False
    assert report["todo_step_instance_count"] == 2
    assert report["workflow_count"] == 1
    assert (output / "project.json").is_file()


def test_convert_rows_preserves_existing_output(tmp_path):
    source = write_source(tmp_path)
    output = convert_rows(source, tmp_path / "out")
    marker = output / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(FileExistsError):
        convert_rows(source, tmp_path / "out")
    assert marker.read_text() == "keep"


@pytest.mark.parametrize("name", ["../escape", "CON", "bad:name", "trailing."])
def test_invalid_project_names_write_no_output(tmp_path, name):
    source = write_source(tmp_path, lambda p: p.update(project_name=name))
    parent = tmp_path / "out"
    with pytest.raises(ValueError):
        convert_rows(source, parent)
    assert not parent.exists()


def test_missing_component_reference_is_rejected(tmp_path):
    source = write_source(
        tmp_path, lambda p: p["BPTEST_TO_COMPONENTS"][0].update(BC_CO_ID="999")
    )
    with pytest.raises(ValueError, match="missing component"):
        convert_rows(source, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_case_insensitive_component_collision_is_rejected(tmp_path):
    source = write_source(
        tmp_path, lambda p: p["COMPONENT"].append(
            {"CO_ID": "11", "CO_NAME": "logincomponent"}
        )
    )
    with pytest.raises(ValueError, match="collide"):
        convert_rows(source, tmp_path / "out")


def test_repeated_component_uses_one_workflow(tmp_path):
    def repeat(payload):
        payload["BPTEST_TO_COMPONENTS"].append(
            {"BC_ID": "2", "BC_BPT_ID": "1", "BC_CO_ID": "10", "BC_ORDER": "2"}
        )
    source = write_source(tmp_path, repeat)
    output = convert_rows(source, tmp_path / "out")
    root = ET.parse(output / "Main.xaml")
    invocations = root.findall(".//{http://schemas.uipath.com/workflow/activities}InvokeWorkflowFile")
    assert len(invocations) == 2
    assert len(list((output / "Workflows").glob("*.xaml"))) == 1
