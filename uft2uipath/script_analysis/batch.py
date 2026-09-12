"""Analyze unique component scripts and link results to test instances by ID."""
import argparse
import codecs
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from uft2uipath.ast import ConversionStatus
from uft2uipath.parser.project_builder import ProjectBuilder
from uft2uipath.rows_cli import TABLES
from uft2uipath.script_analysis.analyzer import analyze_source

LIMITATIONS = [
    "Analysis only: no executable UiPath workflows are produced.",
    "Manifest mappings must be supplied from verified ALM relationships; names and ProjRep numbers are not guessed.",
    "Recognition coverage is not semantic equivalence or migration success.",
    "Source declarations, unsupported constructs and expressions remain preserved for review.",
    "Argument definitions, instance values, selectors and full UFT semantics are not resolved.",
    "Reference inventories cover parsed nodes; references inside unsupported expressions remain in raw source.",
]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def identity(value, location):
    if isinstance(value, bool):
        raise ValueError(f"{location}: invalid ID.")
    try:
        return int(str(value))
    except (ValueError, TypeError):
        raise ValueError(f"{location}: integer ID required, got {value!r}.") from None


def relative_path(root, value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}: non-empty path required.")
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_inputs(manifest_path):
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be an object.")
    rows_path = relative_path(manifest_path.parent, manifest.get("rows"), "rows").resolve()
    rows = read_json(rows_path)
    if not isinstance(rows, dict) or not isinstance(rows.get("project_name"), str) or not rows["project_name"].strip():
        raise ValueError("Rows require project_name.")
    for table in TABLES:
        if not isinstance(rows.get(table), list) or any(not isinstance(r, dict) for r in rows[table]):
            raise ValueError(f"{table}: list of row objects required.")
    for table, key in (("TEST", "TS_TEST_ID"), ("COMPONENT", "CO_ID")):
        seen = set()
        for row in rows[table]:
            number = identity(row.get(key), key)
            if number in seen:
                raise ValueError(f"{table}: duplicate ID {number}.")
            seen.add(number)
    bindings = manifest.get("bindings")
    if not isinstance(bindings, list):
        raise ValueError("Manifest requires bindings array.")
    by_id = {}
    known = {identity(r["CO_ID"], "CO_ID") for r in rows["COMPONENT"]}
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValueError("Each binding must be an object.")
        number = identity(binding.get("component_id"), "component_id")
        if number in by_id:
            raise ValueError(f"Duplicate binding for component {number}; mapping is ambiguous.")
        if number not in known:
            raise ValueError(f"Binding references unknown component {number}.")
        relative_path(manifest_path.parent, binding.get("script"), "script")
        encoding = binding.get("encoding", "auto")
        if not isinstance(encoding, str):
            raise ValueError("encoding must be a string.")
        if encoding != "auto":
            codecs.lookup(encoding)
        by_id[number] = binding
    return manifest, rows, rows_path, by_id


def relationship_issues(rows):
    tests = {identity(r["TS_TEST_ID"], "TS_TEST_ID") for r in rows["TEST"]}
    components = {identity(r["CO_ID"], "CO_ID") for r in rows["COMPONENT"]}
    issues = []
    for table, checks in (
        ("COMPONENT_STEP", (("CS_COMPONENT_ID", components),)),
        ("BPTEST_TO_COMPONENTS", (("BC_BPT_ID", tests), ("BC_CO_ID", components))),
    ):
        for index, row in enumerate(rows[table]):
            for key, allowed in checks:
                try:
                    number = identity(row.get(key), key)
                    if number not in allowed:
                        raise ValueError(f"{key}: missing referenced entity {number}.")
                except ValueError as exc:
                    issues.append({"code": "invalid_relationship", "table": table,
                                   "row_index": index, "message": str(exc), "raw": row})
            order = "CS_STEP_ORDER" if table == "COMPONENT_STEP" else "BC_ORDER"
            try:
                identity(row.get(order), order)
            except ValueError as exc:
                issues.append({"code": "unresolved_order", "table": table,
                               "row_index": index, "message": str(exc), "raw": row})
    return issues


def decode(data, encoding):
    if encoding == "auto":
        encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    return data.decode(encoding, errors="strict"), encoding


def run_batch(manifest_path, output):
    manifest_path, output = Path(manifest_path).resolve(), Path(output).resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Output already exists: {output}")
    manifest, rows, rows_path, bindings = load_inputs(manifest_path)
    global_issues = relationship_issues(rows)
    project = ProjectBuilder().build(
        project_name=rows["project_name"], test_rows=rows["TEST"],
        component_rows=rows["COMPONENT"], component_step_rows=rows["COMPONENT_STEP"],
        test_component_rows=rows["BPTEST_TO_COMPONENTS"], source_path=str(rows_path),
    )
    with tempfile.TemporaryDirectory(prefix="uft_script_analysis_") as temporary:
        stage = Path(temporary)
        (stage / "Sources").mkdir()
        (stage / "Components").mkdir()
        (stage / "Sources/manifest.json").write_bytes(manifest_path.read_bytes())
        (stage / "Sources/alm_rows.json").write_bytes(rows_path.read_bytes())
        results = {}
        for row in rows["COMPONENT"]:
            number = identity(row["CO_ID"], "CO_ID")
            binding = bindings.get(number)
            result = {
                "component_id": number, "name": row.get("CO_NAME"),
                "source_row": row, "binding": binding,
                "status": "missing_binding", "issues": [],
                "generation_ready": False, "executable_verified": False,
            }
            if binding is None:
                result["issues"] = [{"code": "missing_binding", "severity": "blocker",
                                     "message": "No explicit source mapping for this component."}]
            else:
                source = relative_path(manifest_path.parent, binding["script"], "script").resolve()
                result["source_path"] = str(source)
                try:
                    data = source.read_bytes()
                    source_copy = f"Sources/component_{number}.source"
                    (stage / source_copy).write_bytes(data)
                    result.update(source_copy=source_copy, sha256=hashlib.sha256(data).hexdigest())
                    text, encoding = decode(data, binding.get("encoding", "auto"))
                    result.update(source_text=text, encoding=encoding)
                    result.update(analyze_source(text))
                    result["status"] = "blocked" if result["issues"] else "analyzed"
                except Exception as exc:
                    result["status"] = "error"
                    result["issues"] = [{"code": "script_analysis_error", "severity": "blocker",
                                         "message": f"{type(exc).__name__}: {exc}"}]
            results[number] = result
            write_json(stage / f"Components/component_{number}.json", result)

        test_reports = []
        for test in project.tests:
            test.status = ConversionStatus.PARTIAL
            links = []
            for component in test.components:
                component.status = ConversionStatus.PARTIAL
                for step in component.steps:
                    step.status = ConversionStatus.UNSUPPORTED
                number = component.id
                component.raw["_script_analysis"] = f"Components/component_{number}.json"
                result = results[number]
                links.append({
                    "component_id": number,
                    "relation": component.raw.get("_bpt_relation"),
                    "analysis": component.raw["_script_analysis"],
                    "status": result["status"],
                    "blocker_count": len(result["issues"]),
                })
            blocked = bool(global_issues or not links or any(r["blocker_count"] for r in links))
            test_reports.append({
                "test_id": test.id, "name": test.name,
                "status": "blocked" if blocked else "analyzed",
                "component_instances": links,
                "generation_ready": False, "executable_verified": False,
            })

        counts = Counter(r["status"] for r in results.values())
        issue_counts = Counter(i["code"] for r in results.values() for i in r["issues"])
        summary = {
            "stage": "script_analysis",
            "unique_component_count": len(results),
            "analyzed_source_count": sum("operations" in r for r in results.values()),
            "test_count": len(test_reports),
            "component_instance_count": sum(len(t["component_instances"]) for t in test_reports),
            "component_statuses": dict(counts),
            "issue_counts": dict(issue_counts),
            "relationship_issue_count": len(global_issues),
            "has_blockers": bool(global_issues or not test_reports or any(
                r["issues"] for r in results.values()
            ) or any(t["status"] == "blocked" for t in test_reports)),
            "generation_ready": False, "executable_verified": False,
            "limitations": LIMITATIONS,
        }
        write_json(stage / "model.json", {
            "format_version": 1, "stage": "script_analysis",
            "project": asdict(project),
            "source_tables": {t: rows[t] for t in TABLES},
            "source_payload": rows,
            "source_manifest": manifest, "manifest_path": str(manifest_path),
            "component_analyses": {
                str(n): f"Components/component_{n}.json" for n in results
            },
            "generation_ready": False,
            "limitations": LIMITATIONS,
        })
        write_json(stage / "report.json", {
            "summary": summary, "relationship_issues": global_issues,
            "tests": test_reports,
            "components": [{k: r[k] for k in ("component_id", "name", "status", "issues")}
                           for r in results.values()],
        })
        (stage / "report.md").write_text(
            "# UFT script analysis\n\n"
            + f"Unique components: {len(results)}\n\nTests: {len(test_reports)}\n\n"
            + "## Limitations\n\n" + "\n".join("- " + s for s in LIMITATIONS)
            + "\n\n## Findings by code\n\n"
            + "\n".join(f"- {code}: {count}" for code, count in sorted(issue_counts.items()))
            + "\n\nDetailed component, test, source-line and relationship findings: report.json.\n",
            encoding="utf-8",
        )
        shutil.copytree(stage, output)
    return summary


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analyze scripts by verified component identity.")
    parser.add_argument("manifest")
    parser.add_argument("--out", required=True, help="New analysis directory")
    parser.add_argument("--fail-on-blockers", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = run_batch(args.manifest, args.out)
    except (OSError, ValueError, LookupError) as exc:
        parser.error(str(exc))
    print(f"Analysis saved: {args.out}")
    print(f"Unique components: {summary['unique_component_count']}; tests: {summary['test_count']}")
    print(f"Blockers: {summary['has_blockers']}; generation-ready: False")
    if args.fail_on_blockers and summary["has_blockers"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
