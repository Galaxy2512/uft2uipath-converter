# Tests the UFT -> UiPath operation registry and the coverage inventory built on
# it: every parser node type has exactly one entry, handlers and statuses agree,
# the emitter dispatches through the registry, and blocked lines are counted by
# reason so mappings can be prioritised.
import inspect

import pytest

from uft2uipath.mapping import operation_registry as registry
from uft2uipath.mapping.inventory import build_inventory, categorize
from uft2uipath.parser import uft_script_nodes as nodes
from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_generation.emitter import ComponentEmitter

EXISTS = 'Browser("B").Page("P").WebElement("Ready")'


def parser_node_types():
    return {
        name for name, cls in inspect.getmembers(nodes, inspect.isclass)
        if cls.__module__ == nodes.__name__
        and (issubclass(cls, nodes.ScriptOperation) and cls is not nodes.ScriptOperation
             or name.endswith("Condition"))
    }


def test_every_parser_node_type_has_a_registry_entry():
    # A new parser node must be classified, even if only as planned.
    assert parser_node_types() - set(registry.REGISTRY) == set()
    assert {name for name, entry in registry.REGISTRY.items()
            if entry.kind == "condition"} >= {"ExistCondition", "ComparisonCondition"}


def test_statuses_and_handlers_agree():
    registry.lookup("ClickOperation")
    for entry in registry.REGISTRY.values():
        assert entry.status in registry.STATUSES
        assert (entry.handler is not None) == (entry.status in ("supported", "no_effect"))
    grouped = registry.capabilities()
    assert "ClickOperation" in [e["node_type"] for e in grouped["supported"]]
    assert "ReportEventOperation" in [e["node_type"] for e in grouped["supported"]]
    assert "CloseOperation" in [e["node_type"] for e in grouped["planned"]]


def test_second_handler_for_the_same_node_type_is_rejected():
    registry.lookup("ClickOperation")
    with pytest.raises(ValueError, match="Duplicate handler"):
        registry.maps("ClickOperation", uft=".Click", activities=("Click",))(lambda *a: None)


def test_planned_operation_blocks_with_its_source_line():
    root, report = ComponentEmitter("1", analyze_source('Browser("B").Close'), {}).generate()
    assert report["status"] == "blocked"
    assert report["trace"][0]["status"] == "blocked"
    assert any(issue["message"] == "CloseOperation has no validated semantic mapping; source preserved."
               for issue in report["issues"])


def test_unsupported_condition_blocks_the_if_only():
    source = 'If Check_File(Parameter("A")) Then\nWait 1\nEnd If'
    config = {"parameters": {"A": {"name": "in_A", "type": "String", "direction": "In"}}}
    root, report = ComponentEmitter("1", analyze_source(source), config).generate()
    by_line = {entry["line_number"]: entry for entry in report["trace"]}
    assert by_line[1]["status"] == "blocked"
    assert by_line[2]["status"] == "mapped_unverified"
    assert any(issue["code"] == "unresolved_condition" for issue in report["issues"])


@pytest.mark.parametrize("issue, category", [
    ({"code": "unsupported_statement", "message": "Unsupported UFT/VBScript statement"}, "parser"),
    ({"code": "unsupported_expression", "message": "Unsupported or malformed value expression"}, "expression"),
    ({"code": "unsupported_mapping", "message": "Expected String; no implicit conversion from Int32."}, "expression"),
    ({"code": "unresolved_condition", "message": "No exact object-identity binding."}, "binding"),
    ({"code": "unresolved_condition", "message": "Only an explicitly parsed Exist condition is supported."}, "condition"),
    ({"code": "unsupported_mapping", "message": "NavigateOperation has no validated semantic mapping; source preserved."}, "mapping"),
])
def test_blockers_are_categorised(issue, category):
    assert categorize(issue) == category


def test_inventory_counts_lines_reasons_calls_and_test_coverage():
    trace = [
        {"line_number": 1, "node_type": "ClickOperation", "status": "mapped_unverified"},
        {"line_number": 2, "node_type": "AssignOperation", "status": "blocked"},
        {"line_number": 3, "node_type": "ReportEventOperation", "status": "blocked"},
    ]
    issues = [
        {"code": "unsupported_expression", "line_number": 2, "message": "Unsupported or malformed value expression",
         "raw": 'Len(CStr(Environment.Value("X"))) + Browser("B").Page("P").WebEdit("E").GetROProperty("value")'},
        {"code": "unsupported_mapping", "line_number": 3,
         "message": "ReportEventOperation has no validated semantic mapping; source preserved."},
    ]
    report = {
        "project_name": "P",
        "workflows": {"a/Action1": {"trace": trace, "issues": issues}},
        "tests": [
            {"test_id": 1, "name": "T", "status": "blocked", "actions": ["a/Action1", "a/Action1"]},
            {"test_id": 2, "name": "Manual", "status": "not_automated", "actions": []},
        ],
    }
    inventory = build_inventory([report])
    assert inventory["lines"] == {"total": 3, "mapped": 1, "blocked": 2, "coverage": 0.333}
    assert inventory["operations"]["ClickOperation"] == {"mapped": 1}
    assert inventory["blocked_by"]["expression"]["lines"] == 1
    assert inventory["blocked_by"]["mapping"]["operations"] == {"ReportEventOperation": 1}
    assert inventory["unsupported_functions"] == {"Len": 1, "CStr": 1}
    assert inventory["unmapped_object_methods"] == {"Value": 1, "GetROProperty": 1}
    # An action called twice by a test counts once; manual tests are left out.
    assert inventory["tests"] == [{"project": "P", "test_id": 1, "name": "T", "status": "blocked",
                                   "operations": 3, "mapped": 1, "blocked": 2, "coverage": 0.333}]


def test_binding_that_is_not_accepted_is_a_binding_blocker():
    issue = {"code": "unsupported_mapping",
             "message": "Object binding must be accepted for generation, with a known "
                        "verification status (see mapping.selector_state)."}
    assert categorize(issue) == "binding"
