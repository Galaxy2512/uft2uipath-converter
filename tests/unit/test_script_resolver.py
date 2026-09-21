import pytest

from ole_fixtures import action_resource
from ptd_fixtures import (COMPONENT_COLUMNS, RELATION_COLUMNS, TEST_COLUMNS,
                          repository_tables, write_export)
from uft2uipath.alm.repository import SmartRepository
from uft2uipath.alm.script_resolver import ScriptResolver, parse_run_actions
from uft2uipath.alm.tables import AlmTables
from uft2uipath.uft.action_resource import ActionResourceError, read_action_resource

AUTOMATED = "hp.qc.component.automated"
SHADOW = "hp.qc.component.shadow"
MANUAL = "hp.qc.component.manual"
BOM = b"\xef\xbb\xbf"


def action_files(root, actions):
    """actions: folder -> (logical name or None, script text)."""
    files = {}
    for folder, (name, script) in actions.items():
        files[f"{root}\\{folder}\\Script.mts"] = BOM + script.encode("utf-8")
        if name is not None:
            files[f"{root}\\{folder}\\Resource.mtr"] = action_resource(name)
        files[f"{root}\\{folder}\\ObjectRepository.bdb"] = b"bdb"
        files[f"{root}\\{folder}\\SnapShots\\obj0.inf"] = b"[obj]"
    return files


def component(number, name, subtype=AUTOMATED, flow=None):
    return {"CO_ID": number, "CO_NAME": name, "CO_SUBTYPE_ID": subtype,
            "CO_PHYSICAL_PATH": str(number), "CO_BPTA_FLOW_TEST_ID": flow}


def component_files(number, name):
    return action_files(f"components\\{number}\\COMPONENT_SCRIPT", {
        "Action0": ("Action0", f'RunAction "{name}", oneIteration'),
        "Action1": (name, f"' body of {name}"),
    })


def relation(bc_id, test, component_id, order, parent=None, subtype="hp.qc.bp-component.bpcomponent",
             name=None, condition=None):
    return {"BC_ID": bc_id, "BC_BPT_ID": test, "BC_CO_ID": component_id, "BC_ORDER": order,
            "BC_PARENT_ID": parent if parent is not None else test,
            "BC_PARENT_TYPE": "BPTEST_TO_COMPONENTS" if parent is not None else "TEST",
            "BC_SUBTYPE_ID": subtype, "BC_NAME": name, "BC_BPTA_CONDITION": condition}


def build(tmp_path, tests, components=(), relations=(), files=None):
    root = tmp_path / "export"
    tables = repository_tables(root, files or {})
    tables.update({
        "TEST": (TEST_COLUMNS, list(tests)),
        "COMPONENT": (COMPONENT_COLUMNS, list(components)),
        "BPTEST_TO_COMPONENTS": (RELATION_COLUMNS, list(relations)),
    })
    alm = AlmTables(write_export(root, tables))
    rows = {name: alm.rows(name) for name in ("TEST", "COMPONENT", "BPTEST_TO_COMPONENTS")}
    return ScriptResolver(SmartRepository(alm), rows)


def qtp_test(number, name, path=None):
    return {"TS_TEST_ID": number, "TS_NAME": name, "TS_TYPE": "QUICKTEST_TEST", "TS_PATH": path or str(number)}


def units(result):
    return [(u.asset, u.action, u.action_name, u.iterations) for u in result.execution]


def test_run_action_syntax_variants_and_comments():
    text = "\n".join([
        'Call RunAction("Get URL", oneIteration) @@ script comments_;_x',
        "' RunAction \"Commented\", oneIteration",
        "Rem RunAction \"Also commented\"",
        'RunAction "Sign On", allIterations, "p1"',
        'RunAction "Close"',
    ])
    calls = parse_run_actions(text)
    assert [(c.name, c.iterations, c.line) for c in calls] == [
        ("Get URL", "oneIteration", 1), ("Sign On", "allIterations", 4), ("Close", None, 5),
    ]


def test_scripted_test_follows_main_flow_by_logical_action_name(tmp_path):
    files = action_files("tests\\5\\sub", {
        "Action0": ("Action0", 'Call RunAction("Get URL", oneIteration)\nRunAction "Sign On", allIterations'),
        "Action1": ("Sign On", 'RunAction "Verify", oneIteration'),
        "Action2": ("Verify", "' nested"),
        "Action4": ("Get URL", "' first"),
    })
    resolver = build(tmp_path, [qtp_test(5, "Login", "5\\sub")], files=files)

    [result] = resolver.resolve([5])

    assert result.status == "resolved"
    assert units(result) == [
        ("test:5", "Action4", "Get URL", "oneIteration"),
        ("test:5", "Action1", "Sign On", "allIterations"),
        ("test:5", "Action2", "Verify", "oneIteration"),
    ]
    action = resolver.assets["test:5"].actions["Action1"]
    assert action.object_repository == "tests\\5\\sub\\Action1\\ObjectRepository.bdb"
    assert action.snapshot_infos == ["tests\\5\\sub\\Action1\\SnapShots\\obj0.inf"]
    assert action.encoding == "utf-8" and not action.text.startswith("﻿")


def test_external_action_resolves_through_owning_test_name(tmp_path):
    files = action_files("tests\\1", {"Action0": ("Action0", 'RunAction "Sign On"'),
                                      "Action1": ("Sign On", "' shared")})
    files.update(action_files("tests\\2", {
        "Action0": ("Action0", 'RunAction "Sign On [Shared Login]", oneIteration\nRunAction "Book"'),
        "Action1": ("Book", "' own"),
    }))
    resolver = build(tmp_path, [qtp_test(1, "Shared Login"), qtp_test(2, "Booking")], files=files)

    [result] = resolver.resolve([2])

    assert units(result) == [("test:1", "Action1", "Sign On", "oneIteration"),
                             ("test:2", "Action1", "Book", None)]


def test_unknown_or_ambiguous_actions_block_the_test(tmp_path):
    files = action_files("tests\\3", {
        "Action0": ("Action0", 'RunAction "Missing"\nRunAction "Twice"\nRunAction "Ok [Nowhere]"'),
        "Action1": ("Twice", ""), "Action2": ("Twice", ""),
    })
    resolver = build(tmp_path, [qtp_test(3, "Broken")], files=files)

    [result] = resolver.resolve([3])

    assert result.status == "blocked"
    codes = {issue["code"] for issue in result.issues}
    assert {"unresolved_action", "ambiguous_action", "external_test_not_found"} <= codes


def test_recursive_action_calls_are_reported(tmp_path):
    files = action_files("tests\\4", {"Action0": ("Action0", 'RunAction "Loop"'),
                                      "Action1": ("Loop", 'RunAction "Loop"')})
    [result] = build(tmp_path, [qtp_test(4, "Cycle")], files=files).resolve([4])

    assert result.status == "blocked"
    assert [issue["code"] for issue in result.issues] == ["action_cycle"]
    assert len(result.execution) == 1


def test_unreadable_action_resource_is_not_silently_ignored(tmp_path):
    files = action_files("tests\\6", {"Action0": ("Action0", 'RunAction "Action1"'),
                                      "Action1": (None, "' no Resource.mtr")})
    [result] = build(tmp_path, [qtp_test(6, "No resource")], files=files).resolve([6])

    assert units(result) == [("test:6", "Action1", None, None)]
    assert result.status == "blocked"
    assert result.issues[0]["code"] == "unreadable_action_resource"


def test_bpt_tree_keeps_order_groups_branches_and_flows(tmp_path):
    files = {}
    for number, name in ((1, "Login"), (2, "Open"), (3, "Delete"), (4, "Logout"), (5, "Start")):
        files.update(component_files(number, name))
    tests = [{"TS_TEST_ID": 10, "TS_NAME": "Delete order", "TS_TYPE": "BUSINESS-PROCESS"},
             {"TS_TEST_ID": 20, "TS_NAME": "Login flow", "TS_TYPE": "FLOW"}]
    components = [component(1, "Login"), component(2, "Open"), component(3, "Delete"),
                  component(4, "Logout"), component(5, "Start"),
                  component(9, "20_Login flow", SHADOW, flow=20)]
    relations = [
        relation(100, 10, 4, 900),
        relation(101, 10, 9, 100),
        relation(102, 10, None, 500, subtype="hp.qc.bp-component.group", name="Group1"),
        relation(103, 10, 3, 2, parent=102),
        relation(104, 10, 2, 1, parent=102),
        relation(105, 10, 0, 600, subtype="hp.qc.bp-component.switch", name="Branch 0", condition="<expression/>"),
        relation(106, 10, 0, 1, parent=105, subtype="hp.qc.bp-component.case", condition="<eq/>"),
        relation(107, 10, 5, 1, parent=106),
        relation(200, 20, 1, 1),
    ]
    resolver = build(tmp_path, tests, components, relations, files)

    [result] = resolver.resolve([10])

    assert result.status == "resolved"
    assert [(u.component_id, u.relation_id, u.flow_path) for u in result.execution] == [
        (1, 200, [20]), (2, 104, []), (3, 103, []), (5, 107, []), (4, 100, []),
    ]
    assert [[c["kind"] for c in u.containers] for u in result.execution] == [
        [], ["group"], ["group"], ["switch", "case"], [],
    ]
    assert result.execution[3].containers[1]["condition"] == "<eq/>"


def test_manual_missing_and_recursive_flow_components_block(tmp_path):
    tests = [{"TS_TEST_ID": 30, "TS_NAME": "Bad", "TS_TYPE": "BUSINESS-PROCESS"}]
    components = [component(1, "Manual", MANUAL), component(2, "Self", SHADOW, flow=30),
                  component(3, "No files")]
    relations = [relation(1, 30, 1, 1), relation(2, 30, 2, 2), relation(3, 30, 3, 3), relation(4, 30, 77, 4)]

    [result] = build(tmp_path, tests, components, relations).resolve([30])

    assert result.status == "blocked"
    assert [issue["code"] for issue in result.issues] == [
        "manual_component", "flow_cycle", "missing_asset_folder", "missing_component",
    ]


def test_non_automated_tests_are_classified_not_blocked(tmp_path):
    tests = [{"TS_TEST_ID": 1, "TS_NAME": "Manual", "TS_TYPE": "MANUAL"}]
    [result] = build(tmp_path, tests).resolve([1])
    assert (result.status, result.execution, result.issues) == ("not_automated", [], [])


def test_repository_rejects_physical_paths_outside_the_export(tmp_path):
    root = tmp_path / "export"
    tables = repository_tables(root, {"tests\\1\\Action0\\Script.mts": b"x"})
    tables["SMART_REPOSITORY_PHYSICAL_FILE"][1][0]["SRPF_PATH"] = "..\\..\\outside"
    repository = SmartRepository(AlmTables(write_export(root, tables)))

    with pytest.raises(ValueError, match="escapes"):
        repository.read_bytes("TESTS\\1\\action0\\script.mts")


def test_action_resource_rejects_non_ole_data():
    with pytest.raises(ActionResourceError, match="OLE"):
        read_action_resource(b"plain text")


def test_action_resource_reads_name_and_ignores_slack():
    resource = read_action_resource(action_resource("Departing and Arriving Locations", reusable=False))
    assert (resource.name, resource.reusable, resource.document_type) == (
        "Departing and Arriving Locations", False, "Action")
