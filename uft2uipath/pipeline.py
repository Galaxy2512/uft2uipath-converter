"""Single entry point from an ALM/QCP export to reviewable migration artifacts.

Each stage writes one JSON artifact under <output>/artifacts so every
intermediate decision can be inspected. Stages not implemented yet are listed
as pending in pipeline-report.json instead of being silently skipped.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from uft2uipath.alm.ptd_reader import PtdFormatError
from uft2uipath.alm.tables import AlmTables
from uft2uipath.archive.extractor import ArchiveExtractor
from uft2uipath.ast import Project
from uft2uipath.parser.project_builder import ProjectBuilder

FORMAT_VERSION = 1

MODEL_TABLES = ("TEST", "COMPONENT", "COMPONENT_STEP", "BPTEST_TO_COMPONENTS")
REPOSITORY_TABLES = ("SMART_REPOSITORY_LOGICAL_FILE", "SMART_REPOSITORY_PHYSICAL_FILE")
EXPORTED_TABLES = MODEL_TABLES + REPOSITORY_TABLES

PENDING_STAGES = (
    "resolve_scripts",
    "resolve_objects",
    "analyze",
    "bind",
    "emit",
    "validate",
)


@dataclass
class PipelineResult:
    output_dir: Path
    project: Project
    artifacts: dict[str, Path] = field(default_factory=dict)
    table_errors: dict[str, str] = field(default_factory=dict)


class ConversionPipeline:
    def __init__(
        self,
        source: str | Path,
        output_dir: str | Path,
        test_ids: list[int] | None = None,
    ):
        self.source = Path(source).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.test_ids = list(dict.fromkeys(test_ids)) if test_ids else None

    def run(self) -> PipelineResult:
        if not self.source.exists():
            raise FileNotFoundError(self.source)
        if self.output_dir.exists() or self.output_dir.is_symlink():
            raise FileExistsError(f"Output already exists: {self.output_dir}")

        with tempfile.TemporaryDirectory(prefix="uft2uipath_pipeline_") as temporary:
            staging = Path(temporary) / "output"
            artifacts_dir = staging / "artifacts"
            artifacts_dir.mkdir(parents=True)
            stages: list[dict[str, Any]] = []

            extracted, cleanup = self._extract(Path(temporary))
            stages.append({"name": "extract", "status": "done",
                           "detail": "archive" if cleanup else "directory"})

            tables = AlmTables(extracted)
            project_name = self._project_name(extracted)
            decoded, table_errors = self._decode(tables)
            _write(artifacts_dir / "decoded-tables.json", {
                "format_version": FORMAT_VERSION,
                "source": str(self.source),
                "project_name": project_name,
                "tables": decoded["summary"],
                "rows": decoded["rows"],
            })
            stages.append({
                "name": "decode", "status": "done" if not table_errors else "done_with_errors",
                "artifact": "artifacts/decoded-tables.json",
                "table_count": len(decoded["summary"]), "error_count": len(table_errors),
            })

            project = self._build_model(project_name, decoded["rows"])
            _write(artifacts_dir / "resolved-project.json", {
                "format_version": FORMAT_VERSION,
                "selection": self.test_ids,
                "project": asdict(project),
            })
            stages.append({
                "name": "model", "status": "done",
                "artifact": "artifacts/resolved-project.json",
                "test_count": len(project.tests),
            })

            stages.extend({"name": name, "status": "pending"} for name in PENDING_STAGES)
            _write(artifacts_dir / "pipeline-report.json", {
                "format_version": FORMAT_VERSION,
                "source": str(self.source),
                "project_name": project_name,
                "selection": self.test_ids,
                "stages": stages,
                "table_errors": table_errors,
                "uipath_project_generated": False,
            })

            shutil.copytree(staging, self.output_dir)

        artifacts = {
            name: self.output_dir / "artifacts" / f"{name}.json"
            for name in ("decoded-tables", "resolved-project", "pipeline-report")
        }
        return PipelineResult(self.output_dir, project, artifacts, table_errors)

    def _extract(self, workspace: Path) -> tuple[Path, bool]:
        if self.source.is_dir():
            return self.source, False
        if self.source.suffix.lower() not in (".qcp", ".zip"):
            raise ValueError(f"Unsupported source: {self.source.name} (expected .qcp, .zip or directory)")
        extracted = ArchiveExtractor().extract(self.source)
        # Move under the pipeline workspace so it is removed with it.
        target = workspace / "extracted"
        shutil.move(str(extracted), target)
        return target, True

    def _project_name(self, extracted: Path) -> str:
        # dbid.xml also holds DB connection details; only the name is read.
        dbid = extracted / "dbid.xml"
        if dbid.is_file():
            name = ET.parse(dbid).getroot().findtext("PROJECT_NAME")
            if name and name.strip():
                return name.strip()
        return self.source.stem

    def _decode(self, tables: AlmTables) -> tuple[dict[str, Any], dict[str, str]]:
        summary: dict[str, dict[str, Any]] = {}
        rows: dict[str, list[dict[str, Any]]] = {}
        errors: dict[str, str] = {}
        for name in tables.names():
            try:
                summary[name] = {"row_count": len(tables.rows(name))}
            except PtdFormatError as exc:
                summary[name] = {"row_count": None, "error": str(exc)}
                errors[name] = str(exc)
        for name in EXPORTED_TABLES:
            if name in errors:
                if name in MODEL_TABLES:
                    raise PtdFormatError(f"Required table {name} could not be decoded: {errors[name]}")
                continue
            rows[name] = tables.rows(name)
        return {"summary": summary, "rows": rows}, errors

    def _build_model(self, project_name: str, rows: dict[str, list[dict[str, Any]]]) -> Project:
        project = ProjectBuilder().build(
            project_name=project_name,
            test_rows=rows["TEST"],
            component_rows=rows["COMPONENT"],
            component_step_rows=rows["COMPONENT_STEP"],
            test_component_rows=rows["BPTEST_TO_COMPONENTS"],
            source_path=str(self.source),
        )
        if self.test_ids is not None:
            by_id = {test.id: test for test in project.tests}
            missing = [number for number in self.test_ids if number not in by_id]
            if missing:
                raise ValueError(f"Test IDs not found in {self.source.name}: {missing}")
            project.tests = [by_id[number] for number in self.test_ids]
        return project


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
