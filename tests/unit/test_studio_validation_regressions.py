"""Regressions from Studio load and UI-DBP-006 reports; not a Studio runtime test."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_generation.emitter import ComponentEmitter, UI, X, document, q, throw, write_xaml
from uft2uipath.script_generation.project import migrate_project

PREFIX = 'Browser("B").Page("P")'
SET = PREFIX + '.WebEdit("User").Set "username"'
CLICK = PREFIX + '.WebButton("Go").Click'
EXIST = PREFIX + '.WebElement("Ready").Exist(10)'


def config():
    return {"objects": [
        {"uft": {"browser": "B", "page": "P", "object_type": kind, "logical_name": name},
         "selector": f"<html app='msedge.exe' title='Fixture' /><webctrl id='{name}' />",
         "verified": True, "input_method": "Simulate", "timeout_ms": 30000,
         "browser_type": "Edge"}
        for kind, name in (("WebEdit", "User"), ("WebButton", "Go"), ("WebElement", "Ready"))
    ]}


def emit(tmp_path, source, bindings=None):
    root, report = ComponentEmitter("20", analyze_source(source), config() if bindings is None else bindings).generate()
    path = tmp_path / "Component_20.xaml"
    write_xaml(path, root)
    return ET.parse(path).getroot(), report


@pytest.mark.parametrize("source", ["CustomValidation", CLICK])
def test_argumentless_workflow_omits_members_but_keeps_activity_body(tmp_path, source):
    root, report = emit(tmp_path, source)
    assert root.find(q("Members", X)) is None
    assert root.find(q("TextExpression.NamespacesForImplementation")) is not None
    assert root.find(q("TextExpression.ReferencesForImplementation")) is not None
    sequence = root.find(q("Sequence"))
    assert sequence is not None and len(sequence)
    if report["status"] == "blocked":
        assert sequence[0].tag == q("Throw")
        assert sequence[0].find(".//" + q("CSharpValue")) is not None


def test_nonempty_members_are_preserved(tmp_path):
    root, sequence = document("WithArguments", {"in_Name": "String"})
    sequence.append(throw("test"))
    path = tmp_path / "WithArguments.xaml"
    write_xaml(path, root)
    prop = ET.parse(path).find("./" + q("Members", X) + "/" + q("Property", X))
    assert prop.attrib == {"Name": "in_Name", "Type": "InArgument(x:String)"}


def test_exists_stays_before_if_and_actions_share_scope_only_inside_their_branch(tmp_path):
    root, report = emit(tmp_path, f"If {EXIST} Then\n{SET}\n{CLICK}\nElse\n{CLICK}\nEnd If")
    assert report["status"] == "mapped_unverified"
    sequence = root.find(q("Sequence"))
    assert [node.tag for node in sequence] == [q("Sequence.Variables"), q("UiElementExists", UI), q("If")]
    assert sequence[1].find(".//" + q("Target", UI)).attrib["TimeoutMS"] == "10000"
    assert sequence[1].find(".//" + q("Target", UI)).attrib["Selector"].startswith("<html")
    scopes = sequence[2].findall(".//" + q("BrowserScope", UI))
    assert len(scopes) == 2
    for scope, expected in zip(scopes, [["TypeInto", "Click"], ["Click"]]):
        assert scope.attrib["BrowserType"] == "Edge"
        assert scope.attrib["ContinueOnError"] == "False"
        assert [child.tag for child in scope.find(".//" + q("Sequence"))] == [q(kind, UI) for kind in expected]
        for target in scope.findall(".//" + q("Target", UI)):
            assert target.attrib["Selector"].startswith("<webctrl")
    assert not root.findall(".//" + q("OpenBrowser", UI))
    assert [row["line_number"] for row in report["trace"]] == [1, 2, 3, 5]


@pytest.mark.parametrize("difference", ["browser", "selector", "browser_type", "timeout_ms"])
def test_different_scope_identity_is_not_merged(tmp_path, difference):
    bindings = config()
    source_click = CLICK
    if difference == "browser":
        bindings["objects"][1]["uft"]["browser"] = "Other"
        source_click = CLICK.replace('Browser("B")', 'Browser("Other")')
    elif difference == "selector":
        bindings["objects"][1]["selector"] = "<html title='Other' /><webctrl id='Go' />"
    elif difference == "browser_type":
        bindings["objects"][1]["browser_type"] = "Chrome"
        bindings["objects"][1]["selector"] = "<html app='chrome.exe' title='Fixture' /><webctrl id='Go' />"
    else:
        bindings["objects"][1]["timeout_ms"] = 15000
    root, report = emit(tmp_path, SET + "\n" + source_click, bindings)
    assert report["status"] == "mapped_unverified"
    scopes = root.find(q("Sequence")).findall(q("BrowserScope", UI))
    assert len(scopes) == 2
    assert scopes[0].find(".//" + q("TypeInto", UI)) is not None
    assert scopes[1].find(".//" + q("Click", UI)) is not None


def test_click_ends_group_so_next_action_reattaches_after_possible_navigation(tmp_path):
    root, _ = emit(tmp_path, SET + "\n" + CLICK + "\n" + SET)
    scopes = root.findall(".//" + q("BrowserScope", UI))
    assert len(scopes) == 2
    assert [child.tag for child in scopes[0].find(".//" + q("Sequence"))] == [q("TypeInto", UI), q("Click", UI)]
    assert [child.tag for child in scopes[1].find(".//" + q("Sequence"))] == [q("TypeInto", UI)]


@pytest.mark.parametrize("change", [
    {"browser_type": None},
    {"browser_type": "Unknown"},
    {"selector": "<webctrl id='User' />"},
    {"selector": "<html title='Fixture' />"},
    {"selector": "<html title='Fixture'><webctrl id='User' /></html>"},
    {"selector": "<html title='Fixture' />unexpected<webctrl id='User' />"},
])
def test_unresolved_scope_blocks_before_valid_ui_actions(tmp_path, change):
    bindings = config()
    bindings["objects"][0].update(change)
    root, report = emit(tmp_path, CLICK + "\n" + SET, bindings)
    assert report["status"] == "blocked"
    assert root.find(q("Sequence"))[0].tag == q("Throw")
    assert root.find(".//" + q("TypeInto", UI)) is None
    assert root.find(".//" + q("Click", UI)) is not None


def test_selector_split_preserves_attributes_and_frame_path(tmp_path):
    bindings = config()
    original = "<html title='A &amp; B' app='msedge.exe' /><webctrl tag='IFRAME' id='frame' /><webctrl tag='INPUT' aaname='User &quot;name&quot;' />"
    bindings["objects"][0]["selector"] = original
    root, report = emit(tmp_path, SET, bindings)
    assert report["status"] == "mapped_unverified"
    scope = root.find(".//" + q("BrowserScope", UI))
    partial = scope.find(".//" + q("Target", UI)).attrib["Selector"]
    combined = ET.fromstring("<root>" + scope.attrib["Selector"] + partial + "</root>")
    expected = ET.fromstring("<root>" + original + "</root>")
    assert [(n.tag, n.attrib) for n in combined] == [(n.tag, n.attrib) for n in expected]
    assert bindings["objects"][0]["selector"] == original


def test_generated_package_has_no_empty_members_or_invoke_arguments(tmp_path):
    example = Path(__file__).resolve().parents[2] / "examples/workflow_generation"
    output, _ = migrate_project(example / "manifest.json", example / "target-bindings.json", tmp_path / "Preview")
    for path in output.rglob("*.xaml"):
        root = ET.parse(path)
        for tag in (q("Members", X), q("InvokeWorkflowFile.Arguments", UI)):
            assert all(len(element) for element in root.findall(".//" + tag)), path
    report = json.loads((output / "generation-report.json").read_text())
    assert report["blocked_component_count"] == 2
    assert report["studio_project"]["studio_load_verified"] is False


def test_assign_and_delay_use_explicit_csharp_nodes(tmp_path):
    source = 'URL = "http://example.test/"\nWait 10'
    root, report = emit(tmp_path, source, {"objects": []})

    assert report["status"] == "mapped_unverified"
    assign = root.find(".//" + q("Assign"))
    out_arg = assign.find(".//" + q("OutArgument"))
    assert out_arg.text is None
    assert out_arg.find(q("CSharpReference")).text == "URL"

    delay = root.find(".//" + q("Delay"))
    assert "Duration" not in delay.attrib
    duration = delay.find(q("Delay.Duration") + "/" + q("InArgument"))
    assert duration is not None
    assert duration.find(q("CSharpValue")).text == "TimeSpan.FromSeconds(10)"

    for element in root.iter():
        for value in element.attrib.values():
            assert not (isinstance(value, str) and value.startswith("[") and value.endswith("]"))
        if element.text:
            assert not (element.text.startswith("[") and element.text.endswith("]"))
