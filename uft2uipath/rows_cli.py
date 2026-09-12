import argparse
import json
from dataclasses import asdict
from pathlib import Path

from uft2uipath.parser.project_builder import ProjectBuilder


TABLES = ("TEST", "COMPONENT", "COMPONENT_STEP", "BPTEST_TO_COMPONENTS")


def build_model(source, output):
    source, output = Path(source), Path(output)
    payload = json.loads(source.read_text(encoding="utf-8-sig"))

    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object.")

    name = payload.get("project_name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("project_name must be a non-empty string.")

    for table in TABLES:
        rows = payload.get(table)
        if not isinstance(rows, list) or any(
            not isinstance(row, dict) for row in rows
        ):
            raise ValueError(f"{table} must be a list of row objects.")

    project = ProjectBuilder().build(
        project_name=name,
        test_rows=payload["TEST"],
        component_rows=payload["COMPONENT"],
        component_step_rows=payload["COMPONENT_STEP"],
        test_component_rows=payload["BPTEST_TO_COMPONENTS"],
        source_path=str(source),
    )

    result = {
        "format_version": 1,
        "stage": "decoded_rows_to_model",
        "notes": [
            "Model export only; no UiPath workflows generated.",
            "ALM relationship integrity is not yet fully validated.",
            "All input rows are retained in source_tables for review.",
        ],
        "project": asdict(project),
        "source_tables": {table: payload[table] for table in TABLES},
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)

    return project


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a model from decoded ALM rows."
    )
    parser.add_argument("source")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    try:
        project = build_model(args.source, args.out)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"Model saved: {args.out}")
    print(f"Tests: {len(project.tests)}")


if __name__ == "__main__":
    main()
