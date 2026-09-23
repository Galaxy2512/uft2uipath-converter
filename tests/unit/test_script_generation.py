# Tests the script_generation emitter/batch pipeline that turns analyzed VBScript
# operations into UiPath XAML: If/Exists mapping, parameters as typed InArguments,
# literal escaping, blocking output when semantics or object bindings are
# unsupported/unresolved, and bundling shared components across multiple tests
# (including the CLI entry point).
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_analysis.batch import run_batch
from uft2uipath.script_generation.batch import emit_bundle
from uft2uipath.script_generation.emitter import ComponentEmitter, UI, X, q

TARGET = 'Browser("B").Page("P").WebEdit("User")'
BUTTON = 'Browser("B").Page("P").WebButton("Go")'
EXISTS = 'Browser("B").Page("P").WebElement("Ready")'
SET = TARGET + '.Set Parameter("User")'
CLICK = BUTTON + '.Click'


def bindings():
    return {
        "parameters": {"User": {"name": "in_User", "type": "String", "direction": "In"}},
        "objects": [
            {"uft": {"browser": "B", "page": "P", "object_type": kind, "logical_name": name},
             "selector": f"<html title='Fixture' /><webctrl id='{name}' />",
             "accepted_for_generation": True, "verification_status": "accepted_unverified",
             "input_method": "Simulate", "timeout_ms": 30000,
             "browser_type": "Edge"}
            for kind, name in (("WebEdit", "User"), ("WebButton", "Go"), ("WebElement", "Ready"))
        ],
    }


def emit(source, config=None):
    return ComponentEmitter("10", analyze_source(source), bindings() if config is None else config).generate()


def first_action(root):
    seq = root.find(q("Sequence"))
    return next(child for child in seq if child.tag != q("Sequence.Variables"))


def test_if_uses_exists_and_preserves_order_and_branches():
    source = f"If {EXISTS}.Exist(10) Then\n{SET}\nElse\n{CLICK}\nEnd If\n{CLICK}"
    root, report = emit(source)
    assert report["status"] == "mapped_unverified"
    assert report["executable_verified"] is False
    seq = root.find(q("Sequence"))
    assert [child.tag for child in seq] == [
        q("Sequence.Variables"), q("UiElementExists", UI), q("If"), q("BrowserScope", UI),
    ]
    exists = seq[1]
    assert exists.attrib["Exists"] == "[exists_1]"
    assert exists.find(".//" + q("Target", UI)).attrib["TimeoutMS"] == "10000"
    branch = seq[2]
    assert branch.attrib["Condition"] == "[exists_1]"
    assert branch.find("./" + q("If.Then")).find(".//" + q("TypeInto", UI)) is not None
    assert branch.find("./" + q("If.Else")).find(".//" + q("Click", UI)) is not None
    assert [row["line_number"] for row in report["trace"]] == [1, 2, 4, 6]


def test_parameter_becomes_typed_argument_not_a_fixed_value():
    root, report = emit(SET)
    prop = root.find("./" + q("Members", X) + "/" + q("Property", X))
    assert prop.attrib == {"Name": "in_User", "Type": "InArgument(x:String)"}
    activity = root.find(".//" + q("TypeInto", UI))
    assert activity.attrib["Text"] == "[in_User]"
    assert activity.attrib["EmptyField"] == "True"


def test_special_literal_is_csharp_expression_and_xml_roundtrips():
    source = TARGET + '.Set "A&B <x> ""quoted"""'
    root, _ = emit(source)
    root = ET.fromstring(ET.tostring(root))
    value = root.find(".//" + q("TypeInto", UI)).attrib["Text"]
    assert value == '["A&B <x> \\"quoted\\""]'


@pytest.mark.parametrize("source", [
    'Reporter.ReportEvent micCustom, "Title", "Failure"',
    'Browser("B").Close',
    TARGET + '.SetSecure Parameter("User")',
    TARGET + '.Set user & "x"',
])
def test_unsupported_semantics_block_before_any_ui(source):
    root, report = emit(CLICK + "\n" + source)
    assert report["status"] == "blocked"
    assert first_action(root).tag == q("Throw")
    assert root.find(".//" + q("Click", UI)) is not None
    assert report["trace"][-1]["raw"] == source


def test_declarations_do_not_block_and_emit_no_activity():
    root, report = emit("Option Explicit\nDim user\n" + CLICK)

    assert report["status"] == "mapped_unverified"
    assert first_action(root).tag != q("Throw")
    assert [trace["activity"] for trace in report["trace"]] == [
        "(declaration)", "(declaration)", "Click",
    ]


def test_unresolved_else_blocks_entire_workflow_before_condition():
    root, report = emit(f"If {EXISTS}.Exist(5) Then\n{CLICK}\nElse\nCustomCheck\nEnd If")
    assert report["status"] == "blocked"
    assert first_action(root).tag == q("Throw")
    assert root.find(".//" + q("If")) is not None


@pytest.mark.parametrize("change", ["missing_selector", "unverified", "missing_method", "missing_param"])
def test_missing_binding_prevents_execution(change):
    config = bindings()
    if change == "missing_selector":
        config["objects"][0].pop("selector")
    elif change == "unverified":
        config["objects"][0]["accepted_for_generation"] = False
    elif change == "missing_method":
        config["objects"][0].pop("input_method")
    else:
        config["parameters"] = {}
    root, report = emit(SET, config)
    assert report["status"] == "blocked"
    assert first_action(root).tag == q("Throw")


def test_nested_if_has_distinct_result_variables():
    source = f"If {EXISTS}.Exist(2) Then\nIf {EXISTS}.Exist(3) Then\n{CLICK}\nEnd If\nEnd If"
    root, report = emit(source)
    assert report["status"] == "mapped_unverified"
    variables = root.findall(".//" + q("Variable"))
    assert [v.attrib["Name"] for v in variables] == ["exists_1", "exists_2"]


def test_partial_object_chain_remains_blocked_even_with_matching_name():
    root, report = emit("Wrapper()." + CLICK)
    assert first_action(root).tag == q("Throw")
    assert any(i["code"] == "unsupported_statement" for i in report["issues"])


def setup_bundle(tmp_path):
    (tmp_path / "source.vbs").write_text(SET, encoding="utf-8")
    rows = {
        "project_name": "Fixture",
        "TEST": [{"TS_TEST_ID": "1", "TS_NAME": "One"}, {"TS_TEST_ID": "2", "TS_NAME": "Two"}],
        "COMPONENT": [{"CO_ID": "10", "CO_NAME": "Shared"}], "COMPONENT_STEP": [],
        "BPTEST_TO_COMPONENTS": [
            {"BC_ID": "1", "BC_BPT_ID": "1", "BC_CO_ID": "10", "BC_ORDER": "1"},
            {"BC_ID": "2", "BC_BPT_ID": "2", "BC_CO_ID": "10", "BC_ORDER": "1"},
        ],
    }
    (tmp_path / "rows.json").write_text(json.dumps(rows))
    (tmp_path / "manifest.json").write_text(json.dumps({
        "rows": "rows.json", "bindings": [{"component_id": "10", "script": "source.vbs"}],
    }))
    run_batch(tmp_path / "manifest.json", tmp_path / "analysis")
    config = {
        "profile": "windows-csharp-classic", "components": {"10": bindings()},
        "calls": {
            "1": {"1": {"in_User": {"argument": "in_User_First", "type": "String"}}},
            "2": {"2": {"in_User": {"argument": "in_User_Second", "type": "String"}}},
        },
    }
    (tmp_path / "bindings.json").write_text(json.dumps(config))
    return config


def test_separate_tests_share_workflow_but_keep_distinct_arguments(tmp_path):
    setup_bundle(tmp_path)
    report = emit_bundle(tmp_path / "analysis", tmp_path / "bindings.json", tmp_path / "out")
    assert report["blocked_test_count"] == 0
    assert len(list((tmp_path / "out/Workflows").glob("*.xaml"))) == 1
    for index, expected in ((1, "in_User_First"), (2, "in_User_Second")):
        root = ET.parse(tmp_path / f"out/Tests/Test_{index}.xaml")
        arg = root.find(".//" + q("InArgument"))
        assert arg.attrib[q("Key", X)] == "in_User"
        assert arg.find(q("CSharpValue")).text == expected
        invoke = root.find(".//" + q("InvokeWorkflowFile", UI))
        assert invoke.attrib["WorkflowFileName"] == "Workflows\\Component_10.xaml"
    assert not (tmp_path / "out/project.json").exists()


def test_missing_call_binding_guards_test_before_invocation(tmp_path):
    config = setup_bundle(tmp_path)
    config["calls"] = {}
    (tmp_path / "bindings.json").write_text(json.dumps(config))
    report = emit_bundle(tmp_path / "analysis", tmp_path / "bindings.json", tmp_path / "out")
    assert report["blocked_test_count"] == 2
    assert first_action(ET.parse(tmp_path / "out/Tests/Test_1.xaml").getroot()).tag == q("Throw")


def test_fixture_profile_always_blocks_live_execution(tmp_path):
    config = setup_bundle(tmp_path)
    config["fixture_only"] = True
    (tmp_path / "bindings.json").write_text(json.dumps(config))
    report = emit_bundle(tmp_path / "analysis", tmp_path / "bindings.json", tmp_path / "out")
    assert report["blocked_component_count"] == 1
    assert report["blocked_test_count"] == 2
    assert first_action(ET.parse(tmp_path / "out/Workflows/Component_10.xaml").getroot()).tag == q("Throw")


def test_output_protection_and_analysis_snapshot(tmp_path):
    setup_bundle(tmp_path)
    emit_bundle(tmp_path / "analysis", tmp_path / "bindings.json", tmp_path / "out")
    assert (tmp_path / "out/Data/Analysis/Sources/component_10.source").read_text() == SET
    with pytest.raises(FileExistsError):
        emit_bundle(tmp_path / "analysis", tmp_path / "bindings.json", tmp_path / "out")


def test_cli_generates_bundle(tmp_path):
    setup_bundle(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "uft2uipath", "emit-workflows",
         str(tmp_path / "analysis"), "--bindings", str(tmp_path / "bindings.json"),
         "--out", str(tmp_path / "out")], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "unverified" in result.stdout
    for file in (tmp_path / "out").rglob("*.xaml"):
        ET.parse(file)


def test_missing_source_analysis_cannot_emit_success(tmp_path):
    setup_bundle(tmp_path)
    analysis_file = tmp_path / "analysis/Components/component_10.json"
    analysis = json.loads(analysis_file.read_text())
    analysis.pop("operations")
    analysis["status"] = "error"
    analysis_file.write_text(json.dumps(analysis))
    report = emit_bundle(tmp_path / "analysis", tmp_path / "bindings.json", tmp_path / "out")
    assert report["blocked_component_count"] == 1
