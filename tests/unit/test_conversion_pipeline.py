import json
import shutil
import sys
import zipfile

import pytest

from ptd_fixtures import minimal_bpt_export
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
    assert set(result.artifacts) == {"decoded-tables", "resolved-project", "pipeline-report"}

    decoded = read(result.artifacts["decoded-tables"])
    assert decoded["tables"]["TEST"] == {"row_count": 2}
    assert decoded["rows"]["TEST"][0]["TS_DESCRIPTION"] == "<html>Zürich</html>"

    report = read(result.artifacts["pipeline-report"])
    assert [s["name"] for s in report["stages"]] == ["extract", "decode", "model", *PENDING_STAGES]
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
