"""Operation inventory and migration coverage from generation reports.

Counts what the scripts actually contain and why lines are blocked, so the
next mappings can be chosen by how many lines they unblock. Coverage is read
from the per-line trace, not from the registry: a supported operation still
blocks when its object has no selector.

Coverage is reported three times, because one number would answer three
different questions at once:

    source     every action written once - how much of the migration work is
               done. An action no test uses still counts.
    execution  every action once per test step that runs it - how much of what
               actually runs is migrated. An action 40 tests share weighs 40x.
    functions  the Function/Sub workflows compiled from the scripts, each
               compiled workflow once.

Mapped never means verified: it means an activity or a deliberate no-op was
emitted for the line.
"""
from __future__ import annotations

import argparse
import json
import re
import textwrap
from collections import Counter, defaultdict
from pathlib import Path

from uft2uipath.mapping.operation_registry import capabilities

# Why a line is blocked. A line can have several reasons.
CATEGORIES = {
    "parser": "Statement or object chain not fully parsed",
    "expression": "Value expression unsupported (functions, operators, types)",
    "condition": "If condition other than a supported condition",
    "binding": "No accepted selector or argument binding",
    "library": "Calls a function from a function library or the action itself (not migrated yet)",
    "mapping": "Operation has no UiPath mapping yet",
    "other": "Other",
}
_BINDING = re.compile(
    r"object-identity binding|selector required|accepted for generation|timeout_ms required|"
    r"input_method required|browser_type required|actions require a full|"
    r"^Missing (\w+ )?binding|SetSecure needs"
)
_EXPRESSION = re.compile(
    r"Unsupported expression|no implicit conversion|is not assigned|Concatenation produces|"
    r"has no UiPath mapping|implicit conversion|rounds non-integer|needs an Int32|needs a number|"
    r"Value expression is missing|Exist requires|Wait requires|not a simple variable"
)
# Data accessors and test-object classes are not calls to translate.
_ACCESSORS = {"parameter", "environment", "datatable"}
_TEST_OBJECT = re.compile(r"(Web|Win|Uia|Swf|Java|Wpf|Sap|Vb|Acx|Ole|Te)[A-Z]|"
                          r"(Browser|Page|Frame|Dialog|Window|Link|Image|Static)$", re.IGNORECASE)
_CALL = re.compile(r"(\.?)\b([A-Za-z_]\w*)\s*\(")
_METHOD = re.compile(r"no validated mapping: (\w+)")
_FUNCTION = re.compile(r"^Function (\w+) (?:has no UiPath mapping|is defined in)")


def _calls(raw: str) -> tuple[set[str], set[str]]:
    """Functions and object methods called in an expression, e.g. Len and GetROProperty."""
    functions, methods = set(), set()
    for dot, name in _CALL.findall(raw):
        if name.casefold() in _ACCESSORS or _TEST_OBJECT.match(name):
            continue
        (methods if dot else functions).add(name)
    return functions, methods


def categorize(issue: dict) -> str:
    """Blocker category of one report issue (parser, expression, library, condition, binding, mapping)."""
    code, message = issue.get("code"), issue.get("message") or ""
    if code in ("unsupported_statement", "unsupported_object_chain"):
        return "parser"
    if "library functions are not migrated" in message or "is not fully migrated" in message:
        return "library"
    if code == "unsupported_expression" or _EXPRESSION.search(message):
        return "expression"
    if _BINDING.search(message) or code == "missing_binding":
        return "binding"
    if code == "unresolved_condition":
        return "condition"
    if "has no validated semantic mapping" in message:
        return "mapping"
    return "other"


def _counted(mapped: int, total: int, scope: str) -> dict:
    """One coverage block: what was counted, and how much of it is mapped."""
    return {"scope": scope, "total": total, "mapped": mapped, "blocked": total - mapped,
            "coverage": round(mapped / total, 3) if total else None}


def build_inventory(reports: list[dict]) -> dict:
    """Count lines, operations, blockers by category, unmapped functions and methods,
    source, execution-weighted and function coverage, over one or more generation reports.
    """
    operations: dict[str, Counter] = defaultdict(Counter)
    blocked_by: Counter = Counter()
    blocked_ops_by: dict[str, Counter] = defaultdict(Counter)
    functions: Counter = Counter()
    methods: Counter = Counter()
    source_total = source_mapped = 0
    run_total = run_mapped = steps_total = 0
    function_total = function_mapped = 0
    tests = []

    def count_workflow(workflow: dict) -> tuple[int, int]:
        """Count one workflow's lines by status and collect why they are blocked."""
        reasons: dict[int | None, set[str]] = defaultdict(set)
        for issue in workflow.get("issues", []):
            reasons[issue.get("line_number")].add(categorize(issue))
            if issue.get("code") == "unsupported_expression":
                called, invoked = _calls(issue.get("raw") or "")
                functions.update(called)
                methods.update(invoked)
            if match := _METHOD.search(issue.get("message") or ""):
                methods[match.group(1)] += 1
            if match := _FUNCTION.search(issue.get("message") or ""):
                functions[match.group(1)] += 1
        mapped = total = 0
        for entry in workflow.get("trace", []):
            kind, status = entry.get("node_type"), entry.get("status")
            total += 1
            if status == "blocked":
                operations[kind]["blocked"] += 1
                for category in reasons.get(entry.get("line_number")) or {"other"}:
                    blocked_by[category] += 1
                    blocked_ops_by[category][kind] += 1
            else:
                operations[kind]["mapped"] += 1
                mapped += 1
        return mapped, total

    for report in reports:
        action_lines: dict[str, tuple[int, int]] = {}
        for key, workflow in report.get("workflows", {}).items():
            mapped, total = count_workflow(workflow)
            action_lines[key] = (mapped, total)
            source_mapped += mapped
            source_total += total
        # Each compiled Function/Sub workflow is counted once, however many
        # actions call it; its lines are not part of any action's source.
        for workflow in (report.get("functions") or {}).values():
            mapped, total = count_workflow(workflow)
            function_mapped += mapped
            function_total += total
        for test in report.get("tests", []):
            if test.get("status") == "not_automated":
                continue
            steps = test.get("actions", [])
            steps_total += len(steps)
            # Execution weight: a step counts every time the test runs it.
            run_mapped += sum(action_lines.get(key, (0, 0))[0] for key in steps)
            run_total += sum(action_lines.get(key, (0, 0))[1] for key in steps)
            # The test's own numbers are the work left in it: each action once.
            keys = list(dict.fromkeys(steps))
            mapped = sum(action_lines.get(key, (0, 0))[0] for key in keys)
            total = sum(action_lines.get(key, (0, 0))[1] for key in keys)
            tests.append({
                "project": report.get("project_name"), "test_id": test.get("test_id"),
                "name": test.get("name"), "status": test.get("status"), "steps": len(steps),
                "operations": total, "mapped": mapped, "blocked": total - mapped,
                "coverage": round(mapped / total, 3) if total else None,
            })

    return {
        "format_version": 2,
        "definition": "Mapped means an activity or a deliberate no-op was emitted for the line, "
                      "not that it was verified in Studio or in a run. Operations and blockers "
                      "count action and function workflows together; coverage keeps them apart.",
        "coverage": {
            "source": _counted(source_mapped, source_total,
                               "Action source lines, each action counted once."),
            "execution": _counted(run_mapped, run_total,
                                  "Action source lines weighted by the test steps that run them; "
                                  f"{len(tests)} automated tests, {steps_total} steps."),
            "functions": _counted(function_mapped, function_total,
                                  "Source lines of the compiled Function/Sub workflows, each once."),
        },
        "operations": {kind: dict(counts) for kind, counts in
                       sorted(operations.items(), key=lambda item: -sum(item[1].values()))},
        "blocked_by": {category: {"description": CATEGORIES[category], "lines": count,
                                  "operations": dict(blocked_ops_by[category].most_common())}
                       for category, count in blocked_by.most_common()},
        "unsupported_functions": dict(functions.most_common()),
        "unmapped_object_methods": dict(methods.most_common()),
        "tests": tests,
        "registry": {status: [e["node_type"] for e in entries]
                     for status, entries in capabilities().items()},
    }


TITLES = {"source": "Source (each action once)", "execution": "Executed (weighted by test steps)",
          "functions": "Function workflows"}


def format_inventory(inventory: dict) -> str:
    """Human-readable summary of an inventory, as printed by `uft2uipath inventory`."""
    out = ["Coverage (lines / mapped / blocked):"]
    for name, block in inventory["coverage"].items():
        out.append(f"  {TITLES[name]:<34}{block['total']:>7}{block['mapped']:>8}{block['blocked']:>8}"
                   f"  {_percent(block['coverage'])}")
    out += [""] + textwrap.wrap(inventory["definition"], width=96, initial_indent="  ",
                                subsequent_indent="  ")
    out += [f"  {TITLES[name]}: {block['scope']}" for name, block in inventory["coverage"].items()]
    out += ["", "Operations (mapped / blocked):"]
    for kind, counts in inventory["operations"].items():
        out.append(f"  {kind:<32}{counts.get('mapped', 0):>6}{counts.get('blocked', 0):>8}")
    out += ["", "Blocked lines by reason (a line can have several):"]
    for category, entry in inventory["blocked_by"].items():
        out.append(f"  {category:<12}{entry['lines']:>6}  {entry['description']}")
    for title, key in (("Unsupported functions in expressions:", "unsupported_functions"),
                       ("Object methods without mapping:", "unmapped_object_methods")):
        if inventory[key]:
            out += ["", title, "  " + ", ".join(f"{name} {n}" for name, n in inventory[key].items())]
    out += ["", "Tests (steps / operations / mapped / blocked / coverage), each action once:"]
    for test in inventory["tests"]:
        out.append(f"  {test['test_id']:>6} {test['name'][:40]:<40}{test['steps']:>5}"
                   f"{test['operations']:>6}{test['mapped']:>7}{test['blocked']:>8}"
                   f"  {_percent(test['coverage'])}")
    out += ["", "Registry:"]
    for status, names in inventory["registry"].items():
        out.append(f"  {status:<18}{len(names):>3}  {', '.join(names)}")
    return "\n".join(out)


def _percent(value) -> str:
    """Coverage ratio as a percentage, or - when there is nothing to count."""
    return "-" if value is None else f"{value * 100:.1f}%"


def load_report(path: Path) -> dict:
    """Accepts a convert output directory, its project folder, or the report file."""
    for candidate in (path, path / "generation-report.json", path / "project" / "generation-report.json"):
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8-sig"))
    raise FileNotFoundError(f"No generation-report.json under {path}")


def main(argv=None):
    """Command line: inventory of one or more convert outputs, optionally written as JSON."""
    parser = argparse.ArgumentParser(description="Inventory UFT operations and migration coverage.")
    parser.add_argument("reports", nargs="+", help="convert output directories or generation-report.json files")
    parser.add_argument("--out", help="Also write the inventory as JSON")
    args = parser.parse_args(argv)
    try:
        inventory = build_inventory([load_report(Path(p)) for p in args.reports])
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.out:
        Path(args.out).write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    print(format_inventory(inventory))


if __name__ == "__main__":
    main()
