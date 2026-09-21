"""Emits a UiPath test project from resolved actions and accepted bindings.

One workflow per UFT action, one test case per ALM test invoking those
workflows in execution order. Main.xaml does not call the test cases: they
are registered in project.json and run from the Test Explorer.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from uft2uipath.script_generation.emitter import (
    DIRECTIONS, EXIT_FAILED_SUFFIX, EXIT_TEST_MARKER, FAILED_FLAG, ComponentEmitter, TYPES, UI, X,
    assign, document, expr, literal, q, throw, write_xaml,
)
from uft2uipath.script_generation.project import project_metadata

_INVALID = re.compile(r"[^A-Za-z0-9_]")
# Test variable that collects the failure flag of every step.
TEST_FAILED = "uft_failed"


@dataclass
class ActionPlan:
    key: str
    workflow: str
    analysis: dict[str, Any]
    binding: dict[str, Any]


@dataclass
class TestPlan:
    test_id: int
    name: str
    status: str
    units: list[dict[str, Any]]
    issues: list[dict[str, Any]] = field(default_factory=list)


def workflow_name(key: str) -> str:
    return "Action_" + _INVALID.sub("_", key).strip("_")


def generate(output: Path, project_name: str, actions: dict[str, ActionPlan],
             tests: list[TestPlan], template: str | None = None) -> dict[str, Any]:
    (output / "Workflows").mkdir(parents=True)
    (output / "Tests").mkdir()

    workflows: dict[str, dict[str, Any]] = {}
    for key, plan in sorted(actions.items()):
        emitter = ComponentEmitter(key, plan.analysis, plan.binding, workflow_name=plan.workflow)
        root, report = emitter.generate()
        write_xaml(output / "Workflows" / f"{plan.workflow}.xaml", root)
        report["action"] = key
        report["workflow"] = f"Workflows\\{plan.workflow}.xaml"
        workflows[key] = report

    test_reports = []
    for test in tests:
        root, report = _emit_test(test, workflows)
        write_xaml(output / "Tests" / f"Test_{test.test_id}.xaml", root)
        test_reports.append(report)

    registered = [report for report in test_reports if report["status"] != "not_automated"]
    metadata = project_metadata(project_name, registered, template)
    (output / "project.json").write_text(_json(metadata), encoding="utf-8")
    write_xaml(output / "Main.xaml", _main())
    return {"workflows": workflows, "tests": test_reports,
            "registered_test_count": len(registered)}


def _emit_test(test: TestPlan, workflows: dict[str, dict[str, Any]]):
    issues = list(test.issues)
    arguments: dict[str, str] = {}
    directions: dict[str, str] = {}
    invocations = []
    reports_failures = exits_test = False
    for unit in test.units:
        key = f"{unit['asset']}/{unit['action']}"
        workflow = workflows.get(key)
        if workflow is None:
            issues.append({"code": "missing_workflow", "message": f"No workflow generated for {key}."})
            continue
        if workflow["status"] == "blocked":
            issues.append({"code": "blocked_action", "message": f"{key} is blocked."})
        exits_test |= bool(workflow.get("exits_test"))
        invoke = ET.Element(q("InvokeWorkflowFile", UI), {
            "DisplayName": f"Step {unit['order']}: {unit.get('action_name') or unit['action']}",
            "WorkflowFileName": workflow["workflow"],
        })
        mapped = ET.SubElement(invoke, q("InvokeWorkflowFile.Arguments", UI))
        for name, kind in sorted(workflow["arguments"].items()):
            direction = workflow.get("argument_directions", {}).get(name, "In")
            if name == FAILED_FLAG:
                # One flag for the whole test: any step's reported failure fails it.
                caller, reports_failures = TEST_FAILED, True
            else:
                caller = f"{name}_{unit['order']}"
                arguments[caller] = kind
                if direction != "In":
                    directions[caller] = direction
            ET.SubElement(mapped, q(DIRECTIONS[direction]), {
                q("TypeArguments", X): TYPES[kind], q("Key", X): name,
            }).text = expr(caller)
        if not len(mapped):
            invoke.remove(mapped)
        invocations.append(invoke)

    root, sequence = document(f"Test_{test.test_id}", arguments, directions)
    status = test.status if test.status != "resolved" else ("blocked" if issues else "mapped_unverified")
    if reports_failures:
        variables = ET.SubElement(sequence, q("Sequence.Variables"))
        ET.SubElement(variables, q("Variable"), {q("TypeArguments", X): "x:Boolean", "Name": TEST_FAILED})
    if issues and test.status != "not_automated":
        sequence.append(throw(f"Test {test.test_id}: incomplete migration. Read generation-report.json."))
    sequence.extend([_until_exit_test(invocations)] if exits_test else invocations)
    if reports_failures:
        check = ET.SubElement(sequence, q("If"), {
            "DisplayName": "Fail the test if a step reported a failure", "Condition": expr(TEST_FAILED),
        })
        then = ET.SubElement(check, q("If.Then"))
        then.append(throw(f"Test {test.test_id}: a step reported a failure (Reporter micFail). See the log.",
                          display="Reported failure", exception="System.Exception"))
    report = {
        "test_id": test.test_id, "name": test.name, "status": status,
        "arguments": arguments, "issues": issues,
        "step_count": len(invocations),
        "actions": [f"{unit['asset']}/{unit['action']}" for unit in test.units],
        "executable_verified": False, "equivalent_verified": False,
    }
    if directions:
        report["argument_directions"] = directions
    return root, report


def _until_exit_test(invocations):
    """Run the steps; an ExitTest ends them without failing, other exceptions still fail."""
    trycatch = ET.Element(q("TryCatch"), {"DisplayName": "Steps (ExitTest stops here)"})
    body = ET.SubElement(ET.SubElement(trycatch, q("TryCatch.Try")), q("Sequence"),
                         {"DisplayName": "Steps"})
    body.extend(invocations)
    catch = ET.SubElement(ET.SubElement(trycatch, q("TryCatch.Catches")), q("Catch"),
                          {q("TypeArguments", X): "s:ApplicationException"})
    action = ET.SubElement(catch, q("ActivityAction"), {q("TypeArguments", X): "s:ApplicationException"})
    argument = ET.SubElement(action, q("ActivityAction.Argument"))
    ET.SubElement(argument, q("DelegateInArgument"), {
        q("TypeArguments", X): "s:ApplicationException", "Name": "exitTest",
    })
    other = ET.SubElement(action, q("If"), {
        "DisplayName": "Not an ExitTest: fail",
        "Condition": expr(f"!exitTest.Message.StartsWith({literal(EXIT_TEST_MARKER)}, "
                          "StringComparison.Ordinal)"),
    })
    ET.SubElement(ET.SubElement(other, q("If.Then")), q("Rethrow"))
    # The exiting step cannot return its flag; its message carries it.
    assign(ET.SubElement(other, q("If.Else")), "Keep a failure reported before ExitTest",
           TEST_FAILED, "Boolean",
           f"{TEST_FAILED} || exitTest.Message.EndsWith({literal(EXIT_FAILED_SUFFIX)}, "
           "StringComparison.Ordinal)")
    return trycatch


def _main():
    root, sequence = document("Main", {})
    ET.SubElement(sequence, q("LogMessage", UI), {
        "DisplayName": "Migration entry point", "Level": "Info",
        "Message": expr('"Generated test cases run from the Test Explorer, not from Main."'),
    })
    return root


def _json(value) -> str:
    import json
    return json.dumps(value, indent=2, ensure_ascii=False)
