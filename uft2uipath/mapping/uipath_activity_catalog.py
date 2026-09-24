"""UiPath activity catalog used by the migration mapper.

This is deliberately not a dump of every activity shipped by UiPath. UiPath
packages contain hundreds of activities and change by version. The catalog is
the supported migration surface: activities that the converter emits today or
has an explicit near-term mapping for.

The UFT mapping registry references activity IDs from this file. Keeping UiPath
metadata here lets the converter answer two different questions cleanly:

1. What does the UFT construct mean?        -> mapping.operation_registry
2. What UiPath primitive implements it?     -> this catalog

No parser code or XAML generation code is imported here.
"""
from __future__ import annotations

from dataclasses import dataclass

TARGETS = ("none", "element", "browser", "page", "window", "application", "workflow")
BACKENDS = ("workflow", "classic", "modern")
STATUSES = ("emitted", "planned", "supporting")


@dataclass(frozen=True)
class UiPathActivity:
    """One UiPath primitive relevant to UFT migration."""

    activity_id: str
    display_name: str
    xaml_name: str
    package: str
    category: str
    target: str = "none"
    backend: str = "workflow"
    status: str = "emitted"
    notes: str = ""


TABLE = (
    # ------------------------------------------------------------------
    # Workflow / control-flow primitives
    # ------------------------------------------------------------------
    UiPathActivity("Sequence", "Sequence", "Sequence", "System.Activities",
                   "flow", status="supporting"),
    UiPathActivity("If", "If", "If", "System.Activities",
                   "flow"),
    UiPathActivity("Assign", "Assign", "Assign", "System.Activities",
                   "flow"),
    UiPathActivity("Delay", "Delay", "Delay", "System.Activities",
                   "flow"),
    UiPathActivity("Throw", "Throw", "Throw", "System.Activities",
                   "flow"),
    UiPathActivity("TryCatch", "Try Catch", "TryCatch", "System.Activities",
                   "flow", status="supporting"),
    UiPathActivity("Rethrow", "Rethrow", "Rethrow", "System.Activities",
                   "flow", status="supporting"),

    # ------------------------------------------------------------------
    # Core / system activities
    # ------------------------------------------------------------------
    UiPathActivity("LogMessage", "Log Message", "ui:LogMessage",
                   "UiPath.System.Activities", "system"),
    UiPathActivity("StartProcess", "Start Process", "ui:StartProcess",
                   "UiPath.System.Activities", "system", target="application"),
    UiPathActivity("InvokeWorkflowFile", "Invoke Workflow File",
                   "ui:InvokeWorkflowFile", "UiPath.System.Activities",
                   "workflow", target="workflow"),

    # ------------------------------------------------------------------
    # Classic UI Automation activities emitted by the current backend
    # ------------------------------------------------------------------
    UiPathActivity("Click", "Click", "ui:Click",
                   "UiPath.UIAutomation.Activities", "ui", target="element",
                   backend="classic"),
    UiPathActivity("TypeInto", "Type Into", "ui:TypeInto",
                   "UiPath.UIAutomation.Activities", "ui", target="element",
                   backend="classic"),
    UiPathActivity("Check", "Check", "ui:Check",
                   "UiPath.UIAutomation.Activities", "ui", target="element",
                   backend="classic"),
    UiPathActivity("SelectItem", "Select Item", "ui:SelectItem",
                   "UiPath.UIAutomation.Activities", "ui", target="element",
                   backend="classic"),
    UiPathActivity("UiElementExists", "Element Exists", "ui:UiElementExists",
                   "UiPath.UIAutomation.Activities", "ui", target="element",
                   backend="classic"),
    UiPathActivity("GetAttribute", "Get Attribute", "ui:GetAttribute",
                   "UiPath.UIAutomation.Activities", "ui", target="element",
                   backend="classic"),
    UiPathActivity("WaitUiElementAppear", "Wait Ui Element Appear",
                   "ui:WaitUiElementAppear", "UiPath.UIAutomation.Activities",
                   "ui", target="element", backend="classic",
                   notes="Current approximation for UFT Sync; not identical to browser load completion."),

    # Scopes are generated as supporting structure rather than direct UFT mappings.
    UiPathActivity("BrowserScope", "Attach Browser", "ui:BrowserScope",
                   "UiPath.UIAutomation.Activities", "scope", target="browser",
                   backend="classic", status="supporting"),
    UiPathActivity("WindowScope", "Attach Window", "ui:WindowScope",
                   "UiPath.UIAutomation.Activities", "scope", target="window",
                   backend="classic", status="supporting"),

    # ------------------------------------------------------------------
    # Modern UI activities we have captured / intend to use.
    # Their exact XAML remains guarded by Activity Lab fixtures.
    # ------------------------------------------------------------------
    UiPathActivity("NApplicationCard", "Use Application/Browser",
                   "ui:NApplicationCard", "UiPath.UIAutomation.Activities",
                   "scope", target="application", backend="modern", status="planned"),
    UiPathActivity("NGoToUrl", "Go To URL", "ui:NGoToUrl",
                   "UiPath.UIAutomation.Activities", "browser",
                   target="browser", backend="modern", status="planned"),
    UiPathActivity("NGoBack", "Go Back", "ui:NGoBack",
                   "UiPath.UIAutomation.Activities", "browser",
                   target="browser", backend="modern", status="planned"),
    UiPathActivity("NCloseApplication", "Close Application/Tab",
                   "ui:NCloseApplication", "UiPath.UIAutomation.Activities",
                   "application", target="application", backend="modern",
                   status="planned"),

    # ------------------------------------------------------------------
    # Testing activities. Checkpoint semantics still require UFT resource data.
    # ------------------------------------------------------------------
    UiPathActivity("VerifyExpression", "Verify Expression",
                   "ui:VerifyExpression", "UiPath.Testing.Activities",
                   "testing", status="planned"),
    UiPathActivity("VerifyControlAttribute", "Verify Control Attribute",
                   "ui:VerifyControlAttribute", "UiPath.Testing.Activities",
                   "testing", target="element", status="planned"),
)


def _index(table: tuple[UiPathActivity, ...]) -> dict[str, UiPathActivity]:
    """Validate and index the catalog."""
    result: dict[str, UiPathActivity] = {}
    for entry in table:
        if entry.target not in TARGETS:
            raise ValueError(f"Unknown UiPath target {entry.target!r} for {entry.activity_id}.")
        if entry.backend not in BACKENDS:
            raise ValueError(f"Unknown UiPath backend {entry.backend!r} for {entry.activity_id}.")
        if entry.status not in STATUSES:
            raise ValueError(f"Unknown UiPath catalog status {entry.status!r} for {entry.activity_id}.")
        if entry.activity_id in result:
            raise ValueError(f"Duplicate UiPath activity ID {entry.activity_id}.")
        result[entry.activity_id] = entry
    return result


CATALOG: dict[str, UiPathActivity] = _index(TABLE)


def lookup(activity_id: str) -> UiPathActivity | None:
    """Return one UiPath activity specification."""
    return CATALOG.get(activity_id)


def require(activity_id: str) -> UiPathActivity:
    """Return a specification or fail fast for an invalid registry reference."""
    entry = lookup(activity_id)
    if entry is None:
        raise ValueError(f"UiPath activity {activity_id!r} is not in the migration activity catalog.")
    return entry


def describe(activity_ids: tuple[str, ...] | list[str]) -> list[dict]:
    """Serializable activity metadata for reports and diagnostics."""
    return [
        {
            "activity_id": entry.activity_id,
            "display_name": entry.display_name,
            "xaml_name": entry.xaml_name,
            "package": entry.package,
            "category": entry.category,
            "target": entry.target,
            "backend": entry.backend,
            "status": entry.status,
            "notes": entry.notes,
        }
        for entry in (require(activity_id) for activity_id in activity_ids)
    ]


def capabilities() -> dict[str, list[dict]]:
    """Catalog grouped by emitted/planned/supporting."""
    grouped = {status: [] for status in STATUSES}
    for activity in sorted(CATALOG.values(), key=lambda item: item.activity_id):
        grouped[activity.status].append({
            "activity_id": activity.activity_id,
            "display_name": activity.display_name,
            "package": activity.package,
            "category": activity.category,
            "target": activity.target,
            "backend": activity.backend,
        })
    return grouped
