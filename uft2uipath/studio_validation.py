"""Static validation for generated UiPath Studio test projects.

Passing this validator proves only the generated project structure. It does not
claim that UiPath Studio loaded the project, restored dependencies, compiled or
executed it, or that behaviour is equivalent to UFT.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from uft2uipath.script_generation.emitter import UI, X, q
from uft2uipath.script_generation.project import DEPENDENCIES


def validate_project(project_dir: str | Path) -> dict[str, Any]:
    """Check a generated project's structure: project.json, registered tests,
    XAML well-formedness, workflow references and Main not invoking tests.
    """
    root = Path(project_dir)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checked_files: list[str] = []

    def error(code: str, message: str, path: str | None = None) -> None:
        """Record a validation error."""
        entry: dict[str, Any] = {"code": code, "message": message}
        if path:
            entry["path"] = path
        errors.append(entry)

    project_file = root / "project.json"
    if not project_file.is_file():
        error("missing_project_json", "project.json is missing.", "project.json")
        return _report(errors, warnings, checked_files)

    try:
        metadata = json.loads(project_file.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        error("invalid_project_json", str(exc), "project.json")
        return _report(errors, warnings, checked_files)

    checked_files.append("project.json")

    if metadata.get("targetFramework") != "Windows":
        error("unsupported_target_framework", "Generated project must target Windows.", "project.json")
    if metadata.get("expressionLanguage") != "CSharp":
        error("unsupported_expression_language", "Generated project must use CSharp.", "project.json")
    if metadata.get("designOptions", {}).get("outputType") != "Tests":
        error("invalid_output_type", "Generated project must use outputType=Tests.", "project.json")

    dependencies = metadata.get("dependencies")
    if not isinstance(dependencies, dict):
        error("missing_dependencies", "project.json has no dependencies object.", "project.json")
    else:
        for package in DEPENDENCIES:
            if package not in dependencies:
                error("missing_dependency", f"Required package is missing: {package}.", "project.json")

    main = metadata.get("main")
    if not isinstance(main, str) or not main:
        error("missing_main", "project.json does not declare a main workflow.", "project.json")
    elif not (root / _relative(main)).is_file():
        error("missing_main_file", f"Main workflow does not exist: {main}.", main)

    registered = metadata.get("designOptions", {}).get("fileInfoCollection", [])
    if not isinstance(registered, list):
        error("invalid_test_registration", "fileInfoCollection must be an array.", "project.json")
        registered = []

    for entry in registered:
        if not isinstance(entry, dict):
            error("invalid_test_registration", "Test registration entry must be an object.", "project.json")
            continue
        file_name = entry.get("fileName")
        if entry.get("testCaseType") != "TestCase":
            error("invalid_test_case_type", f"Registered file is not TestCase: {file_name!r}.", "project.json")
        if not isinstance(file_name, str) or not file_name:
            error("missing_test_file_name", "Registered test has no fileName.", "project.json")
            continue
        if not (root / _relative(file_name)).is_file():
            error("missing_registered_test", f"Registered test does not exist: {file_name}.", file_name)

    xaml_files = sorted(root.rglob("*.xaml"))
    if not xaml_files:
        error("no_xaml", "Generated project contains no XAML workflows.")

    for path in xaml_files:
        relative = path.relative_to(root).as_posix()
        checked_files.append(relative)
        try:
            document = ET.parse(path)
        except ET.ParseError as exc:
            error("invalid_xaml_xml", str(exc), relative)
            continue

        activity = document.getroot()
        if activity.tag != q("Activity"):
            error("invalid_xaml_root", "XAML root must be Activity.", relative)

        for members in activity.findall(".//" + q("Members", X)):
            if len(members) == 0:
                error("empty_members", "Empty x:Members is rejected by Studio.", relative)

        for arguments in activity.findall(".//" + q("InvokeWorkflowFile.Arguments", UI)):
            if len(arguments) == 0:
                error("empty_invoke_arguments", "Empty InvokeWorkflowFile.Arguments should be omitted.", relative)

        for invoke in activity.findall(".//" + q("InvokeWorkflowFile", UI)):
            target_name = invoke.attrib.get("WorkflowFileName")
            if not target_name:
                error("missing_workflow_reference", "Invoke Workflow File has no WorkflowFileName.", relative)
                continue
            if not (root / _relative(target_name)).is_file():
                error("broken_workflow_reference",
                      f"Referenced workflow does not exist: {target_name}.", relative)

    if isinstance(main, str) and main:
        main_path = root / _relative(main)
        if main_path.is_file():
            try:
                main_root = ET.parse(main_path)
                for invoke in main_root.findall(".//" + q("InvokeWorkflowFile", UI)):
                    name = invoke.attrib.get("WorkflowFileName", "").replace("/", "\\")
                    if name.casefold().startswith("tests\\"):
                        error("main_invokes_test_case",
                              "Main.xaml must not invoke registered private test cases.", main_path.name)
            except ET.ParseError:
                pass

    return _report(errors, warnings, checked_files)


def _relative(value: str) -> Path:
    """Path of a project-relative file name, whether written with forward or back slashes."""
    return Path(*value.replace("/", "\\").split("\\"))


def _report(errors, warnings, checked_files):
    """Validation result; Studio load and execution always stay unverified here."""
    return {
        "format_version": 1,
        "validation_level": "static",
        "static_validation_passed": not errors,
        "studio_load_verified": False,
        "executable_verified": False,
        "errors": errors,
        "warnings": warnings,
        "checked_files": checked_files,
        "note": (
            "Passing static validation proves generated project structure only. "
            "UiPath Studio load, dependency restore, Workflow Analyzer, execution "
            "and UFT equivalence still require external verification."
        ),
    }
