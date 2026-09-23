"""Control flow (If, Select Case, conditions), variables and statements that emit nothing."""
import xml.etree.ElementTree as ET

from uft2uipath.script_generation.emitter import (
    CSHARP_KEYWORDS, IDENTIFIER_NAME, assign, expr, q, throw,
)
from uft2uipath.script_generation.handlers import emits


@emits("IfOperation")
def emit_if(ctx, node, parent, trace, display):
    """If ... Then ... Else: the condition's activities first, then an If with the
    C# condition. A condition that cannot be mapped blocks only the If line.
    """
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


@emits("SelectCaseOperation")
def emit_select_case(ctx, node, parent, trace, display):
    """Select Case: the subject once into a variable, then an If/Else chain of the Cases.

    Each Case compares the subject for equality with its values (Or'ed), exactly
    as VBScript tries them top to bottom; Case Else is the last Else.
    """
    subject = node.get("subject")
    kind = ctx.expression_type(subject)
    # Every Case value must compare with the subject; check before emitting anything.
    for case in node.get("cases") or []:
        for value in case.get("values") or []:
            value_kind = ctx.expression_type(value)
            if value_kind != kind:
                raise ValueError(f"Case value {value.get('raw')!r} is {value_kind}, "
                                 f"the Select Case subject is {kind}.")
    code = ctx.value(subject, kind, parent)
    variable = ctx.temporary("case", kind)
    ctx.assigned.add((variable, kind))
    assign(parent, display + " / subject", variable, kind, code)
    current = parent
    for case in node.get("cases") or []:
        comparisons = [{"node_type": "ComparisonCondition", "operator": "=", "raw": case.get("raw"),
                        "left": {"node_type": "VariableReference", "name": variable, "raw": variable},
                        "right": value} for value in case.get("values") or []]
        condition = comparisons[0] if len(comparisons) == 1 else {
            "node_type": "LogicalCondition", "operator": "Or", "operands": comparisons, "raw": case.get("raw")}
        case_display = f"UFT line {case.get('line_number')}: Case"
        branch = ET.SubElement(current, q("If"), {
            "DisplayName": case_display, "Condition": expr(ctx.condition(condition, current, case_display)),
        })
        then = ET.SubElement(ET.SubElement(branch, q("If.Then")), q("Sequence"),
                             {"DisplayName": (case.get("raw") or "").strip()})
        for child in case.get("operations") or []:
            ctx.map_operation(child, then)
        current = ET.SubElement(ET.SubElement(branch, q("If.Else")), q("Sequence"), {"DisplayName": "else"})
    for child in node.get("else_operations") or []:
        ctx.map_operation(child, current)
    trace.update(status="mapped_unverified", activity="Assign + If (Select Case)")


_ORDERING = {"<": "<", ">": ">", "<=": "<=", ">=": ">="}


@emits("ComparisonCondition")
def emit_comparison(ctx, node, parent, display):
    """C# comparison of two values of the same static type.

    Strings compare ordinally and treat null as ""; numbers compare
    directly; Booleans only for equality.
    """
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


@emits("LogicalCondition")
def emit_logical(ctx, node, parent, display):
    """C# && / || of the operands. VBScript evaluates every operand; the
    activities they need all run before the If, so nothing is skipped.
    """
    joiner = {"and": " && ", "or": " || "}.get((node.get("operator") or "").lower())
    if joiner is None or len(node.get("operands") or []) < 2:
        raise ValueError(f"Logical operator {node.get('operator')!r} is not supported.")
    return joiner.join(f"({ctx.condition(operand, parent, display)})" for operand in node["operands"])


@emits("NotCondition")
def emit_not(ctx, node, parent, display):
    """C# negation of a condition."""
    return f"!({ctx.condition(node.get('operand'), parent, display)})"


@emits("DeclarationOperation")
def emit_declaration(ctx, node, parent, trace, display):
    """Dim / Option Explicit: nothing to emit; variables are declared where they are assigned."""
    trace.update(status="mapped_unverified", activity="(declaration)")


@emits("NoEffectOperation")
def emit_no_effect(ctx, node, parent, trace, display):
    """Statements without a migrated effect, e.g. Randomize: nothing to emit."""
    trace.update(status="mapped_unverified", activity="(no effect)",
                 note=f"{node.get('keyword')} has no migrated equivalent.")


@emits("FunctionDefinitionOperation")
def emit_function_definition(ctx, node, parent, trace, display):
    """A Function/Sub definition is not part of the flow; calls to it block instead."""
    trace.update(status="mapped_unverified", activity="(definition not migrated)")


def _variable(ctx, name, kind):
    """Declare a workflow variable for a VBScript variable of one static type."""
    if not IDENTIFIER_NAME.fullmatch(name or ""):
        raise ValueError("Assignment target is not a simple variable name.")
    alias = ctx.aliases.get(name.casefold())
    if alias and alias[2] == "constant":
        # Without a local Dim the function would change the library global for every caller.
        raise ValueError(f"{name} is a library global set at load time; changing it inside "
                         "a function is not supported.")
    if alias:
        raise ValueError(f"{name} is a function parameter; it cannot be assigned here.")
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


@emits("AssignOperation")
def emit_assign(ctx, node, parent, trace, display):
    """x = value: Assign to a workflow variable typed from the value (String, Int32, Boolean, Double)."""
    if not IDENTIFIER_NAME.fullmatch(node.get("name") or ""):
        raise ValueError("Assignment target is not a simple variable name.")
    kind = ctx.value_type(node.get("value")) or "String"
    code = ctx.value(node.get("value"), kind, parent)
    if ctx.function and node["name"].casefold() == ctx.function["name"].casefold():
        # FunctionName = value sets the function's return value.
        assign(parent, display, ctx.function_result(kind), kind, code)
        trace.update(status="mapped_unverified", activity="Assign (return value)")
        return
    alias = ctx.aliases.get(node["name"].casefold())
    if alias and alias[2] == "byref":
        # A parameter the body assigns is InOut: the caller's variable changes as in VBScript.
        if alias[1] != kind:
            raise ValueError(f"Parameter {node['name']} is {alias[1]}, assigned {kind}.")
        assign(parent, display, alias[0], kind, code)
        trace.update(status="mapped_unverified", activity="Assign (ByRef parameter)")
        return
    _variable(ctx, node.get("name"), kind)
    assign(parent, display, node["name"], kind, code)
    trace.update(status="mapped_unverified", activity="Assign")


@emits("ParameterAssignmentOperation")
def emit_output_parameter(ctx, node, parent, trace, display):
    """Parameter("X") = value: Assign to the Out argument of output parameter X."""
    binding = ctx.references.get(("outputs", node.get("name")))
    if binding is None:
        raise ValueError(f"Missing Out binding for output parameter {node.get('name')}.")
    target, kind = binding
    assign(parent, display, target, kind, ctx.value(node.get("value"), kind, parent))
    trace.update(status="mapped_unverified", activity="Assign (output parameter)")


@emits("WaitOperation")
def emit_wait(ctx, node, parent, trace, display):
    """Wait n: Delay of n seconds; only a positive literal is accepted."""
    seconds = (node.get("seconds") or {}).get("value")
    if (node.get("seconds") or {}).get("node_type") != "LiteralValue" or type(seconds) is not int or not 0 < seconds <= 86400:
        raise ValueError("Wait requires a positive literal number of seconds.")
    ET.SubElement(parent, q("Delay"), {
        "DisplayName": display, "Duration": expr(f"TimeSpan.FromSeconds({seconds})"),
    })
    trace.update(status="mapped_unverified", activity="Delay")
