import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_analysis.batch import run_batch

CLICK = 'Browser("B").Page("P").WebButton("Go").Click'
SET = 'Browser("B").Page("P").WebEdit("User").Set Parameter("User")'


def setup_case(tmp_path, count=2):
    rows = {
        "project_name": "Test",
        "TEST": [{"TS_TEST_ID": "1", "TS_NAME": "Test A"}],
        # Intentionally identical names: IDs, not names, identify scripts.
        "COMPONENT": [{"CO_ID": str(n), "CO_NAME": "Same name"} for n in range(1, count + 1)],
        "COMPONENT_STEP": [],
        "BPTEST_TO_COMPONENTS": [
            {"BC_ID": str(n), "BC_BPT_ID": "1", "BC_CO_ID": str(n),
             "BC_ORDER": str(n), "custom_instance_value": f"value-{n}"}
            for n in range(1, count + 1)
        ],
    }
    bindings = []
    for n in range(1, count + 1):
        path = tmp_path / f"script{n}.vbs"
        path.write_text(CLICK, encoding="utf-8")
        bindings.append({"component_id": str(n), "script": path.name})
    manifest = {"rows": "rows.json", "bindings": bindings}
    save_inputs(tmp_path, rows, manifest)
    return rows, manifest


def save_inputs(path, rows, manifest):
    (path / "rows.json").write_text(json.dumps(rows), encoding="utf-8")
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_branch_types_and_references_are_preserved():
    source = (
        'If Browser("B").Page("P").WebElement("Ready").Exist(10) Then\n'
        + SET + '\nElse\nExitTest(-1)\nEnd  If\n' + CLICK
    )
    result = analyze_source(source)
    block, after = result["operations"]
    assert block["node_type"] == "IfOperation"
    assert block["then_operations"][0]["value"]["node_type"] == "ParameterReference"
    assert block["else_operations"][0]["node_type"] == "ExitTestOperation"
    assert after["node_type"] == "ClickOperation"
    assert after["line_number"] == 6
    assert result["references"]["parameters"] == ["User"]
    assert result["coverage"]["operation_count"] == 4
    assert result["generation_ready"] is False


def test_unknown_expression_and_declarations_have_line_diagnostics():
    source = 'Option Explicit\nDim user\n' + SET.replace('Parameter("User")', 'user & "x"')
    result = analyze_source(source)
    assert result["operations"][0]["raw"] == "Option Explicit"
    assert result["coverage"]["unsupported_statement_count"] == 2
    assert result["coverage"]["unsupported_expression_count"] == 1
    expression = [i for i in result["issues"] if i["code"] == "unsupported_expression"][0]
    assert expression["line_number"] == 3
    assert expression["raw"] == 'user & "x"'


def test_partial_object_match_is_not_certified():
    result = analyze_source('Wrapper().' + CLICK)
    assert any(i["code"] == "unsupported_object_chain" for i in result["issues"])


def test_identical_names_link_by_id_and_preserve_bytes(tmp_path):
    rows, manifest = setup_case(tmp_path)
    original = (SET + "\r\n").encode("utf-8")
    (tmp_path / "script2.vbs").write_bytes(original)
    summary = run_batch(tmp_path / "manifest.json", tmp_path / "out")
    assert summary["analyzed_source_count"] == 2
    out = tmp_path / "out"
    component = read(out / "Components/component_2.json")
    assert component["operations"][0]["node_type"] == "SetTextOperation"
    assert component["sha256"] == hashlib.sha256(original).hexdigest()
    assert (out / component["source_copy"]).read_bytes() == original
    model = read(out / "model.json")
    instances = model["project"]["tests"][0]["components"]
    assert [c["id"] for c in instances] == [1, 2]
    assert instances[1]["raw"]["_bpt_relation"]["custom_instance_value"] == "value-2"
    assert model["source_tables"]["COMPONENT"] == rows["COMPONENT"]


@pytest.mark.parametrize("failure", ["missing", "encoding", "parser"])
def test_one_failed_script_does_not_stop_other_components(tmp_path, failure):
    setup_case(tmp_path)
    script = tmp_path / "script1.vbs"
    if failure == "missing":
        script.unlink()
    elif failure == "encoding":
        script.write_bytes(b"\x80\x81\x82")
    if failure == "parser":
        original = analyze_source
        with patch("uft2uipath.script_analysis.batch.analyze_source",
                   side_effect=[RuntimeError("test parser failure"), original(CLICK)]):
            run_batch(tmp_path / "manifest.json", tmp_path / "out")
    else:
        run_batch(tmp_path / "manifest.json", tmp_path / "out")
    assert read(tmp_path / "out/Components/component_1.json")["status"] == "error"
    assert "operations" in read(tmp_path / "out/Components/component_2.json")
    if failure == "encoding":
        assert (tmp_path / "out/Sources/component_1.source").read_bytes() == b"\x80\x81\x82"


def test_missing_binding_is_reported(tmp_path):
    rows, manifest = setup_case(tmp_path)
    manifest["bindings"].pop()
    save_inputs(tmp_path, rows, manifest)
    run_batch(tmp_path / "manifest.json", tmp_path / "out")
    report = read(tmp_path / "out/report.json")
    assert report["summary"]["component_statuses"]["missing_binding"] == 1
    assert report["tests"][0]["status"] == "blocked"


@pytest.mark.parametrize("mutation", ["duplicate", "unknown_id", "duplicate_entity"])
def test_ambiguous_identity_rejected_before_output(tmp_path, mutation):
    rows, manifest = setup_case(tmp_path)
    if mutation == "duplicate":
        manifest["bindings"].append(manifest["bindings"][0])
    elif mutation == "unknown_id":
        manifest["bindings"][0]["component_id"] = "999"
    else:
        rows["COMPONENT"].append(rows["COMPONENT"][0])
    save_inputs(tmp_path, rows, manifest)
    with pytest.raises(ValueError):
        run_batch(tmp_path / "manifest.json", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_dangling_relation_preserved_and_blocks_report(tmp_path):
    rows, manifest = setup_case(tmp_path)
    rows["BPTEST_TO_COMPONENTS"][0]["BC_CO_ID"] = "999"
    save_inputs(tmp_path, rows, manifest)
    run_batch(tmp_path / "manifest.json", tmp_path / "out")
    report = read(tmp_path / "out/report.json")
    assert report["summary"]["relationship_issue_count"] == 1
    assert report["tests"][0]["status"] == "blocked"
    assert read(tmp_path / "out/model.json")["source_tables"]["BPTEST_TO_COMPONENTS"][0]["BC_CO_ID"] == "999"


def test_utf16_decoding_is_lossless(tmp_path):
    setup_case(tmp_path)
    source = SET.replace('Parameter("User")', '"Šime"')
    (tmp_path / "script1.vbs").write_bytes(source.encode("utf-16"))
    run_batch(tmp_path / "manifest.json", tmp_path / "out")
    component = read(tmp_path / "out/Components/component_1.json")
    assert component["source_text"] == source
    assert component["operations"][0]["value"]["value"] == "Šime"


def test_existing_output_is_untouched(tmp_path):
    setup_case(tmp_path)
    (tmp_path / "out").mkdir()
    marker = tmp_path / "out/keep.txt"
    marker.write_text("keep")
    with pytest.raises(FileExistsError):
        run_batch(tmp_path / "manifest.json", tmp_path / "out")
    assert marker.read_text() == "keep"


def test_cli_fail_on_blockers_still_writes_reports(tmp_path):
    setup_case(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "uft2uipath", "analyze-scripts",
         str(tmp_path / "manifest.json"), "--out", str(tmp_path / "out"),
         "--fail-on-blockers"], capture_output=True, text=True,
    )
    assert result.returncode == 2, result.stderr
    assert (tmp_path / "out/report.json").exists()
    assert "generation-ready: False" in result.stdout


def test_4000_test_instances_analyze_shared_definition_once(tmp_path):
    rows, manifest = setup_case(tmp_path, count=1)
    rows["TEST"] = [{"TS_TEST_ID": str(n), "TS_NAME": f"Test {n}"} for n in range(1, 4001)]
    rows["BPTEST_TO_COMPONENTS"] = [
        {"BC_ID": str(n), "BC_BPT_ID": str(n), "BC_CO_ID": "1", "BC_ORDER": "1"}
        for n in range(1, 4001)
    ]
    save_inputs(tmp_path, rows, manifest)
    with patch("uft2uipath.script_analysis.batch.analyze_source", wraps=analyze_source) as analyzer:
        summary = run_batch(tmp_path / "manifest.json", tmp_path / "out")
    assert analyzer.call_count == 1
    assert summary["test_count"] == summary["component_instance_count"] == 4000
    assert summary["unique_component_count"] == 1


def test_empty_script_is_not_success(tmp_path):
    setup_case(tmp_path)
    (tmp_path / "script1.vbs").write_text("' comment only")
    run_batch(tmp_path / "manifest.json", tmp_path / "out")
    assert read(tmp_path / "out/Components/component_1.json")["status"] == "blocked"


def test_environment_and_report_outcome_require_mapping():
    result = analyze_source('Reporter.ReportEvent micFail, Environment("TestName"), "Failed"')
    assert result["references"]["environment"] == ["TestName"]
    codes = {i["code"] for i in result["issues"]}
    assert "assertion_mapping_required" in codes
    assert "environment_binding_required" in codes


def test_additional_parameter_tables_and_original_inputs_are_retained(tmp_path):
    rows, manifest = setup_case(tmp_path)
    rows["COMPONENT_PARAM"] = [{"component_id": 1, "name": "User", "direction": "In"}]
    save_inputs(tmp_path, rows, manifest)
    rows_bytes = (tmp_path / "rows.json").read_bytes()
    manifest_bytes = (tmp_path / "manifest.json").read_bytes()
    run_batch(tmp_path / "manifest.json", tmp_path / "out")
    output = tmp_path / "out"
    assert (output / "Sources/alm_rows.json").read_bytes() == rows_bytes
    assert (output / "Sources/manifest.json").read_bytes() == manifest_bytes
    model = read(output / "model.json")
    assert model["source_payload"]["COMPONENT_PARAM"] == rows["COMPONENT_PARAM"]
