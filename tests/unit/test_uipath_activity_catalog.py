"""Tests for the UiPath activity catalog used by UFT mappings."""
import pytest

from uft2uipath.mapping import operation_registry
from uft2uipath.mapping.uipath_activity_catalog import (
    CATALOG, capabilities, describe, lookup, require,
)


def test_core_migration_activities_are_catalogued():
    for activity_id in (
        "Click", "TypeInto", "SelectItem", "UiElementExists", "GetAttribute",
        "LogMessage", "Throw", "Assign", "If", "StartProcess", "InvokeWorkflowFile",
    ):
        assert activity_id in CATALOG


def test_catalog_distinguishes_target_kinds():
    assert require("Click").target == "element"
    assert require("NGoToUrl").target == "browser"
    assert require("NCloseApplication").target == "application"
    assert require("LogMessage").target == "none"


def test_catalog_distinguishes_classic_and_modern_backends():
    assert require("Click").backend == "classic"
    assert require("NApplicationCard").backend == "modern"
    assert require("If").backend == "workflow"


def test_every_operation_registry_activity_exists_in_catalog():
    missing = {
        activity
        for entry in operation_registry.TABLE
        for activity in entry.activities
        if lookup(activity) is None
    }
    assert missing == set()


def test_registry_capabilities_include_activity_metadata():
    click = next(
        entry for entry in operation_registry.capabilities()["supported"]
        if entry["node_type"] == "ClickOperation"
    )
    assert click["activities"] == ["Click"]
    assert click["activity_specs"][0]["target"] == "element"
    assert click["activity_specs"][0]["backend"] == "classic"


def test_describe_returns_serializable_activity_metadata():
    items = describe(["Click", "NGoToUrl"])
    assert items[0]["display_name"] == "Click"
    assert items[1]["status"] == "planned"


def test_unknown_activity_fails_fast():
    with pytest.raises(ValueError, match="not in the migration activity catalog"):
        require("InventedActivity")


def test_capabilities_group_catalog_entries():
    grouped = capabilities()
    assert "Click" in [item["activity_id"] for item in grouped["emitted"]]
    assert "NGoToUrl" in [item["activity_id"] for item in grouped["planned"]]
    assert "BrowserScope" in [item["activity_id"] for item in grouped["supporting"]]
