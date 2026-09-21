"""Activity emitters, one handler per mapped node type (see mapping.operation_registry).

A handler is called as handler(ctx, node, parent, trace, display): ctx is the
ComponentEmitter, parent the XAML element to append to, trace the report entry
of the source line. Raising ValueError blocks the line; the caller records the
problem and emits a guard instead.

Condition handlers are called as handler(ctx, condition, parent, display, variable)
and must set the Boolean workflow variable the If then reads.
"""
from uft2uipath.script_generation.emitters import flow, functions, testing, ui  # noqa: F401
