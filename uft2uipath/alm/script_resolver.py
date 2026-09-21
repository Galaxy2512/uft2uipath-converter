"""Resolves ALM tests to the ordered UFT action scripts they execute.

- QUICKTEST_TEST: the test folder is tests\\<TS_PATH>; Action0 is the main
  flow and RunAction calls select the other actions by their logical name
  (stored in each action's Resource.mtr). "Action [Other Test]" calls an
  action stored in another QUICKTEST_TEST.
- BUSINESS-PROCESS / FLOW: BPTEST_TO_COMPONENTS is a tree (BC_PARENT_TYPE
  TEST = top level, BPTEST_TO_COMPONENTS = child of relation BC_PARENT_ID),
  siblings ordered by BC_ORDER. Groups and switch/case branches are kept as
  containers on each execution unit. Automated components live in
  components\\<CO_PHYSICAL_PATH>\\COMPONENT_SCRIPT with the same
  Action0/RunAction layout; shadow components stand for a FLOW test
  (CO_BPTA_FLOW_TEST_ID) and are expanded in place.

Nothing is guessed: anything that cannot be resolved is recorded as an issue
on the test, and the test is marked blocked.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from uft2uipath.alm.repository import SmartRepository, normalize
from uft2uipath.alm.resources import ResourceIndex, parse_reference
from uft2uipath.uft.action_resource import ActionResourceError, read_action_resource

SCRIPTED_TEST_TYPES = {"QUICKTEST_TEST"}
BPT_TEST_TYPES = {"BUSINESS-PROCESS", "FLOW"}
AUTOMATED_COMPONENT = "hp.qc.component.automated"
SHADOW_COMPONENT = "hp.qc.component.shadow"
RELATION_COMPONENT = "hp.qc.bp-component.bpcomponent"
RELATION_CONTAINERS = {
    "hp.qc.bp-component.group": "group",
    "hp.qc.bp-component.switch": "switch",
    "hp.qc.bp-component.case": "case",
}

_ACTION_FOLDER = re.compile(r"^(Action\d+)\\", re.IGNORECASE)
_RUN_ACTION = re.compile(
    r"^(?:call\s+)?RunAction\s*\(?\s*\"([^\"]+)\"\s*(?:,\s*([^,)]+))?(.*)$",
    re.IGNORECASE,
)
_EXTERNAL_ACTION = re.compile(r"^(.*?)\s*\[(.+)\]$")


@dataclass
class ActionCall:
    """A RunAction call in a script: the called name, its iterations and where it is written."""
    name: str
    iterations: str | None
    line: int
    source: str
    target: str | None = None
    target_asset: str | None = None


@dataclass
class ActionScript:
    """One action of a test or component: its Script.mts text and metadata
    (logical name, repositories, snapshots) and the RunAction calls it makes.
    """
    folder: str
    name: str | None
    script: str
    physical_path: str
    sha256: str
    encoding: str
    text: str
    object_repository: str | None
    shared_repositories: list[dict[str, Any]]
    snapshot_infos: list[str]
    calls: list[ActionCall] = field(default_factory=list)


@dataclass
class ScriptAsset:
    """A test or component folder in the repository with its actions and function libraries."""
    key: str
    kind: str
    entity_id: int
    root: str
    actions: dict[str, ActionScript] = field(default_factory=dict)
    function_libraries: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ExecutionUnit:
    """One action executed by a test, in order, with the component, relation,
    flow and group/branch containers it was reached through.
    """
    order: int
    asset: str
    action: str
    action_name: str | None
    iterations: str | None
    component_id: int | None = None
    relation_id: int | None = None
    flow_path: list[int] = field(default_factory=list)
    containers: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ResolvedTest:
    """An ALM test with the ordered actions it executes and why it may be blocked."""
    test_id: int
    name: str
    test_type: str | None
    status: str
    execution: list[ExecutionUnit] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)


def decode_script(data: bytes) -> tuple[str, str]:
    """Decode Script.mts bytes (UTF-16 with BOM, UTF-8, else cp1252) and name the encoding used."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), "cp1252"


def parse_run_actions(text: str) -> list[ActionCall]:
    """RunAction calls in a script, skipping comments and UFT step metadata."""
    calls = []
    for number, line in enumerate(text.splitlines(), 1):
        code = line.split(" @@ ", 1)[0].strip()
        if not code or code.startswith("'") or code.lower().startswith("rem "):
            continue
        match = _RUN_ACTION.match(code)
        if match:
            iterations = match.group(2).strip() if match.group(2) else None
            calls.append(ActionCall(match.group(1), iterations, number, code))
    return calls


@dataclass
class _Context:
    """Where the expansion currently is: component, relation, flow path and containers."""
    component_id: int | None = None
    relation_id: int | None = None
    flow_path: list[int] = field(default_factory=list)
    containers: list[dict[str, Any]] = field(default_factory=list)


class ScriptResolver:
    """Resolves ALM tests (scripted or BPT) to the ordered action scripts they run."""
    def __init__(self, repository: SmartRepository, rows: dict[str, list[dict[str, Any]]]):
        """Index tests, components and the BPT relation tree; nothing is read from disk yet."""
        self.repository = repository
        self.tests = {row["TS_TEST_ID"]: row for row in rows["TEST"]}
        self.components = {row["CO_ID"]: row for row in rows["COMPONENT"]}
        self.children: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for row in rows["BPTEST_TO_COMPONENTS"]:
            parent_type = row.get("BC_PARENT_TYPE") or "TEST"
            parent_id = row.get("BC_PARENT_ID") if row.get("BC_PARENT_ID") is not None else row.get("BC_BPT_ID")
            self.children.setdefault((parent_type, parent_id), []).append(row)
        for siblings in self.children.values():
            siblings.sort(key=lambda r: (_sort_int(r.get("BC_ORDER")), _sort_int(r.get("BC_ID"))))
        self.assets: dict[str, ScriptAsset] = {}
        self.resources = (
            ResourceIndex(rows["RESOURCES"], rows.get("RESOURCE_FOLDERS", []))
            if "RESOURCES" in rows else None
        )

    def resolve(self, test_ids: list[int]) -> list[ResolvedTest]:
        """Resolve the given tests in order."""
        return [self._resolve_test(test_id) for test_id in test_ids]

    def _resolve_test(self, test_id: int) -> ResolvedTest:
        """Resolve one test by type; manual tests are not_automated, unresolved parts block it."""
        row = self.tests[test_id]
        test_type = row.get("TS_TYPE")
        result = ResolvedTest(test_id, row.get("TS_NAME") or "", test_type, "resolved")
        if test_type in SCRIPTED_TEST_TYPES:
            asset = self._test_asset(test_id)
            if asset is None:
                _issue(result, "missing_test_path", "TEST.TS_PATH is empty.")
            else:
                self._expand(asset, result, _Context())
        elif test_type in BPT_TEST_TYPES:
            relations = self.children.get(("TEST", test_id), [])
            if not relations:
                _issue(result, "no_components", f"BPT test {test_id} has no component relations.")
            self._expand_relations(relations, result, _Context())
        else:
            result.status = "not_automated"
            return result
        if not result.execution and not result.issues:
            _issue(result, "empty_test", "Test resolves to no executable action.")
        if result.issues:
            result.status = "blocked"
        return result

    def _expand_relations(self, relations, result: ResolvedTest, context: _Context) -> None:
        """Expand BPT relations in order; groups and switch/case branches become containers."""
        for relation in relations:
            subtype = relation.get("BC_SUBTYPE_ID") or RELATION_COMPONENT
            if subtype in RELATION_CONTAINERS:
                container = {
                    "kind": RELATION_CONTAINERS[subtype], "relation_id": relation.get("BC_ID"),
                    "name": relation.get("BC_NAME"), "condition": relation.get("BC_BPTA_CONDITION"),
                }
                children = self.children.get(("BPTEST_TO_COMPONENTS", relation.get("BC_ID")), [])
                self._expand_relations(children, result, _Context(
                    context.component_id, context.relation_id, context.flow_path,
                    context.containers + [container],
                ))
            elif subtype == RELATION_COMPONENT:
                self._expand_component(relation, result, context)
            else:
                _issue(result, "unsupported_relation",
                       f"Relation {relation.get('BC_ID')} has unsupported type {subtype}.")

    def _expand_component(self, relation, result: ResolvedTest, context: _Context) -> None:
        """Expand one component relation: an automated component's actions, or a shadow component's flow."""
        component_id = relation.get("BC_CO_ID")
        component = self.components.get(component_id)
        if component is None:
            _issue(result, "missing_component",
                   f"Relation {relation.get('BC_ID')} references unknown component {component_id}.")
            return
        subtype = component.get("CO_SUBTYPE_ID")
        if subtype == SHADOW_COMPONENT:
            flow_id = component.get("CO_BPTA_FLOW_TEST_ID")
            if flow_id not in self.tests:
                _issue(result, "missing_flow", f"Component {component_id} references unknown flow test {flow_id}.")
            elif flow_id == result.test_id or flow_id in context.flow_path:
                _issue(result, "flow_cycle", f"Flow {flow_id} is included recursively.")
            else:
                self._expand_relations(self.children.get(("TEST", flow_id), []), result, _Context(
                    context.component_id, context.relation_id,
                    context.flow_path + [flow_id], context.containers,
                ))
        elif subtype == AUTOMATED_COMPONENT:
            folder = f"components\\{component.get('CO_PHYSICAL_PATH') or component_id}\\COMPONENT_SCRIPT"
            asset = self._asset("component", component_id, folder)
            self._expand(asset, result, _Context(
                component_id, relation.get("BC_ID"), context.flow_path, context.containers,
            ))
        else:
            _issue(result, "manual_component",
                   f"Component {component_id} ({component.get('CO_NAME')}) is not automated ({subtype}).")

    def _expand(self, asset: ScriptAsset, result: ResolvedTest, context: _Context) -> None:
        """Expand an asset from its main flow, Action0."""
        for issue in asset.issues:
            _issue(result, issue["code"], f"{asset.key}: {issue['message']}")
        main = asset.actions.get("Action0")
        if main is None:
            if not asset.issues:
                _issue(result, "missing_main_action", f"{asset.key}: Action0 (main flow) not found.")
            return
        self._walk(asset, main, result, context, stack=[(asset.key, "Action0")])

    def _walk(self, asset: ScriptAsset, action: ActionScript, result: ResolvedTest,
              context: _Context, stack: list[tuple[str, str]]) -> None:
        """Follow the RunAction calls of an action depth-first, recording each executed action."""
        for call in action.calls:
            if call.target is None:
                _issue(result, "unresolved_action", f"{asset.key}/{action.folder} line {call.line}: {call.source}")
                continue
            target_asset = self.assets[call.target_asset]
            if (target_asset.key, call.target) in stack:
                _issue(result, "action_cycle", f"{target_asset.key}: {call.target} is called recursively.")
                continue
            if target_asset is not asset:
                for issue in target_asset.issues:
                    _issue(result, issue["code"], f"{target_asset.key}: {issue['message']}")
            target = target_asset.actions[call.target]
            result.execution.append(ExecutionUnit(
                order=len(result.execution) + 1, asset=target_asset.key, action=target.folder,
                action_name=target.name, iterations=call.iterations,
                component_id=context.component_id, relation_id=context.relation_id,
                flow_path=list(context.flow_path), containers=list(context.containers),
            ))
            self._walk(target_asset, target, result, context, stack + [(target_asset.key, target.folder)])

    def _test_asset(self, test_id: int) -> ScriptAsset | None:
        """The scripted test's asset, from TS_PATH; None if the path is empty."""
        path = self.tests[test_id].get("TS_PATH")
        return self._asset("test", test_id, "tests\\" + path) if path else None

    def _asset(self, kind: str, entity_id: int, root: str) -> ScriptAsset:
        """Load (once) a test or component folder: its actions, function libraries and call targets."""
        key = f"{kind}:{entity_id}"
        if key in self.assets:
            return self.assets[key]
        asset = ScriptAsset(key, kind, entity_id, normalize(root))
        self.assets[key] = asset
        files = self.repository.files_under(asset.root)
        if not files:
            asset.issues.append({"code": "missing_asset_folder", "message": f"No repository files under {asset.root}."})
            return asset
        asset.function_libraries = self._function_libraries(asset)
        folders = sorted({m.group(1) for f in files if (m := _ACTION_FOLDER.match(f[len(asset.root) + 1:]))},
                         key=lambda name: int(name[6:]))
        for folder in folders:
            self._load_action(asset, folder, files)
        self._link_calls(asset)
        return asset

    def _load_action(self, asset: ScriptAsset, folder: str, files: list[str]) -> None:
        """Read one action folder: Script.mts, Resource.mtr metadata and repository files."""
        base = f"{asset.root}\\{folder}"
        script = f"{base}\\Script.mts"
        if not self.repository.exists(script):
            return
        try:
            data = self.repository.read_bytes(script)
        except (FileNotFoundError, ValueError) as exc:
            asset.issues.append({"code": "unreadable_script", "message": str(exc)})
            return
        text, encoding = decode_script(data)
        name, shared = None, []
        resource = f"{base}\\Resource.mtr"
        try:
            metadata = read_action_resource(self.repository.read_bytes(resource))
            name = metadata.name
            shared = [self._shared_repository(reference) for reference in metadata.shared_repositories]
        except (FileNotFoundError, ActionResourceError) as exc:
            asset.issues.append({"code": "unreadable_action_resource", "message": f"{resource}: {exc}"})
        repository_file = f"{base}\\ObjectRepository.bdb"
        snapshots = f"{base}\\snapshots\\".lower()
        asset.actions[folder] = ActionScript(
            folder=folder, name=name, script=script,
            physical_path=str(self.repository.physical_path(script).relative_to(self.repository.root)),
            sha256=hashlib.sha256(data).hexdigest(), encoding=encoding, text=text,
            object_repository=repository_file if self.repository.exists(repository_file) else None,
            shared_repositories=shared,
            snapshot_infos=[f for f in files if f.lower().startswith(snapshots) and f.lower().endswith(".inf")],
            calls=parse_run_actions(text),
        )

    def _function_libraries(self, asset: ScriptAsset) -> list[dict[str, Any]]:
        """Function libraries are associated with the test or component, in Test.tsp."""
        settings = f"{asset.root}\\Test.tsp"
        if not self.repository.exists(settings):
            return []
        try:
            metadata = read_action_resource(self.repository.read_bytes(settings), require_name=False)
        except (FileNotFoundError, ActionResourceError) as exc:
            asset.issues.append({"code": "unreadable_test_settings", "message": f"{settings}: {exc}"})
            return []
        return [self._resource(reference) for reference in metadata.function_libraries]

    def _shared_repository(self, reference: str) -> dict[str, Any]:
        """Resolve a shared Object Repository reference of an action."""
        return self._resource(reference)

    def _resource(self, reference: str) -> dict[str, Any]:
        """Resolve an ALM resource reference to a repository file, recording why it failed if it did."""
        entry: dict[str, Any] = {"reference": reference, "path": None, "issue": None}
        parts = parse_reference(reference)
        if parts is None:
            entry["issue"] = "unsupported_reference_format"
        elif self.resources is None:
            entry["issue"] = "resource_tables_unavailable"
        else:
            entry["path"] = self.resources.find(*parts)
            if entry["path"] is None:
                candidates = [path for path in self.resources.find_by_name(parts[1])
                              if self.repository.exists(path)]
                if len(candidates) == 1:
                    entry["path"] = candidates[0]
                    entry["issue"] = "resolved_by_file_name"
                else:
                    entry["issue"] = "resource_not_found" if not candidates else "ambiguous_resource"
            elif not self.repository.exists(entry["path"]):
                entry["issue"] = "resource_file_missing"
        return entry

    def _link_calls(self, asset: ScriptAsset) -> None:
        """Link each RunAction call to the action it names; ambiguous names are issues."""
        for action in asset.actions.values():
            for call in action.calls:
                external = _EXTERNAL_ACTION.match(call.name)
                if external:
                    self._link_external(asset, action, call, external.group(1), external.group(2))
                    continue
                matches = _find_action(asset, call.name)
                if len(matches) == 1:
                    call.target, call.target_asset = matches[0], asset.key
                elif len(matches) > 1:
                    asset.issues.append({"code": "ambiguous_action",
                                         "message": f"{action.folder} line {call.line}: {call.name!r} matches {matches}"})

    def _link_external(self, asset, action, call, action_name: str, test_name: str) -> None:
        """Link a call to an action of another scripted test ('Action [Test]')."""
        owners = [test_id for test_id, row in self.tests.items()
                  if row.get("TS_TYPE") in SCRIPTED_TEST_TYPES
                  and (row.get("TS_NAME") or "").casefold() == test_name.casefold()]
        where = f"{action.folder} line {call.line}"
        if len(owners) != 1:
            asset.issues.append({"code": "external_test_not_found" if not owners else "ambiguous_external_test",
                                 "message": f"{where}: test {test_name!r} matches {len(owners)} scripted tests."})
            return
        owner = self._test_asset(owners[0])
        matches = _find_action(owner, action_name) if owner else []
        if len(matches) != 1:
            asset.issues.append({"code": "external_action_not_found",
                                 "message": f"{where}: action {action_name!r} matches {matches} in test {owners[0]}."})
            return
        call.target, call.target_asset = matches[0], owner.key


def _find_action(asset: ScriptAsset, label: str) -> list[str]:
    """Action folders whose folder name or logical name matches, case-insensitively."""
    wanted = label.casefold()
    return sorted({a.folder for a in asset.actions.values()
                   if wanted in {a.folder.casefold(), (a.name or "").casefold()}})


def _issue(result: ResolvedTest, code: str, message: str) -> None:
    """Record an issue on a test once."""
    entry = {"code": code, "message": message}
    if entry not in result.issues:
        result.issues.append(entry)


def _sort_int(value) -> int:
    """Sort key that puts missing orders last."""
    return value if isinstance(value, int) else 2**31
