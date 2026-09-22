"""Activity emitters, one handler per mapped node type (see mapping.operation_registry).

A handler is called as handler(ctx, node, parent, trace, display): ctx is the
ComponentEmitter, parent the XAML element to append to, trace the report entry
of the source line. Raising ValueError blocks the line; the caller records the
problem and emits a guard instead.

Condition handlers are called as handler(ctx, condition, parent, display) and
return C# Boolean code; expression handlers as handler(ctx, node, parent) and
return C# code. Activities they need (Element Exists, Get Attribute, a function
call) go into parent before the statement that uses the value.

Modules: ui (UI actions and checks), flow (If, conditions, assignments),
testing (ReportEvent, ExitTest), functions (VBScript built-ins, arithmetic),
calls (user and library Functions/Subs), system (SystemUtil.Run).
"""
from uft2uipath.script_generation.emitters import calls, flow, functions, system, testing, ui  # noqa: F401
