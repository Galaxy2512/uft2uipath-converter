"""Control flow, variables and statements that emit nothing."""
import xml.etree.ElementTree as ET

from uft2uipath.mapping.operation_registry import maps
from uft2uipath.script_generation.emitter import (
    CSHARP_KEYWORDS, IDENTIFIER_NAME, assign, expr, q, throw,
)


@maps("IfOperation", uft="If ... Then ... Else ... End If", activities=("If",))
def emit_if(ctx, node, parent, trace, display):
    line = node.get("line_number")
    start = len(parent)
    try:
        code = ctx.condition(node.get("condition"), parent, display)
        # VBScript evaluates every operand, so the activities all run before the If.
        activities = [element.tag.split("}")[-1] for element in parent[start:]]
        trace.update(status="mapped_unverified", activity=" + ".join(activities + ["If"]))
    except (ValueError, ET.ParseError) as exc:
        del parent[start:]
        ctx.problem(node, "unresolved_condition", str(exc))
        parent.append(throw(f"Component {ctx.component_id}, line {line}: unresolved condition."))
        code = "false"
    branch = ET.SubElement(parent, q("If"), {"DisplayName": display, "Condition": expr(code)})
    for field, prop_name in (("then_operations", "If.Then"), ("else_operations", "If.Else")):
        prop = ET.SubElement(branch, q(prop_name))
        body = ET.SubElement(prop, q("Sequence"), {"DisplayName": field})
        for child in node.get(field, []):
            ctx.map_operation(child, body)


_ORDERING = {"<": "<", ">": ">", "<=": "<=", ">=": ">="}


@maps("ComparisonCondition", uft="a = b, a <> b, a < b ...", activities=(), kind="condition",
      notes="Both sides must have the same static type; VBScript's implicit conversions are "
            "not reproduced. Strings compare ordinally, as VBScript's default binary compare.")
def emit_comparison(ctx, node, parent, display):
    left, right, operator = node.get("left"), node.get("right"), node.get("operator")
    kinds = {kind for kind in (ctx.value_type(left), ctx.value_type(right)) if kind}
    if len(kinds) > 1:
        raise ValueError(f"Comparing {' and '.join(sorted(kinds))} needs an explicit conversion.")
    kind = kinds.pop() if kinds else "String"
    a, b = ctx.value(left, kind, parent), ctx.value(right, kind, parent)
    if kind == "String":
        # An unset argument is null in C# but Empty ("") in VBScript; literals never are.
        a, b = (code if side.get("node_type") == "LiteralValue" else f"({code} ?? \"\")"
                for side, code in ((left, a), (right, b)))
        if operator in _ORDERING:
            return f"string.CompareOrdinal({a}, {b}) {_ORDERING[operator]} 0"
    elif kind == "Boolean" and operator not in ("=", "<>"):
        raise ValueError("Booleans can only be compared for equality.")
    else:
        a, b = f"({a})", f"({b})"
    return f"{a} {'==' if operator == '=' else '!=' if operator == '<>' else operator} {b}"


@maps("LogicalCondition", uft="a And b, a Or b", activities=(), kind="condition")
def emit_logical(ctx, node, parent, display):
    joiner = {"and": " && ", "or": " || "}.get((node.get("operator") or "").lower())
    if joiner is None or len(node.get("operands") or []) < 2:
        raise ValueError(f"Logical operator {node.get('operator')!r} is not supported.")
    return joiner.join(f"({ctx.condition(operand, parent, display)})" for operand in node["operands"])


@maps("NotCondition", uft="Not a", activities=(), kind="condition")
def emit_not(ctx, node, parent, display):
    return f"!({ctx.condition(node.get('operand'), parent, display)})"


@maps("DeclarationOperation", uft="Dim / Option Explicit", activities=(), status="no_effect",
      notes="Declarations become workflow variables where they are used.")
def emit_declaration(ctx, node, parent, trace, display):
    trace.update(status="mapped_unverified", activity="(declaration)")


@maps("NoEffectOperation", uft="Randomize and similar", activities=(), status="no_effect")
def emit_no_effect(ctx, node, parent, trace, display):
    trace.update(status="mapped_unverified", activity="(no effect)",
                 note=f"{node.get('keyword')} has no migrated equivalent.")


@maps("FunctionDefinitionOperation", uft="Function / Sub definition", activities=(),
      status="no_effect", notes="The definition is not part of the flow; calls to it block instead.")
def emit_function_definition(ctx, node, parent, trace, display):
    trace.update(status="mapped_unverified", activity="(definition not migrated)")


def _variable(ctx, name, kind):
    """Declare a workflow variable for a VBScript variable of one static type."""
    if not IDENTIFIER_NAME.fullmatch(name or ""):
        raise ValueError("Assignment target is not a simple variable name.")
    if name in CSHARP_KEYWORDS or name in ctx.arguments:
        raise ValueError(f"{name} collides with a C# keyword or a workflow argument.")
    # VBScript names ignore case; C# names do not.
    other = next((known for known in ctx.typed_variables
                  if known != name and known.casefold() == name.casefold()), None)
    if other:
        raise ValueError(f"{name} is also written as {other}; VBScript names are case-insensitive.")
    if ctx.typed_variables.get(name, kind) != kind:
        raise ValueError(f"{name} is already used with another type.")
    ctx.typed_variables[name] = kind
    ctx.assigned.add((name, kind))


@maps("AssignOperation", uft="x = value", activities=("Assign",),
      notes="String, Int32 and Boolean; a variable keeps one type for the whole action.")
def emit_assign(ctx, node, parent, trace, display):
    if not IDENTIFIER_NAME.fullmatch(node.get("name") or ""):
        raise ValueError("Assignment target is not a simple variable name.")
    kind = ctx.value_type(node.get("value")) or "String"
    code = ctx.value(node.get("value"), kind, parent)
    _variable(ctx, node.get("name"), kind)
    assign(parent, display, node["name"], kind, code)
    trace.update(status="mapped_unverified", activity="Assign")


@maps("ParameterAssignmentOperation", uft='Parameter("X") = value', activities=("Assign",),
      notes="Writes an Out argument of the action workflow; the test exposes it per step.")
def emit_output_parameter(ctx, node, parent, trace, display):
    binding = ctx.references.get(("outputs", node.get("name")))
    if binding is None:
        raise ValueError(f"Missing Out binding for output parameter {node.get('name')}.")
    target, kind = binding
    assign(parent, display, target, kind, ctx.value(node.get("value"), kind, parent))
    trace.update(status="mapped_unverified", activity="Assign (output parameter)")


@maps("WaitOperation", uft="Wait n", activities=("Delay",))
def emit_wait(ctx, node, parent, trace, display):
    seconds = (node.get("seconds") or {}).get("value")
    if (node.get("seconds") or {}).get("node_type") != "LiteralValue" or type(seconds) is not int or not 0 < seconds <= 86400:
        raise ValueError("Wait requires a positive literal number of seconds.")
    ET.SubElement(parent, q("Delay"), {
        "DisplayName": display, "Duration": expr(f"TimeSpan.FromSeconds({seconds})"),
    })
    trace.update(status="mapped_unverified", activity="Delay")
