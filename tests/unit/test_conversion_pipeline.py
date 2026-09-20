import json
import shutil
import sys
import zipfile

import pytest

from bdb_fixtures import VT_BSTR, object_repository, object_stream
from ole_fixtures import action_resource
from ptd_fixtures import (COMPONENT_COLUMNS, RELATION_COLUMNS, RESOURCE_COLUMNS,
                          RESOURCE_FOLDER_COLUMNS, STEP_COLUMNS, TEST_COLUMNS,
                          minimal_bpt_export, repository_tables, write_export)
from uft2uipath import cli
from uft2uipath.pipeline import PENDING_STAGES, ConversionPipeline


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def zip_export(root, archive):
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in root.rglob("*"):
            bundle.write(path, path.relative_to(root))
    return archive


def test_pipeline_builds_model_from_real_table_rows(tmp_path):
    source = minimal_bpt_export(tmp_path / "export")

    result = ConversionPipeline(source, tmp_path / "out").run()

    assert result.project.name == "SYNTHETIC_ALM"
    test = next(t for t in result.project.tests if t.id == 7)
    assert [c.name for c in test.components] == ["Login", "Logout"]
    assert set(result.artifacts) == {"decoded-tables", "resolved-project", "resolved-scripts",
                                     "selector-candidates", "pipeline-report"}

    decoded = read(result.artifacts["decoded-tables"])
    assert decoded["tables"]["TEST"] == {"row_count": 2}
    assert decoded["rows"]["TEST"][0]["TS_DESCRIPTION"] == "<html>Zürich</html>"

    report = read(result.artifacts["pipeline-report"])
    assert [s["name"] for s in report["stages"]] == [
        "extract", "decode", "model", "resolve_scripts", "resolve_objects", *PENDING_STAGES,
    ]
    assert report["uipath_project_generated"] is False


def test_pipeline_reads_qcp_archive_and_never_copies_connection_details(tmp_path):
    export = minimal_bpt_export(tmp_path / "export")
    archive = zip_export(export, tmp_path / "demo.qcp")
    shutil.rmtree(export)

    result = ConversionPipeline(archive, tmp_path / "out").run()

    assert read(result.artifacts["pipeline-report"])["stages"][0]["detail"] == "archive"
    produced = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "out").rglob("*.json"))
    assert "secret" not in produced


def test_pipeline_selects_tests_in_requested_order(tmp_path):
    source = minimal_bpt_export(tmp_path / "export")

    result = ConversionPipeline(source, tmp_path / "out", test_ids=[8, 7, 8]).run()

    assert [t.id for t in result.project.tests] == [8, 7]
    assert read(result.artifacts["resolved-project"])["selection"] == [8, 7]


def test_pipeline_rejects_unknown_tests_without_writing_output(tmp_path):
    source = minimal_bpt_export(tmp_path / "export")

    with pytest.raises(ValueError, match=r"\[99\]"):
        ConversionPipeline(source, tmp_path / "out", test_ids=[99]).run()
    assert not (tmp_path / "out").exists()


def test_pipeline_refuses_existing_output(tmp_path):
    source = minimal_bpt_export(tmp_path / "export")
    (tmp_path / "out").mkdir()

    with pytest.raises(FileExistsError):
        ConversionPipeline(source, tmp_path / "out").run()


def test_pipeline_reports_undecodable_optional_tables_and_continues(tmp_path):
    source = minimal_bpt_export(tmp_path / "export")
    (source / "tables" / "SMART_REPOSITORY_LOGICAL_FILE_!000001.ptd").write_bytes(b"\x05")

    result = ConversionPipeline(source, tmp_path / "out").run()

    assert list(result.table_errors) == ["SMART_REPOSITORY_LOGICAL_FILE"]
    decoded = read(result.artifacts["decoded-tables"])
    assert "SMART_REPOSITORY_LOGICAL_FILE" not in decoded["rows"]


def test_pipeline_fails_when_a_model_table_cannot_be_decoded(tmp_path):
    source = minimal_bpt_export(tmp_path / "export")
    (source / "tables" / "TEST_!000001.ptd").write_bytes(b"\x05")

    with pytest.raises(ValueError, match="Required table TEST"):
        ConversionPipeline(source, tmp_path / "out").run()


def test_pipeline_resolves_scripts_and_copies_sources(tmp_path):
    root = tmp_path / "export"
    files = {
        "tests\\5\\Action0\\Script.mts": b'RunAction "Sign On", oneIteration',
        "tests\\5\\Action0\\Resource.mtr": action_resource("Action0"),
        "tests\\5\\Action1\\Script.mts": "' Zürich\r\nBrowser(\"B\").Page(\"P\").WebEdit(\"u\").Set \"x\"".encode(),
        "tests\\5\\Action1\\Resource.mtr": action_resource("Sign On"),
    }
    tables = repository_tables(root, files)
    tables.update({
        "TEST": (TEST_COLUMNS, [{"TS_TEST_ID": 5, "TS_NAME": "Login", "TS_TYPE": "QUICKTEST_TEST", "TS_PATH": "5"}]),
        "COMPONENT": (COMPONENT_COLUMNS, []),
        "COMPONENT_STEP": (STEP_COLUMNS, []),
        "BPTEST_TO_COMPONENTS": (RELATION_COLUMNS, []),
    })
    write_export(root, tables)

    result = ConversionPipeline(root, tmp_path / "out").run()

    scripts = read(result.artifacts["resolved-scripts"])
    assert scripts["tests"][0]["status"] == "resolved"
    assert [u["action_name"] for u in scripts["tests"][0]["execution"]] == ["Sign On"]
    action = scripts["assets"]["test:5"]["actions"]["Action1"]
    assert "text" not in action
    copy = tmp_path / "out" / "artifacts" / action["source_copy"]
    assert copy.read_bytes() == files["tests\\5\\Action1\\Script.mts"]
    stage = read(result.artifacts["pipeline-report"])["stages"][3]
    assert stage == {"name": "resolve_scripts", "status": "done",
                     "artifact": "artifacts/resolved-scripts.json", "test_statuses": {"resolved": 1}}


def test_pipeline_proposes_selectors_from_local_and_shared_repositories(tmp_path):
    root = tmp_path / "export"
    tree = [("Browser", [("B", "1", "Browser", [
        ("Page", [("P", "2", "Page", [("WebEdit", [("userName", "3", "WebEdit", [])])])])])])]
    shared = object_repository(tree, {
        "1": object_stream([("micclass", VT_BSTR, "Browser")], ["micclass"]),
        "2": object_stream([("micclass", VT_BSTR, "Page"), ("title", VT_BSTR, "Welcome")], ["micclass"]),
        "3": object_stream([("micclass", VT_BSTR, "WebEdit"), ("name", VT_BSTR, "userName"),
                            ("html tag", VT_BSTR, "INPUT")], ["micclass", "name", "html tag"]),
    })
    reference = "[QC-RESOURCE];;Resources\\Object Repositories;;\\Shared.tsr"
    files = {
        "tests\\5\\Action0\\Script.mts": b'RunAction "Sign On", oneIteration',
        "tests\\5\\Action0\\Resource.mtr": action_resource("Action0"),
        "tests\\5\\Action1\\Script.mts": b'Browser("B").Page("P").WebEdit("userName").Set "admin"',
        "tests\\5\\Action1\\Resource.mtr": action_resource("Sign On", shared_repositories=[reference]),
        "resources\\7\\Shared.tsr": shared,
    }
    tables = repository_tables(root, files)
    tables.update({
        "TEST": (TEST_COLUMNS, [{"TS_TEST_ID": 5, "TS_NAME": "Login",
                                 "TS_TYPE": "QUICKTEST_TEST", "TS_PATH": "5"}]),
        "COMPONENT": (COMPONENT_COLUMNS, []),
        "COMPONENT_STEP": (STEP_COLUMNS, []),
        "BPTEST_TO_COMPONENTS": (RELATION_COLUMNS, []),
        "RESOURCES": (RESOURCE_COLUMNS, [{"RSC_ID": 7, "RSC_NAME": "Shared.tsr",
                                          "RSC_FILE_NAME": "Shared.tsr", "RSC_PARENT_ID": 2}]),
        "RESOURCE_FOLDERS": (RESOURCE_FOLDER_COLUMNS, [
            {"RFO_ID": 1, "RFO_NAME": "Resources", "RFO_PARENT_ID": 0},
            {"RFO_ID": 2, "RFO_NAME": "Object Repositories", "RFO_PARENT_ID": 1}]),
    })
    write_export(root, tables)

    result = ConversionPipeline(root, tmp_path / "out").run()

    candidates = read(result.artifacts["selector-candidates"])
    action = candidates["actions"]["test:5/Action1"]
    assert [source["path"] for source in action["repositories"]] == ["resources\\7\\Shared.tsr"]
    assert action["unresolved_repository_references"] == []
    [entry] = action["objects"]
    assert entry["status"] == "resolved" and entry["repository"] == "resources\\7\\Shared.tsr"
    assert entry["candidate"]["selector"] == (
        '<html title="Welcome" /><webctrl name="userName" tag="INPUT" />'
    )
    assert entry["candidate"]["verified"] is False
    stage = read(result.artifacts["pipeline-report"])["stages"][4]
    assert stage["reference_statuses"] == {"resolved": 1}


def test_pipeline_reports_missing_repository_tables(tmp_path):
    source = minimal_bpt_export(tmp_path / "export")
    for name in ("SMART_REPOSITORY_LOGICAL_FILE", "SMART_REPOSITORY_PHYSICAL_FILE"):
        (source / "tables" / f"{name}_!000001.ptd").unlink()

    result = ConversionPipeline(source, tmp_path / "out").run()

    stages = read(result.artifacts["pipeline-report"])["stages"]
    assert [(s["name"], s["status"]) for s in stages[3:5]] == [
        ("resolve_scripts", "failed"), ("resolve_objects", "skipped"),
    ]
    assert "resolved-scripts" not in result.artifacts
    assert "selector-candidates" not in result.artifacts


def test_convert_command_runs_pipeline(tmp_path, monkeypatch, capsys):
    source = minimal_bpt_export(tmp_path / "export")
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["uft2uipath", "convert", str(source),
                                      "--out", str(out), "--test-id", "7"])

    cli.main()

    printed = capsys.readouterr().out
    assert "Tests selected: 1" in printed
    assert "No UiPath project generated" in printed
    assert (out / "artifacts" / "resolved-project.json").is_file()
