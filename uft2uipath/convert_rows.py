"""Generate a review scaffold from decoded ALM rows, not a runnable test."""
import argparse
import json
import re
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from uft2uipath.generator.project_generator import UiPathProjectGenerator
from uft2uipath.rows_cli import build_model


def check_name(name):
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved.update(f"{prefix}{n}" for prefix in ("COM", "LPT") for n in "123456789¹²³")
    if (
        not isinstance(name, str) or not name.strip()
        or name in {".", ".."} or name.endswith((" ", "."))
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
        or name.split(".")[0].upper() in reserved
        or len(name) > 100
    ):
        raise ValueError(f"Invalid Windows file name: {name!r}")


def integer(row, key):
    try:
        return int(str(row[key]))
    except (KeyError, ValueError, TypeError):
        raise ValueError(f"Missing or invalid integer {key}: {row.get(key)!r}") from None


def validate_tables(tables):
    identifiers = {}
    for table, key in (("TEST", "TS_TEST_ID"), ("COMPONENT", "CO_ID")):
        values = [integer(row, key) for row in tables[table]]
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate IDs in {table}.")
        identifiers[table] = set(values)
    if not identifiers["TEST"]:
        raise ValueError("At least one test is required.")

    for row in tables["COMPONENT"]:
        check_name(row.get("CO_NAME"))
    for row in tables["COMPONENT_STEP"]:
        if integer(row, "CS_COMPONENT_ID") not in identifiers["COMPONENT"]:
            raise ValueError("Step references a missing component.")
        integer(row, "CS_STEP_ORDER")
    for row in tables["BPTEST_TO_COMPONENTS"]:
        if integer(row, "BC_BPT_ID") not in identifiers["TEST"]:
            raise ValueError("Relation references a missing test.")
        if integer(row, "BC_CO_ID") not in identifiers["COMPONENT"]:
            raise ValueError("Relation references a missing component.")
        integer(row, "BC_ORDER")

    names = [row["CO_NAME"].casefold() for row in tables["COMPONENT"]]
    if len(names) != len(set(names)):
        raise ValueError("Component names collide on Windows.")


def convert_rows(source, output_dir):
    source = Path(source).resolve()
    with tempfile.TemporaryDirectory(prefix="uft2uipath_convert_") as temporary:
        staging = Path(temporary)
        model_file = staging / "model.json"
        project = build_model(source, model_file)
        snapshot = json.loads(model_file.read_text(encoding="utf-8"))
        check_name(project.name)
        validate_tables(snapshot["source_tables"])
        target = Path(output_dir).resolve() / project.name
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Output already exists: {target}")

        issues = [
            "Review scaffold only: Studio compatibility and execution are unverified.",
            "PTD decoding, VBScript conversion, selectors and arguments are not connected.",
            "Main.xaml invokes components across all tests; independent test cases are not generated.",
            "ALM descriptive steps are not executable UFT code; generated steps are TODOs.",
            "Unreferenced component definitions remain in source_tables, without workflows.",
        ]
        # Make the model status agree with what is actually generated.
        from uft2uipath.ast import ConversionStatus
        for test in project.tests:
            test.status = ConversionStatus.PARTIAL
            for component in test.components:
                component.status = ConversionStatus.PARTIAL
                for step in component.steps:
                    step.status = ConversionStatus.UNSUPPORTED

        generated = UiPathProjectGenerator().generate(project, staging / "generated")
        data = generated / "Data"
        reports = generated / "Reports"
        data.mkdir()
        reports.mkdir()
        snapshot.update(
            stage="review_scaffold",
            project=asdict(project),
            notes=issues,
        )
        (data / "migration_model.json").write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        report = {
            "status": "requires_manual_work",
            "executable_verified": False,
            "test_count": len(project.tests),
            "workflow_count": len(list((generated / "Workflows").glob("*.xaml"))),
            "component_instance_count": sum(len(t.components) for t in project.tests),
            "todo_step_instance_count": sum(
                len(c.steps) for t in project.tests for c in t.components
            ),
            "limitations": issues,
        }
        (reports / "ConversionReport.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        (reports / "ConversionReport.md").write_text(
            "# Conversion report\n\nStatus: requires manual work\n\n"
            + "\n".join("- " + issue for issue in issues) + "\n",
            encoding="utf-8",
        )
        # copytree refuses an existing destination instead of merging into it.
        shutil.copytree(generated, target)
        return target


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate a review scaffold from ALM JSON.")
    parser.add_argument("source")
    parser.add_argument("--out", required=True, help="Parent output directory")
    args = parser.parse_args(argv)
    try:
        output = convert_rows(args.source, args.out)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Generated review scaffold: {output}")
    print("Read Reports/ConversionReport.md before opening in Studio.")


if __name__ == "__main__":
    main()
