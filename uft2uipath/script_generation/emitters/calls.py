"""Calls to user and library Functions/Subs: Invoke Workflow File of the compiled function.

The function itself is compiled by script_generation.user_functions. Here the
call site passes each argument, the context values the function needs (from the
caller's own arguments) and the failure flag, and reads the return value.
"""
import xml.etree.ElementTree as ET

from uft2uipath.mapping.operation_registry import maps
from uft2uipath.script_generation.emitter import (
    DIRECTIONS, FAILED_FLAG, RESULT_ARGUMENT, TYPES, UI, X, assign, expr, q,
)


def user_function(ctx, name, arguments):
    """The compiled function a call refers to, or ValueError naming why it cannot be called."""
    definition = ctx.function_definition(name)
    if definition is None or ctx.functions is None:
        where = ctx.function_origin(name) or "a function library not included in the export"
        raise ValueError(f"Function {name} is defined in {where}; library functions are not migrated yet.")
    kinds = [ctx.expression_type(argument) for argument in arguments]
    compiled = ctx.functions.compile(definition, name, kinds, ctx.bindings.get("objects", []),
                                     ctx.analysis.get("function_definitions") or {})
    if compiled.status == "blocked":
        raise ValueError(f"Function {name} from {compiled.origin} is not fully migrated: {compiled.reason}.")
    return compiled


def _assignable(ctx, argument, kind):
    """The caller's variable (or ByRef parameter) a ByRef argument refers to, if it is one."""
    if not isinstance(argument, dict) or argument.get("node_type") != "VariableReference":
        return None
    name = argument.get("name") or ""
    alias = ctx.aliases.get(name.casefold())
    if alias:
        return alias[0] if alias[2] == "byref" and alias[1] == kind else None
    return name if ctx.typed_variables.get(name) == kind else None


def result_type(ctx, name, arguments):
    """Type of the value a function call returns; blocks calls to functions returning nothing."""
    compiled = user_function(ctx, name, arguments)
    if compiled.result is None:
        raise ValueError(f"Function {name} returns no value.")
    return compiled.result


def emit_call(ctx, name, arguments, parent, display, want_result):
    """Emit the Invoke Workflow File of a call; returns the compiled function and its result variable."""
    compiled = user_function(ctx, name, arguments)
    if want_result and compiled.result is None:
        raise ValueError(f"Function {name} returns no value.")
    if compiled.empty:
        return compiled, None
    # Argument values may need activities of their own; they run before the call.
    bindings = []
    for argument, parameter in zip(arguments, compiled.parameters):
        kind = parameter["kind"]
        code = ctx.value(argument, kind, parent)
        if parameter["direction"] == "In":
            bindings.append(("In", kind, parameter["argument"], code))
            continue
        target = _assignable(ctx, argument, kind) if parameter["byref"] else None
        if target is None:
            # ByVal, or not a variable: the function changes a copy, as in VBScript.
            target = ctx.temporary("arg", kind)
            assign(parent, f"{display} / {parameter['vb']}", target, kind, code)
        bindings.append(("InOut", kind, parameter["argument"], target))
    invoke = ET.SubElement(parent, q("InvokeWorkflowFile", UI), {
        "DisplayName": display, "WorkflowFileName": compiled.workflow,
    })
    mapped = ET.SubElement(invoke, q("InvokeWorkflowFile.Arguments", UI))

    def bind(direction, kind, key, code):
        """Add one argument binding to the Invoke Workflow File."""
        ET.SubElement(mapped, q(DIRECTIONS[direction]), {
            q("TypeArguments", X): TYPES[kind], q("Key", X): key,
        }).text = expr(code)

    for binding in bindings:
        bind(*binding)
    for argument, kind in sorted(compiled.context_arguments.items()):
        if argument == FAILED_FLAG:
            bind("InOut", kind, argument, ctx.failure_flag())
            continue
        # The function reads a value from the test; the caller passes on its own argument.
        if ctx.arguments.get(argument, kind) != kind:
            raise ValueError(f"Function {name} needs {argument} as {kind}, the caller has another type.")
        ctx.arguments[argument] = kind
        bind(compiled.directions.get(argument, "In"), kind, argument, argument)
    result = None
    if compiled.result is not None and want_result:
        result = ctx.temporary("result", compiled.result)
        bind("Out", compiled.result, RESULT_ARGUMENT, result)
    if not len(mapped):
        invoke.remove(mapped)
    ctx.exits_test |= compiled.exits_test
    return compiled, result


@maps("CallOperation", uft="Name args / Call Name(args)", activities=("InvokeWorkflowFile",),
      notes="Calls a Function/Sub compiled into its own workflow; VBScript built-ins called as "
            "statements (MsgBox ...) are not mapped.")
def emit_call_statement(ctx, node, parent, trace, display):
    """A Function/Sub called as a statement: Invoke Workflow File, the return value discarded."""
    from uft2uipath.script_generation.emitters.functions import BUILTINS, FUNCTIONS
    name = node.get("name") or ""
    if name.lower() in BUILTINS and ctx.function_definition(name) is None:
        if name.lower() in FUNCTIONS:
            # The mapped built-ins only compute a value; called as a statement, it is discarded.
            trace.update(status="mapped_unverified", activity="(no effect)",
                         note=f"{name} is called as a statement; its result is discarded, as in VBScript.")
            return
        raise ValueError(f"Function {name} has no UiPath mapping as a statement.")
    compiled, _ = emit_call(ctx, name, node.get("arguments") or [], parent, display, want_result=False)
    if compiled.empty:
        trace.update(status="mapped_unverified", activity="(empty function)",
                     note=f"{name} has an empty body; nothing to call.")
    else:
        trace.update(status="mapped_unverified", activity="InvokeWorkflowFile",
                     note=f"Calls {compiled.workflow}, translated from {compiled.origin}.")
