"""Operation inventory and migration coverage from generation reports.

Counts what the scripts actually contain and why lines are blocked, so the
next mappings can be chosen by how many lines they unblock. Coverage is read
from the per-line trace, not from the registry: a supported operation still
blocks when its object has no selector.
"""
from __future__ import annotations

import argparse
import json
import re
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


def build_inventory(reports: list[dict]) -> dict:
    """Count lines, operations, blockers by category, unmapped functions and methods,
    and coverage per test, over one or more generation reports.
    """
    operations: dict[str, Counter] = defaultdict(Counter)
    blocked_by: Counter = Counter()
    blocked_ops_by: dict[str, Counter] = defaultdict(Counter)
    functions: Counter = Counter()
    methods: Counter = Counter()
    lines_total = lines_mapped = 0
    tests = []

    for report in reports:
        action_lines: dict[str, tuple[int, int]] = {}
        for key, workflow in report.get("workflows", {}).items():
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
            action_lines[key] = (mapped, total)
            lines_mapped += mapped
            lines_total += total
        for test in report.get("tests", []):
            if test.get("status") == "not_automated":
                continue
            # Each action counts once per test, however often the test calls it.
            keys = list(dict.fromkeys(test.get("actions", [])))
            mapped = sum(action_lines.get(key, (0, 0))[0] for key in keys)
            total = sum(action_lines.get(key, (0, 0))[1] for key in keys)
            tests.append({
                "project": report.get("project_name"), "test_id": test.get("test_id"),
                "name": test.get("name"), "status": test.get("status"),
                "operations": total, "mapped": mapped, "blocked": total - mapped,
                "coverage": round(mapped / total, 3) if total else None,
            })

    return {
        "format_version": 1,
        "definition": "Source lines of executed actions; mapped means an activity or a deliberate "
                      "no-op was emitted, not that it was verified in Studio.",
        "lines": {"total": lines_total, "mapped": lines_mapped, "blocked": lines_total - lines_mapped,
                  "coverage": round(lines_mapped / lines_total, 3) if lines_total else None},
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


def format_inventory(inventory: dict) -> str:
    """Human-readable summary of an inventory, as printed by `uft2uipath inventory`."""
    lines = inventory["lines"]
    out = [f"Lines: {lines['total']}  mapped: {lines['mapped']}  blocked: {lines['blocked']}  "
           f"coverage: {_percent(lines['coverage'])}", "", "Operations (mapped / blocked):"]
    for kind, counts in inventory["operations"].items():
        out.append(f"  {kind:<32}{counts.get('mapped', 0):>6}{counts.get('blocked', 0):>8}")
    out += ["", "Blocked lines by reason (a line can have several):"]
    for category, entry in inventory["blocked_by"].items():
        out.append(f"  {category:<12}{entry['lines']:>6}  {entry['description']}")
    for title, key in (("Unsupported functions in expressions:", "unsupported_functions"),
                       ("Object methods without mapping:", "unmapped_object_methods")):
        if inventory[key]:
            out += ["", title, "  " + ", ".join(f"{name} {n}" for name, n in inventory[key].items())]
    out += ["", "Tests (operations / mapped / blocked / coverage):"]
    for test in inventory["tests"]:
        out.append(f"  {test['test_id']:>6} {test['name'][:40]:<40}{test['operations']:>6}"
                   f"{test['mapped']:>7}{test['blocked']:>8}  {_percent(test['coverage'])}")
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
