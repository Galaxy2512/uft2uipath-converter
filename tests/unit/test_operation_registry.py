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
from uft2uipath.script_generation import handlers
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


def test_every_promised_handler_exists_and_no_other():
    # The registry promises a handler for supported/no_effect entries only; the
    # handler table must deliver exactly those, and nothing it invented itself.
    handlers.load_emitters()
    promised = {name for name, entry in registry.REGISTRY.items() if entry.status in registry.EMITTED}
    assert set(handlers.HANDLERS) == promised
    grouped = registry.capabilities()
    assert "ClickOperation" in [e["node_type"] for e in grouped["supported"]]
    assert "ReportEventOperation" in [e["node_type"] for e in grouped["supported"]]
    assert "CloseOperation" in [e["node_type"] for e in grouped["planned"]]


def test_second_handler_for_the_same_node_type_is_rejected():
    handlers.load_emitters()
    with pytest.raises(ValueError, match="Duplicate handler"):
        handlers.emits("ClickOperation")(lambda *a: None)


def test_a_handler_needs_an_entry_that_promises_it():
    with pytest.raises(ValueError, match="no entry in mapping.operation_registry"):
        handlers.emits("InventedOperation")(lambda *a: None)
    with pytest.raises(ValueError, match="planned"):
        handlers.emits("CloseOperation")(lambda *a: None)


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
        "workflows": {"a/Action1": {"trace": trace, "issues": issues},
                      "a/Unused": {"trace": [{"line_number": 1, "node_type": "WaitOperation",
                                              "status": "mapped_unverified"}], "issues": []}},
        "functions": {"Functions\\Login.xaml": {
            "trace": [{"line_number": 1, "node_type": "ClickOperation", "status": "mapped_unverified"}],
            "issues": []}},
        "tests": [
            {"test_id": 1, "name": "T", "status": "blocked", "actions": ["a/Action1", "a/Action1"]},
            {"test_id": 2, "name": "Manual", "status": "not_automated", "actions": []},
        ],
    }
    inventory = build_inventory([report])
    coverage = inventory["coverage"]
    # Source: every action written once, including the one no test runs.
    assert [coverage["source"][key] for key in ("total", "mapped", "blocked", "coverage")] \
        == [4, 2, 2, 0.5]
    # Execution: the test runs Action1 twice, so its lines weigh twice; Unused never runs.
    assert [coverage["execution"][key] for key in ("total", "mapped", "coverage")] == [6, 2, 0.333]
    assert "2 steps" in coverage["execution"]["scope"]
    # Compiled Function/Sub workflows are counted apart from the actions.
    assert [coverage["functions"][key] for key in ("total", "mapped")] == [1, 1]
    assert inventory["operations"]["ClickOperation"] == {"mapped": 2}
    assert inventory["blocked_by"]["expression"]["lines"] == 1
    assert inventory["blocked_by"]["mapping"]["operations"] == {"ReportEventOperation": 1}
    # Names called in blocked lines carry what the registries know about them, and
    # the ones that are already translated sort last: they are not missing work.
    called = inventory["blocked_calls"]["functions"]
    assert list(called) == ["Len", "CStr"] or list(called) == ["CStr", "Len"]
    assert all(fact["status"] == "supported" and fact["source"] == "vbscript_builtin"
               for fact in called.values())
    methods = inventory["blocked_calls"]["object_methods"]
    assert methods["GetROProperty"]["node_type"] == "ObjectPropertyReference"
    assert methods["Value"]["owner"] == "UFT data accessor"
    # A test's own numbers are the work left in it: each action once, whatever
    # its step count. Manual tests are left out of every count.
    assert inventory["tests"] == [{"project": "P", "test_id": 1, "name": "T", "status": "blocked",
                                   "steps": 2, "operations": 3, "mapped": 1, "blocked": 2,
                                   "coverage": 0.333}]


def test_binding_that_is_not_accepted_is_a_binding_blocker():
    issue = {"code": "unsupported_mapping",
             "message": "Object binding must be accepted for generation, with a known "
                        "verification status (see contracts.selector_state)."}
    assert categorize(issue) == "binding"
