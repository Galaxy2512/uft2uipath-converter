# Tests VBScript value expressions: the parser builds calls and arithmetic by
# VBScript precedence, and the emitter translates built-in functions and
# operators to typed, null-safe C#; library functions and conversions VBScript
# would do implicitly block with their reason instead of being guessed.
import pytest

from uft2uipath.mapping.acceptance import build_binding
from uft2uipath.mapping.inventory import categorize
from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser
from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_generation.emitter import X, ComponentEmitter, literal, q


def shape(node):
    kind = type(node).__name__
    if kind == "BinaryExpression":
        return f"({shape(node.left)} {node.operator} {shape(node.right)})"
    if kind == "UnaryExpression":
        return f"-{shape(node.operand)}"
    if kind == "FunctionCall":
        return f"{node.name}[{', '.join(shape(a) for a in node.arguments)}]"
    if kind == "LiteralValue":
        return repr(node.value)
    if kind == "VariableReference":
        return node.name
    return kind


@pytest.mark.parametrize("text, expected", [
    ("Int((max-min+1)*Rnd+min)", "Int[((((max - min) + 1) * Rnd[]) + min)]"),
    ('"#" + CStr(i)', "('#' + CStr[i])"),
    ("a - b - c", "((a - b) - c)"),
    ("-x * 2", "(-x * 2)"),
    ("-x ^ 2", "-(x ^ 2)"),
    ("a Mod 3 + 1", "((a Mod 3) + 1)"),
    ("10 \\ 3", "(10 \\ 3)"),
    ("Modulo + 1", "(Modulo + 1)"),
    ('Left(s, InStrRev(s, "\\") - 1)', "Left[s, (InStrRev[s, '\\\\'] - 1)]"),
    ("1.5 * n", "(1.5 * n)"),
    ('"a-b"', "'a-b'"),
])
def test_values_parse_by_vbscript_precedence(text, expected):
    assert shape(UftVbScriptParser()._parse_value(text)) == expected


def emit(source, library_functions=None):
    analysis = analyze_source(source)
    if library_functions:
        analysis["library_functions"] = library_functions
    return ComponentEmitter("1", analysis, build_binding(analysis, [])).generate()


def assigned(root):
    return {a.find(".//" + q("OutArgument")).text[1:-1]: a.find(".//" + q("InArgument")).text[1:-1]
            for a in root.iter(q("Assign"))}


def variables(root):
    return {v.attrib["Name"]: v.attrib[q("TypeArguments", X)] for v in root.iter(q("Variable"))}


def test_string_functions_are_null_safe_and_typed():
    root, report = emit('p = Parameter("Path")\n'
                        'n = Len(p)\n'
                        'dir = Left(p, InStrRev(p, "\\") - 1)\n'
                        'u = UCase(Trim(p))\n'
                        'r = Replace(p, "\\", "/")')
    assert report["status"] == "mapped_unverified"
    code = assigned(root)
    assert code["n"] == '(p ?? "").Length'
    assert code["dir"] == ('(p ?? "").Substring(0, System.Math.Min((((p ?? "").LastIndexOf("\\\\", '
                           'System.StringComparison.Ordinal) + 1) - (1)), (p ?? "").Length))')
    assert code["u"] == "(p ?? \"\").Trim(' ').ToUpper()"
    assert code["r"] == '(string.IsNullOrEmpty("\\\\") ? (p ?? "") : (p ?? "").Replace("\\\\", "/"))'
    assert variables(root) == {"p": "x:String", "n": "x:Int32", "dir": "x:String",
                               "u": "x:String", "r": "x:String"}


def test_random_integer_idiom_and_numeric_types():
    root, report = emit("min = 2\nmax = 10\ni = Int((max-min+1)*Rnd+min)\nd = max / 4\nk = max \\ 4")
    assert report["status"] == "mapped_unverified"
    code = assigned(root)
    assert code["i"].startswith("(int)System.Math.Floor(") and "System.Random.Shared.NextDouble()" in code["i"]
    assert code["d"] == "((double)(max) / (4))"
    assert code["k"] == "((max) / (4))"
    assert variables(root)["i"] == "x:Int32" and variables(root)["d"] == "x:Double"


def test_vbscript_conversions_in_concatenation_and_cstr():
    root, report = emit('i = 5\nf = True\ns = "#" + CStr(i)\nt = "n=" & i & ", " & f')
    assert report["status"] == "mapped_unverified"
    code = assigned(root)
    assert code["s"] == '"#" + (i).ToString()'
    assert code["t"] == '"n=" + (i).ToString() + ", " + (f).ToString()'


@pytest.mark.parametrize("source, category", [
    ('x = "a" + 1', "expression"),
    ("x = 1.5 Mod 2", "expression"),
    ("x = StrReverse(\"a\")", "expression"),
    ('x = InStr(2, "abc", "b")', "expression"),
    ('x = Excel_ReadValue("f", 1)', "library"),
])
def test_unsafe_or_unknown_expressions_block_with_category(source, category):
    root, report = emit(source)
    assert report["status"] == "blocked"
    issue = next(i for i in report["issues"] if i["code"] == "unsupported_mapping")
    assert categorize(issue) == category


def test_library_function_names_its_library():
    root, report = emit('x = Excel_ReadValue("f", 1)', {"excel_readvalue": "[QC] Resources/Lib.qfl"})
    assert any("[QC] Resources/Lib.qfl" in i["message"] for i in report["issues"])


def test_function_defined_in_the_action_is_named():
    root, report = emit("Function Check_File(p)\nEnd Function\nx = Check_File(\"a\")")
    assert any("defined in this action" in i["message"] for i in report["issues"])


def test_double_literals():
    assert literal(1.5) == "1.5"
    assert literal(2.0) == "2.0"
