"""Which function emits which UFT construct: the handler table.

The mapping registry says what a construct should become; this says who writes
it. A handler registers itself next to the code it emits:

    @emits("ClickOperation")
    def emit_click(ctx, node, parent, trace, display):
        ...

The registration is checked against mapping.operation_registry: the node type
must be in the table, its status must promise a handler, and no node type may
have two. A handler that is not in the table, or an entry marked supported
without a handler, is a programming error and fails the test suite.

The split keeps the dependency one-directional: the registry is data the
coverage reports can read, and only this module knows the emitters exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from uft2uipath.mapping.operation_registry import EMITTED, lookup


@dataclass(frozen=True)
class Handler:
    """The code that emits one node type.

    emit's signature follows the kind of the registry entry: an operation is
    called as (ctx, node, parent, trace, display), a condition as
    (ctx, node, parent, display), an expression as (ctx, node, parent).
    typer is set for expressions whose type depends on their operands:
    typer(ctx, node) -> value type; otherwise the entry's returns applies.
    """
    node_type: str
    emit: Callable
    typer: Callable | None = None


HANDLERS: dict[str, Handler] = {}


def emits(node_type: str, *, typer: Callable | None = None):
    """Register the decorated function as the emitter of one node type."""
    def decorate(handler):
        """Register the handler and return it unchanged."""
        entry = lookup(node_type)
        if entry is None:
            raise ValueError(f"{node_type} has no entry in mapping.operation_registry.")
        if entry.status not in EMITTED:
            raise ValueError(f"{node_type} is {entry.status}; only {'/'.join(EMITTED)} entries "
                             "have a handler.")
        if typer is not None and entry.kind != "expression":
            raise ValueError(f"{node_type} is a {entry.kind}; only an expression has a typer.")
        if node_type in HANDLERS:
            raise ValueError(f"Duplicate handler for {node_type}.")
        HANDLERS[node_type] = Handler(node_type, handler, typer)
        return handler
    return decorate


def handler_for(node_type: str | None) -> Handler | None:
    """The handler of a node type, after the emitter modules have registered theirs."""
    load_emitters()
    return HANDLERS.get(node_type)


def load_emitters() -> None:
    """Import the emitter modules so their @emits handlers are registered."""
    # Imported here, not at module level: the emitters import this module.
    import uft2uipath.script_generation.emitters  # noqa: F401
