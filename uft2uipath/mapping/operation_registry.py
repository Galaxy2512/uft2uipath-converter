"""Bridge between neutral UFT operations and the UiPath activities emitted for them.

Each parser node type has one entry: what the UFT statement means, which UiPath
activities it becomes, and how far that mapping is trusted. Entries with a
handler are emitted by script_generation.emitters, which register themselves
with @maps; the rest document what is still missing, so coverage reports and
the emitter read the same source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# supported: a handler emits it. no_effect: nothing to emit, by design.
# planned: a known mapping, not implemented yet. requires_strategy: needs a
# design decision first. unsupported: no target semantics identified.
STATUSES = ("supported", "no_effect", "planned", "requires_strategy", "unsupported")


@dataclass(frozen=True)
class OperationMapping:
    """Registry entry for one parser node type.

    node_type is the parser class name; uft and activities describe the
    mapping for people and reports; handler emits it (None while planned).
    """
    node_type: str
    uft: str
    activities: tuple[str, ...]
    status: str
    requires_selector: bool = False
    handler: Callable | None = None
    notes: str = ""
    # "operation": a statement. "condition": the Boolean test of an If.
    # "expression": a value; returns names its type.
    kind: str = "operation"
    returns: str | None = None
    # For expressions whose type depends on their operands: typer(ctx, node) -> type.
    typer: Callable | None = None


REGISTRY: dict[str, OperationMapping] = {}


def _register(entry: OperationMapping) -> None:
    """Add an entry; a handler may replace a planned entry but not another handler."""
    if entry.status not in STATUSES:
        raise ValueError(f"Unknown mapping status {entry.status!r} for {entry.node_type}.")
    if (entry.handler is None) == (entry.status in ("supported", "no_effect")):
        raise ValueError(f"{entry.node_type}: only supported/no_effect entries have a handler.")
    if entry.node_type in REGISTRY and REGISTRY[entry.node_type].handler is not None:
        raise ValueError(f"Duplicate handler for {entry.node_type}.")
    REGISTRY[entry.node_type] = entry


def maps(node_type: str, *, uft: str, activities: tuple[str, ...], status: str = "supported",
         requires_selector: bool = False, notes: str = "", kind: str = "operation",
         returns: str | None = None, typer: Callable | None = None):
    """Register the decorated function as the emitter of one node type."""
    def decorate(handler):
        """Register the handler and return it unchanged."""
        _register(OperationMapping(node_type, uft, tuple(activities), status,
                                   requires_selector, handler, notes, kind, returns, typer))
        return handler
    return decorate


def lookup(node_type: str | None) -> OperationMapping | None:
    """Entry for a node type, after the emitter modules have registered their handlers."""
    _load_emitters()
    return REGISTRY.get(node_type)


def capabilities() -> dict[str, list[dict]]:
    """Registry entries grouped by status, for coverage reports."""
    _load_emitters()
    grouped: dict[str, list[dict]] = {status: [] for status in STATUSES}
    for entry in sorted(REGISTRY.values(), key=lambda e: e.node_type):
        grouped[entry.status].append({
            "node_type": entry.node_type, "kind": entry.kind, "uft": entry.uft,
            "activities": list(entry.activities),
            "requires_selector": entry.requires_selector, "notes": entry.notes,
        })
    return grouped


def _load_emitters() -> None:
    # Emitter modules register on import; imported lazily to avoid a cycle.
    """Import the emitter modules so their @maps handlers are registered."""
    import uft2uipath.script_generation.emitters  # noqa: F401


# Known operations without an emitter yet. Moving one to "supported" means
# writing its handler with @maps, which replaces the entry below.
for _entry in (
    OperationMapping("NavigateOperation", "Browser.Navigate", ("NGoToUrl",), "planned",
                     requires_selector=True),
    OperationMapping("CloseOperation", "Browser/Window.Close", ("NCloseApplication",), "planned",
                     requires_selector=True),
    OperationMapping("ActivateOperation", "Window.Activate", ("NApplicationCard",), "planned",
                     requires_selector=True),
    OperationMapping("BackOperation", "Browser.Back", ("NGoBack",), "planned",
                     requires_selector=True),
    OperationMapping("CheckpointOperation", "Checkpoint", ("VerifyExpression",), "requires_strategy",
                     notes="Checkpoint criteria live in the UFT resource files, not in the script."),
    OperationMapping("ObjectAssignmentOperation", "Set x = ...", (), "requires_strategy",
                     notes="Object references (CreateObject, test objects) have no direct equivalent."),
    OperationMapping("UnknownScriptOperation", "(unparsed statement)", (), "unsupported"),
):
    _register(_entry)
