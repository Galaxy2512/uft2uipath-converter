"""Generate an importable workflow bundle for a Windows C# UiPath project."""
import argparse
import json
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from uft2uipath.script_generation.emitter import (
    ComponentEmitter, IDENTIFIER, TYPES, UI, X, document, expr, q, throw, write_xaml,
)

LIMITATIONS = [
    "Windows C# / Classic UI activity candidates; Studio load, compilation and execution are unverified.",
    "No project.json is invented. Import Workflows and Tests into an existing Windows C# UiPath project with UIAutomation and System activities.",
    "Mapped does not mean equivalent: validate live selectors, input methods, timeouts and application state.",
    "Click/Set use Attach Browser with explicit browser_type and partial selectors. Attachment adds its own timeout wait; timing equivalence remains unverified.",
    "Reporter.ReportEvent, ExitTest, SetSecure, declarations and other unsupported operations block before any UI action.",
    "Caller arguments are explicitly mapped per ALM relation ID; original dataset/value bindings still need verification.",
    "Generated test files are entry workflows, not registered Test Explorer test cases.",
]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def inside(root, reference):
    if not isinstance(reference, str):
        raise ValueError("Analysis reference must be a path string.")
    path = (root / reference).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Analysis reference escapes its directory.")
    return path


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def emit_test(test, components, call_bindings, global_issues):
    test_id = test["id"]
    issues = list(global_issues)
    arguments, invocations, seen_relations = {}, [], set()
    if not test.get("components"):
        issues.append({"message": "Test has no linked component instances."})
    for instance in test.get("components", []):
        number = str(instance["id"])
        component = components[number]
        relation = instance.get("raw", {}).get("_bpt_relation", {})
        relation_id = str(relation.get("BC_ID", ""))
        if not relation_id or relation_id in seen_relations:
            issues.append({"message": "Missing or duplicate relation ID."})
        seen_relations.add(relation_id)
        mapping = call_bindings.get(relation_id, {})
        if not isinstance(mapping, dict):
            issues.append({"message": f"Relation {relation_id}: binding must be an object."})
            mapping = {}
        if component["status"] == "blocked":
            issues.append({"message": f"Component {number} is blocked."})
        invoke = ET.Element(q("InvokeWorkflowFile", UI), {
            "DisplayName": f"ALM relation {relation_id}: component {number}",
            "WorkflowFileName": f"Workflows\\Component_{number}.xaml",
        })
        args = ET.SubElement(invoke, q("InvokeWorkflowFile.Arguments", UI))
        for target_arg, kind in component["arguments"].items():
            binding = mapping.get(target_arg)
            if not isinstance(binding, dict):
                issues.append({"message": f"Relation {relation_id}: missing call binding for {target_arg}."})
                continue
            caller = binding.get("argument")
            if (
                not isinstance(caller, str) or not IDENTIFIER.fullmatch(caller)
                or binding.get("type") != kind
                or (caller in arguments and arguments[caller] != kind)
            ):
                issues.append({"message": f"Relation {relation_id}: invalid caller binding for {target_arg}."})
                continue
            arguments[caller] = kind
            ET.SubElement(args, q("InArgument"), {
                q("TypeArguments", X): TYPES[kind], q("Key", X): target_arg,
            }).text = expr(caller)
        if set(mapping) - set(component["arguments"]):
            issues.append({"message": f"Relation {relation_id}: unknown target arguments in call mapping."})
        if not len(args):
            invoke.remove(args)
        invocations.append(invoke)
    if set(call_bindings) - seen_relations:
        issues.append({"message": "Call mappings reference unknown relation IDs in this test."})
    root, seq = document(f"Test_{test_id}", arguments)
    if issues:
        seq.append(throw(f"Test {test_id}: incomplete migration or call bindings. Read generation-report.json."))
    seq.extend(invocations)
    return root, {
        "test_id": test_id, "status": "blocked" if issues else "mapped_unverified",
        "arguments": arguments, "issues": issues,
        "executable_verified": False, "equivalent_verified": False,
    }


def emit_bundle(analysis_dir, bindings_path, output):
    analysis_dir, output = Path(analysis_dir).resolve(), Path(output).resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Output already exists: {output}")
    model = read(analysis_dir / "model.json")
    source_report = read(analysis_dir / "report.json")
    bindings = read(Path(bindings_path))
    if model.get("stage") != "script_analysis":
        raise ValueError("Expected analyze-scripts output.")
    if bindings.get("profile") != "windows-csharp-classic":
        raise ValueError("Explicit profile windows-csharp-classic required.")
    definitions, calls = bindings.get("components", {}), bindings.get("calls", {})
    if not isinstance(definitions, dict) or not isinstance(calls, dict):
        raise ValueError("components and calls must be objects.")
    analyses = model["component_analyses"]
    if set(definitions) - set(analyses):
        raise ValueError("Target bindings reference unknown component IDs.")
    tests = model["project"]["tests"]
    test_ids = {str(test["id"]) for test in tests}
    if set(calls) - test_ids:
        raise ValueError("Call bindings reference unknown test IDs.")
    for number in [*analyses, *test_ids]:
        if not str(number).isdigit():
            raise ValueError("Non-negative numeric ALM IDs required for XAML class names.")
    component_reports, test_reports = {}, []
    with tempfile.TemporaryDirectory(prefix="uft_emit_") as temporary:
        stage = Path(temporary)
        (stage / "Workflows").mkdir()
        (stage / "Tests").mkdir()
        for number, reference in analyses.items():
            analysis = read(inside(analysis_dir, reference))
            if str(analysis.get("component_id")) != number:
                raise ValueError("Component analysis identity mismatch.")
            try:
                emitter = ComponentEmitter(number, analysis, definitions.get(number, {}))
                root, report = emitter.generate()
                if bindings.get("fixture_only") is True:
                    seq = root.find(q("Sequence"))
                    index = 1 if len(seq) and seq[0].tag == q("Sequence.Variables") else 0
                    seq.insert(index, throw("Synthetic fixture bindings: do not execute against a live application."))
                    report["issues"].append({"code": "fixture_only", "message": "Synthetic example selectors, not live verification."})
                    report["status"] = "blocked"
            except (ValueError, TypeError, KeyError, ET.ParseError) as exc:
                root, seq = document(f"Component_{number}", {})
                seq.append(throw(f"Component {number}: invalid mapping configuration."))
                report = {
                    "component_id": number, "status": "blocked", "arguments": {},
                    "issues": [{"message": str(exc), "code": "invalid_configuration"}],
                    "trace": [], "executable_verified": False, "equivalent_verified": False,
                }
            write_xaml(stage / f"Workflows/Component_{number}.xaml", root)
            component_reports[number] = report
        global_issues = source_report.get("relationship_issues", [])
        for test in tests:
            mapping = calls.get(str(test["id"]), {})
            if not isinstance(mapping, dict):
                raise ValueError("Per-test call bindings must be an object.")
            root, report = emit_test(test, component_reports, mapping, global_issues)
            write_xaml(stage / f"Tests/Test_{test['id']}.xaml", root)
            test_reports.append(report)
        report = {
            "stage": "workflow_candidates",
            "component_count": len(component_reports),
            "test_count": len(test_reports),
            "blocked_component_count": sum(r["status"] == "blocked" for r in component_reports.values()),
            "blocked_test_count": sum(r["status"] == "blocked" for r in test_reports),
            "components": component_reports, "tests": test_reports,
            "executable_verified": False, "equivalent_verified": False,
            "limitations": LIMITATIONS,
        }
        write_json(stage / "generation-report.json", report)
        write_json(stage / "target-bindings.json", bindings)
        shutil.copytree(analysis_dir, stage / "Data/Analysis")
        (stage / "README.md").write_text(
            "# Generated workflow candidates\n\n" + "\n".join("- " + s for s in LIMITATIONS)
            + "\n\nSee generation-report.json for source lines, mapping decisions and blockers.\n",
            encoding="utf-8",
        )
        shutil.copytree(stage, output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Emit guarded workflow candidates from script analysis.")
    parser.add_argument("analysis")
    parser.add_argument("--bindings", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        report = emit_bundle(args.analysis, args.bindings, args.out)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(f"Workflow bundle: {args.out}")
    print(f"Components: {report['component_count']}; tests: {report['test_count']}")
    print(f"Blocked components: {report['blocked_component_count']}; blocked tests: {report['blocked_test_count']}")
    print("Studio execution and equivalence: unverified.")


if __name__ == "__main__":
    main()
