"""One-command manifest to a Studio test project and optional ZIP."""
import argparse
import json
import shutil
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from uft2uipath.script_analysis.batch import run_batch
from uft2uipath.script_generation.batch import emit_bundle
from uft2uipath.script_generation.emitter import TYPES, UI, X, document, expr, q, throw, write_xaml

DEPENDENCIES = {
    "UiPath.System.Activities": "[23.10.3]",
    "UiPath.Testing.Activities": "[23.10.0]",
    "UiPath.UIAutomation.Activities": "[23.10.7]",
}


def project_metadata(name, tests, template=None):
    """project.json for a Windows C# test project, optionally based on a template."""
    if template:
        data = json.loads(Path(template).read_text(encoding="utf-8-sig"))
        if data.get("targetFramework") != "Windows" or data.get("expressionLanguage") != "CSharp":
            raise ValueError("Project template must be Windows + CSharp.")
        for package in DEPENDENCIES:
            if package not in data.get("dependencies", {}):
                raise ValueError(f"Template requires {package}.")
    else:
        data = {
            "dependencies": dict(DEPENDENCIES),
            "webServices": [], "entitiesStores": [],
            "schemaVersion": "4.0", "studioVersion": "23.10.0.0",
            "runtimeOptions": {
                "isPausable": True, "isAttended": True,
                "requiresUserInteraction": True, "supportsPersistence": False,
                "workflowSerialization": "DataContract",
                "excludedLoggedData": ["Private:*", "*password*"],
                "executionType": "Workflow", "mustRestoreAllDependencies": True,
            },
            "designOptions": {
                "projectProfile": "Developement", "outputType": "Tests",
                "libraryOptions": {"includeOriginalXaml": False, "privateWorkflows": []},
                "processOptions": {"ignoredFiles": []},
                "modernBehavior": False,
            },
        }
    project_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "uft2uipath:" + name))
    data.update(
        name=name, projectId=project_id, description="Generated UFT migration preview; see generation-report.json",
        main="Main.xaml", projectVersion="0.1.0",
        expressionLanguage="CSharp", targetFramework="Windows",
        isTemplate=False, templateProjectData={}, publishData={},
    )
    data["designOptions"]["outputType"] = "Tests"
    data["designOptions"]["fileInfoCollection"] = [
        {
            "editingStatus": "InProgress",
            "testCaseId": str(uuid.uuid5(uuid.UUID(project_id), f"test:{test['test_id']}")),
            "testCaseType": "TestCase",
            "fileName": f"Tests\\Test_{test['test_id']}.xaml",
        }
        for test in tests
    ]
    # Let Studio discover entry argument metadata from XAML.
    data.pop("entryPoints", None)
    return data


def migrate_project(manifest, bindings, output, template=None, make_zip=False):
    """Analyze, emit and package a manifest as a Studio test project (migrate-project)."""
    output = Path(output).resolve()
    archive = output.with_name(output.name + ".zip")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Output exists: {output}")
    if make_zip and (archive.exists() or archive.is_symlink()):
        raise FileExistsError(f"ZIP exists: {archive}")
    with tempfile.TemporaryDirectory(prefix="uft_project_") as temporary:
        stage = Path(temporary)
        run_batch(manifest, stage / "analysis")
        report = emit_bundle(stage / "analysis", bindings, stage / "project")
        generated = stage / "project"
        if not report["tests"]:
            raise ValueError("At least one linked test is required.")
        metadata = project_metadata(output.name, report["tests"], template)
        (generated / "project.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        first = report["tests"][0]
        root, sequence = document("Main", first["arguments"])
        if first["status"] == "blocked":
            sequence.append(throw("Selected migration test is blocked. Open Tests and generation-report.json."))
        invoke = ET.SubElement(sequence, q("InvokeWorkflowFile", UI), {
            "DisplayName": f"Open test {first['test_id']}",
            "WorkflowFileName": f"Tests\\Test_{first['test_id']}.xaml",
        })
        arguments = ET.SubElement(invoke, q("InvokeWorkflowFile.Arguments", UI))
        for name, kind in first["arguments"].items():
            ET.SubElement(arguments, q("InArgument"), {
                q("TypeArguments", X): TYPES[kind], q("Key", X): name,
            }).text = expr(name)
        if not len(arguments):
            invoke.remove(arguments)
        write_xaml(generated / "Main.xaml", root)
        report["studio_project"] = {
            "project_file": "project.json", "target": "Windows", "language": "CSharp",
            "registered_test_count": len(report["tests"]),
            "studio_load_verified": False,
            "dependency_profile": "template" if template else "official-sample-23.10-baseline",
        }
        # Bundle-level instructions differ from raw emission.
        report["limitations"] = [
            s for s in report["limitations"]
            if not s.startswith("No project.json") and not s.startswith("Generated test files")
        ] + ["Test registration uses Studio project metadata; actual discovery, validation and execution must be checked in Studio."]
        (generated / "generation-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        (generated / "OPEN_IN_UIPATH.md").write_text(
            "# Open the generated project\n\n"
            "1. Extract the entire ZIP into a new folder.\n"
            "2. In UiPath Studio choose Open and select project.json.\n"
            "3. Allow dependency restoration.\n"
            "4. Open Tests/Test_1.xaml (or another generated Test_<ID>.xaml).\n"
            "5. Open Workflows/Component_<ID>.xaml to inspect migrated branches and activities.\n"
            "6. Run Studio validation before execution.\n\n"
            "Validation corrections: argumentless workflows omit x:Members; "
            "Click and Type Into use Attach Browser with partial selectors. "
            "Exist stays before If, outside the branch scopes. "
            "Keep the UI-DBP-006 analyzer rule enabled.\n\n"
            "The sample uses synthetic selectors and is intentionally blocked with Throw. "
            "Do not remove the guard merely to make the test pass.\n\n"
            "The project targets Windows C#. Python tests check generation and XML, "
            "not Studio loading, compilation, execution or UFT equivalence. "
            "Read generation-report.json for unresolved items.\n\n"
            "Package versions use an official UiPath sample baseline. For your installed "
            "versions rerun migrate-project with --project-template pointing to a blank "
            "Windows C# test project's project.json containing System, Testing and UIAutomation dependencies.\n",
            encoding="utf-8",
        )
        (generated / "README.md").write_text(
            "# UFT migration preview\n\nOpen project.json in UiPath Studio.\n\n"
            "See OPEN_IN_UIPATH.md and generation-report.json.\n",
            encoding="utf-8",
        )
        shutil.copytree(generated, output)
        if make_zip:
            # Build outside destination, then exclusively create the final archive.
            temporary_zip = shutil.make_archive(str(stage / "project-package"), "zip", generated)
            with Path(temporary_zip).open("rb") as src, archive.open("xb") as dst:
                shutil.copyfileobj(src, dst)
    return output, archive if make_zip else None


def main(argv=None):
    """Command line of migrate-project."""
    parser = argparse.ArgumentParser(description="Migrate an explicitly mapped script manifest to a UiPath test project.")
    parser.add_argument("manifest")
    parser.add_argument("--bindings", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--project-template")
    parser.add_argument("--zip", action="store_true")
    args = parser.parse_args(argv)
    try:
        output, archive = migrate_project(
            args.manifest, args.bindings, args.out, args.project_template, args.zip,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(f"Open in Studio: {output / 'project.json'}")
    if archive:
        print(f"ZIP: {archive}")
    print("Studio validation and execution: not yet verified.")


if __name__ == "__main__":
    main()
