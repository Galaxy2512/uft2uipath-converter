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
from uft2uipath.alm.repository import SmartRepository
from uft2uipath.alm.script_resolver import ScriptResolver
from uft2uipath.alm.tables import AlmTables
from uft2uipath.archive.extractor import ArchiveExtractor
from uft2uipath.ast import Project
from uft2uipath.mapping.acceptance import AcceptanceSettings, build_binding, decide, review_template
from uft2uipath.parser.project_builder import ProjectBuilder
from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_generation.project_emitter import (ActionPlan, TestPlan, generate,
                                                          workflow_name)
from uft2uipath.uft.object_repository import read_object_repository
from uft2uipath.uft.object_resolution import resolve_objects

FORMAT_VERSION = 1

MODEL_TABLES = ("TEST", "COMPONENT", "COMPONENT_STEP", "BPTEST_TO_COMPONENTS")
REPOSITORY_TABLES = ("SMART_REPOSITORY_LOGICAL_FILE", "SMART_REPOSITORY_PHYSICAL_FILE")
RESOURCE_TABLES = ("RESOURCES", "RESOURCE_FOLDERS")
EXPORTED_TABLES = MODEL_TABLES + REPOSITORY_TABLES + RESOURCE_TABLES

PENDING_STAGES = ("validate",)


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
        acceptance: AcceptanceSettings | None = None,
    ):
        self.source = Path(source).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.test_ids = list(dict.fromkeys(test_ids)) if test_ids else None
        self.acceptance = acceptance or AcceptanceSettings()

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

            stage, resolution = self._resolve_scripts(tables, decoded["rows"], project, staging)
            stages.append(stage)
            if resolution is None:
                stages.extend({"name": name, "status": "skipped",
                               "detail": "Script resolution did not run."}
                              for name in ("resolve_objects", "analyze", "bind", "emit"))
            else:
                repository, resolver, referenced, resolved = resolution
                object_stage, resolutions = self._resolve_objects(repository, resolver, referenced, staging)
                stages.append(object_stage)
                stages.extend(self._generate(resolver, resolutions, resolved, staging, project_name))

            stages.extend({"name": name, "status": "pending"} for name in PENDING_STAGES)
            _write(artifacts_dir / "pipeline-report.json", {
                "format_version": FORMAT_VERSION,
                "source": str(self.source),
                "project_name": project_name,
                "selection": self.test_ids,
                "stages": stages,
                "table_errors": table_errors,
                "uipath_project_generated": (staging / "project" / "project.json").is_file(),
            })

            shutil.copytree(staging, self.output_dir)

        artifacts = {
            name: self.output_dir / "artifacts" / f"{name}.json"
            for name in ("decoded-tables", "resolved-project", "resolved-scripts",
                         "selector-candidates", "script-analysis", "conversion-plan",
                         "selector-review.template", "pipeline-report")
        }
        artifacts = {name: path for name, path in artifacts.items() if path.is_file()}
        return PipelineResult(self.output_dir, project, artifacts, table_errors)

    def _resolve_scripts(self, tables, rows, project, staging: Path):
        missing = [name for name in REPOSITORY_TABLES if name not in rows]
        if missing or not tables.has(REPOSITORY_TABLES[0]):
            reason = f"Repository tables unavailable: {missing or [REPOSITORY_TABLES[0]]}"
            return {"name": "resolve_scripts", "status": "failed", "detail": reason}, None

        repository = SmartRepository(tables)
        resolver = ScriptResolver(repository, rows)
        resolved = resolver.resolve([test.id for test in project.tests])
        referenced = {unit.asset for test in resolved for unit in test.execution}
        referenced |= {key for key, asset in resolver.assets.items() if asset.issues}
        assets = {}
        for key in sorted(referenced):
            asset = resolver.assets[key]
            actions = {}
            for folder, action in asset.actions.items():
                source = f"sources/{asset.kind}_{asset.entity_id}/{folder}/Script.mts"
                target = staging / "artifacts" / source
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(action.text, encoding="utf-8", newline="")
                entry = asdict(action)
                entry.pop("text")
                entry["source_copy"] = source
                actions[folder] = entry
            assets[key] = {"kind": asset.kind, "entity_id": asset.entity_id, "root": asset.root,
                           "actions": actions, "issues": asset.issues}
        _write(staging / "artifacts" / "resolved-scripts.json", {
            "format_version": FORMAT_VERSION,
            "tests": [asdict(test) for test in resolved],
            "assets": assets,
        })
        statuses: dict[str, int] = {}
        for test in resolved:
            statuses[test.status] = statuses.get(test.status, 0) + 1
        stage = {"name": "resolve_scripts", "status": "done",
                 "artifact": "artifacts/resolved-scripts.json", "test_statuses": statuses}
        return stage, (repository, resolver, sorted(referenced), resolved)

    def _resolve_objects(self, repository, resolver, referenced, staging: Path) -> dict[str, Any]:
        cache: dict[str, tuple[Any, str | None]] = {}
        actions = {}
        statuses: dict[str, int] = {}
        for key in referenced:
            for folder, action in resolver.assets[key].actions.items():
                # UFT looks in the action's own repository first, then the shared ones in order.
                wanted = [action.object_repository] if action.object_repository else []
                wanted += [shared["path"] for shared in action.shared_repositories if shared["path"]]
                repositories, sources = [], []
                for path in wanted:
                    if path not in cache:
                        cache[path] = self._load_repository(repository, path)
                    loaded, issue = cache[path]
                    if loaded is not None:
                        repositories.append((path, loaded))
                    sources.append({"path": path, "issue": issue,
                                    "object_count": len(loaded.objects) if loaded else 0})
                objects = resolve_objects(action.text, repositories)
                for entry in objects:
                    statuses[entry["status"]] = statuses.get(entry["status"], 0) + 1
                actions[f"{key}/{folder}"] = {
                    "repositories": sources,
                    "unresolved_repository_references": [s for s in action.shared_repositories if not s["path"]],
                    "objects": objects,
                }
        _write(staging / "artifacts" / "selector-candidates.json", {
            "format_version": FORMAT_VERSION,
            "note": "Candidates are proposals derived from UFT identification properties; none is verified.",
            "actions": actions,
        })
        stage = {"name": "resolve_objects", "status": "done",
                 "artifact": "artifacts/selector-candidates.json", "reference_statuses": statuses}
        return stage, {key: value["objects"] for key, value in actions.items()}

    def _generate(self, resolver, resolutions, resolved, staging: Path, project_name: str):
        # Only actions a test actually executes become workflows; Action0 is the main flow.
        executed = {f"{unit.asset}/{unit.action}" for test in resolved for unit in test.execution}
        analyses, decisions = {}, {}
        for key, objects in sorted(resolutions.items()):
            if key not in executed:
                continue
            asset_key, folder = key.rsplit("/", 1)
            analyses[key] = analyze_source(resolver.assets[asset_key].actions[folder].text)
            decisions[key] = [decide(entry, self.acceptance) for entry in objects]
        _write(staging / "artifacts" / "script-analysis.json", {
            "format_version": FORMAT_VERSION,
            "actions": {key: {"coverage": analysis["coverage"], "issues": analysis["issues"],
                              "references": analysis["references"]}
                        for key, analysis in analyses.items()},
        })
        coverage = {"operation_count": 0, "recognized_operation_count": 0}
        for analysis in analyses.values():
            for name in coverage:
                coverage[name] += analysis["coverage"][name]
        analyze_stage = {"name": "analyze", "status": "done",
                         "artifact": "artifacts/script-analysis.json", **coverage}

        actions = {}
        for key, analysis in analyses.items():
            actions[key] = ActionPlan(key, workflow_name(key), analysis,
                                      build_binding(analysis, decisions[key]))
        accepted = sum(d["accepted"] for entries in decisions.values() for d in entries)
        _write(staging / "artifacts" / "conversion-plan.json", {
            "format_version": FORMAT_VERSION,
            "acceptance": {"threshold": self.acceptance.threshold,
                           "review_entries": len(self.acceptance.review),
                           "browser_type": self.acceptance.browser_type,
                           "timeout_ms": self.acceptance.timeout_ms},
            "actions": {key: {"workflow": plan.workflow, "binding": plan.binding,
                              "decisions": decisions[key]}
                        for key, plan in actions.items()},
        })
        _write(staging / "artifacts" / "selector-review.template.json", review_template(decisions))
        bind_stage = {"name": "bind", "status": "done", "artifact": "artifacts/conversion-plan.json",
                      "accepted_selectors": accepted,
                      "proposed_selectors": sum(bool(d["proposed"]) for e in decisions.values() for d in e)}

        tests = [TestPlan(test.test_id, test.name, test.status,
                          [asdict(unit) for unit in test.execution],
                          [dict(issue) for issue in test.issues])
                 for test in resolved]
        report = generate(staging / "project", project_name, actions, tests)
        report.update(format_version=FORMAT_VERSION, project_name=project_name,
                      studio_load_verified=False, executable_verified=False,
                      equivalent_verified=False)
        _write(staging / "project" / "generation-report.json", report)
        statuses: dict[str, int] = {}
        for entry in report["tests"]:
            statuses[entry["status"]] = statuses.get(entry["status"], 0) + 1
        emit_stage = {"name": "emit", "status": "done", "artifact": "project/project.json",
                      "test_statuses": statuses,
                      "registered_test_count": report["registered_test_count"]}
        return [analyze_stage, bind_stage, emit_stage]

    @staticmethod
    def _load_repository(repository, logical: str):
        try:
            return read_object_repository(repository.read_bytes(logical)), None
        except (OSError, ValueError) as exc:
            return None, str(exc)

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
