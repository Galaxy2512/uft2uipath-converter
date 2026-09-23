"""VBScript built-in functions and arithmetic as typed C# expressions.

Each function states which argument types it accepts and what it returns, so
a call is either translated with its VBScript semantics or blocked with the
reason. Strings are null-safe: an unset argument is null in C#, "" in VBScript.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from uft2uipath.script_generation.emitter import NonNull
from uft2uipath.script_generation.emitters import calls
from uft2uipath.script_generation.handlers import emits


NUMERIC = ("Int32", "Double")


def _s(code: str) -> str:
    """Null-safe string: literals and values that cannot be null stay as they are."""
    if isinstance(code, NonNull) or (len(code) > 1 and code[0] == code[-1] == '"' and '" + ' not in code):
        return code
    return f'({code} ?? "")'


@dataclass(frozen=True)
class Function:
    """How one VBScript built-in is translated: accepted argument types, result type and C# template."""
    # "String": any value, converted as VBScript would; "Int32"; "Number": Int32
    # or Double as given; "DateTime"; "Any": any type, passed as is.
    params: tuple[str, ...]
    # A type, or a function of the argument types.
    returns: str | Callable[[list[str]], str]
    emit: Callable[[list[str], list[str]], str]
    optional: int = 0
    notes: str = ""


def _cint(codes, kinds):
    """CInt/CLng: VBScript rounds half to even, as Convert.ToInt32 does; True is -1."""
    a, kind = codes[0], kinds[0]
    return {"Int32": a, "Double": f"System.Convert.ToInt32({a})",
            "Boolean": f"({a} ? -1 : 0)"}.get(kind, f"System.Convert.ToInt32(System.Convert.ToDouble({a}))")


def _cdbl(codes, kinds):
    """CDbl for each source type; True is -1."""
    a, kind = codes[0], kinds[0]
    return {"Double": a, "Int32": f"(double)({a})",
            "Boolean": f"({a} ? -1.0 : 0.0)"}.get(kind, f"System.Convert.ToDouble({a})")


def _mid(codes, kinds):
    """Mid(s, start[, length]) with VBScript's 1-based start and "" past the end."""
    s, start = _s(codes[0]), codes[1]
    if len(codes) == 2:
        return f'({start} > {s}.Length ? "" : {s}.Substring({start} - 1))'
    return (f'({start} > {s}.Length ? "" : '
            f'{s}.Substring({start} - 1, System.Math.Min({codes[2]}, {s}.Length - {start} + 1)))')


FUNCTIONS: dict[str, Function] = {
    "len": Function(("String",), "Int32", lambda c, k: f"{_s(c[0])}.Length"),
    "lcase": Function(("String",), "String", lambda c, k: f"{_s(c[0])}.ToLower()"),
    "ucase": Function(("String",), "String", lambda c, k: f"{_s(c[0])}.ToUpper()"),
    # VBScript trims spaces only, not tabs or line breaks.
    "trim": Function(("String",), "String", lambda c, k: f"{_s(c[0])}.Trim(' ')"),
    "ltrim": Function(("String",), "String", lambda c, k: f"{_s(c[0])}.TrimStart(' ')"),
    "rtrim": Function(("String",), "String", lambda c, k: f"{_s(c[0])}.TrimEnd(' ')"),
    "left": Function(("String", "Int32"), "String",
                     lambda c, k: f"{_s(c[0])}.Substring(0, System.Math.Min({c[1]}, {_s(c[0])}.Length))"),
    "right": Function(("String", "Int32"), "String",
                      lambda c, k: f"{_s(c[0])}.Substring({_s(c[0])}.Length - System.Math.Min({c[1]}, {_s(c[0])}.Length))"),
    "mid": Function(("String", "Int32", "Int32"), "String", _mid, optional=1),
    "instr": Function(("String", "String"), "Int32",
                      lambda c, k: f"{_s(c[0])}.IndexOf({_s(c[1])}, System.StringComparison.Ordinal) + 1",
                      notes="Two-argument form only; a start position or compare mode blocks."),
    "instrrev": Function(("String", "String"), "Int32",
                         lambda c, k: f"{_s(c[0])}.LastIndexOf({_s(c[1])}, System.StringComparison.Ordinal) + 1",
                         notes="Two-argument form only."),
    "replace": Function(("String", "String", "String"), "String",
                        lambda c, k: f"(string.IsNullOrEmpty({c[1]}) ? {_s(c[0])} : "
                                     f"{_s(c[0])}.Replace({c[1]}, {_s(c[2])}))"),
    "cstr": Function(("String",), "String", lambda c, k: _s(c[0])),
    "cint": Function(("Any",), "Int32", _cint, notes="Rounds half to even, as VBScript does."),
    "clng": Function(("Any",), "Int32", _cint, notes="Int32 range, not VBScript's Long promotion."),
    "cdbl": Function(("Any",), "Double", _cdbl),
    "int": Function(("Number",), "Int32",
                    lambda c, k: c[0] if k[0] == "Int32" else f"(int)System.Math.Floor({c[0]})",
                    notes="Returns Int32; VBScript keeps a Double subtype with the same value."),
    "fix": Function(("Number",), "Int32",
                    lambda c, k: c[0] if k[0] == "Int32" else f"(int)System.Math.Truncate({c[0]})"),
    "abs": Function(("Number",), lambda k: k[0], lambda c, k: f"System.Math.Abs({c[0]})"),
    "rnd": Function((), "Double", lambda c, k: "System.Random.Shared.NextDouble()",
                    notes="Randomize seeds from the clock in UFT; a shared random generator is equivalent."),
    "chr": Function(("Int32",), "String", lambda c, k: f"((char)({c[0]})).ToString()",
                    notes="UTF-16 code; VBScript uses the ANSI code page above 127."),
    "space": Function(("Int32",), "String", lambda c, k: f"new string(' ', {c[0]})"),
    "date": Function((), "DateTime", lambda c, k: "System.DateTime.Today"),
    "now": Function((), "DateTime", lambda c, k: "System.DateTime.Now"),
    **{name: Function(("DateTime",), "Int32", lambda c, k, part=part: f"({c[0]}).{part}")
       for name, part in (("day", "Day"), ("month", "Month"), ("year", "Year"),
                          ("hour", "Hour"), ("minute", "Minute"), ("second", "Second"))},
    # VBScript counts Sunday as 1 by default; .NET's DayOfWeek counts it as 0.
    "weekday": Function(("DateTime",), "Int32", lambda c, k: f"((int)({c[0]}).DayOfWeek + 1)",
                        notes="Default first day (Sunday) only; a firstdayofweek argument blocks."),
}


# VBScript built-ins not mapped yet; any other name is a user or library function.
BUILTINS = set(FUNCTIONS) | set("""
    asc ascb ascw array cbool cbyte ccur cdate chrb chrw createobject csng date dateadd datediff
    datepart dateserial datevalue day escape eval exp filter formatcurrency formatdatetime
    formatnumber formatpercent getlocale getobject getref hex hour inputbox instrb isarray isdate
    isempty isnull isnumeric isobject join lbound leftb lenb loadpicture log midb minute month
    monthname msgbox now oct rgb rightb round scriptengine second setlocale sgn sin sqr split
    strcomp string strreverse tan time timer timeserial timevalue typename ubound unescape
    vartype weekday weekdayname year atn cos
""".split())


def _spec(ctx, node) -> Function:
    """Catalog entry of a call, or ValueError naming why it cannot be mapped:
    a built-in not mapped yet, or a library/action function not migrated yet.
    """
    name = node.get("name") or ""
    spec = FUNCTIONS.get(name.lower())
    if spec is None:
        if name.lower() in BUILTINS:
            raise ValueError(f"Function {name} has no UiPath mapping.")
        where = ctx.function_origin(name) or "a function library not included in the export"
        raise ValueError(f"Function {name} is defined in {where}; library functions are not migrated yet.")
    count = len(node.get("arguments") or [])
    if not len(spec.params) - spec.optional <= count <= len(spec.params):
        raise ValueError(f"Function {name} with {count} arguments has no UiPath mapping.")
    return spec


def _argument_types(ctx, node, spec):
    """Types the arguments of a call are used with; blocks arguments the function cannot take."""
    kinds = []
    for param, argument in zip(spec.params, node.get("arguments") or []):
        kind = ctx.expression_type(argument)
        if param == "String":
            kind = "String"
        elif param == "Int32" and kind != "Int32":
            raise ValueError(f"Function {node.get('name')} needs an Int32 argument, not {kind}.")
        elif param == "Number" and kind not in NUMERIC:
            raise ValueError(f"Function {node.get('name')} needs a number, not {kind}.")
        elif param == "DateTime" and kind != "DateTime":
            raise ValueError(f"Function {node.get('name')} needs a date, not {kind}.")
        kinds.append(kind)
    return kinds


def _user_call(ctx, node) -> bool:
    """True for a call to a Function defined in the action or an associated library.

    A user definition wins over a VBScript built-in of the same name, as in VBScript.
    """
    return ctx.function_definition(node.get("name") or "") is not None


def _function_type(ctx, node):
    """Result type of a call (the registry's typer for FunctionCall)."""
    if _user_call(ctx, node):
        return calls.result_type(ctx, node["name"], node.get("arguments") or [])
    spec = _spec(ctx, node)
    kinds = _argument_types(ctx, node, spec)
    return spec.returns(kinds) if callable(spec.returns) else spec.returns


@emits("FunctionCall", typer=_function_type)
def emit_function(ctx, node, parent):
    """C# code for a call: a built-in inline, a user function through Invoke Workflow File.

    A String built-in result is never null.
    """
    if _user_call(ctx, node):
        if parent is None:
            raise ValueError(f"Calling {node['name']} needs an activity before this statement; "
                             "not supported here.")
        _, result = calls.emit_call(ctx, node["name"], node.get("arguments") or [], parent,
                                    f"Call {node['name']}", want_result=True)
        return result
    spec = _spec(ctx, node)
    kinds = _argument_types(ctx, node, spec)
    codes = [ctx.as_string(argument, parent) if param == "String" else ctx.value(argument, kind, parent)
             for param, kind, argument in zip(spec.params, kinds, node.get("arguments") or [])]
    code = spec.emit(codes, kinds)
    # Every String built-in returns a string, never null.
    return NonNull(code) if _function_type(ctx, node) == "String" else code


def _binary_type(ctx, node):
    """Result type of an arithmetic operation, following VBScript: / and ^ give
    Double, integer division and Mod need Int32, + on two strings concatenates.
    Mixed or non-numeric operands block rather than guess VBScript's conversions.
    """
    operator = node.get("operator")
    left, right = ctx.expression_type(node.get("left")), ctx.expression_type(node.get("right"))
    if operator == "+" and left == right == "String":
        return "String"
    if left not in NUMERIC or right not in NUMERIC:
        raise ValueError(f"{operator} on {left} and {right} relies on VBScript's implicit conversion; "
                         "not reproduced.")
    if operator in ("/", "^"):
        return "Double"
    if operator in ("\\", "Mod"):
        if left == right == "Int32":
            return "Int32"
        raise ValueError(f"{operator} rounds non-integer operands in VBScript; not reproduced.")
    return "Int32" if left == right == "Int32" else "Double"


@emits("BinaryExpression", typer=_binary_type)
def emit_binary(ctx, node, parent):
    """C# code for an arithmetic operation of the type _binary_type found."""
    kind, operator = _binary_type(ctx, node), node.get("operator")
    left, right = node.get("left"), node.get("right")
    a = ctx.value(left, ctx.expression_type(left), parent)
    b = ctx.value(right, ctx.expression_type(right), parent)
    if kind == "String":
        return NonNull(f"{a} + {b}")
    if operator == "/":
        return f"((double)({a}) / ({b}))"
    if operator == "^":
        return f"System.Math.Pow({a}, {b})"
    if operator == "\\":
        return f"(({a}) / ({b}))"
    if operator == "Mod":
        return f"(({a}) % ({b}))"
    return f"(({a}) {operator} ({b}))"


def _unary_type(ctx, node):
    """Type of -x: the operand's numeric type."""
    kind = ctx.expression_type(node.get("operand"))
    if kind not in NUMERIC:
        raise ValueError(f"Negating {kind} relies on VBScript's implicit conversion; not reproduced.")
    return kind


@emits("UnaryExpression", typer=_unary_type)
def emit_unary(ctx, node, parent):
    """C# negation of a number."""
    operand = node.get("operand")
    return f"(-({ctx.value(operand, _unary_type(ctx, node), parent)}))"
