# Tests If conditions beyond Exist: the parser splits And/Or/Not, comparisons and
# parentheses by VBScript precedence outside strings and calls; the emitter turns
# them into one typed C# condition, reading GetROProperty values with Get
# Attribute first, and removes everything a condition emitted when it blocks.
import pytest

from uft2uipath.mapping.acceptance import build_binding
from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser
from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_generation.emitter import UI, X, ComponentEmitter, q

ELEMENT = 'Browser("B").Page("P").WebElement("Role")'


def condition_of(text):
    return UftVbScriptParser().parse(f"If {text} Then\nEnd If").operations[0].condition


def shape(node):
    kind = type(node).__name__
    if kind == "LogicalCondition":
        return (node.operator, [shape(o) for o in node.operands])
    if kind == "NotCondition":
        return ("Not", shape(node.operand))
    if kind == "ComparisonCondition":
        return (type(node.left).__name__, node.operator, type(node.right).__name__)
    return kind


@pytest.mark.parametrize("text, expected", [
    ('(Parameter("B") = "IE")', ("ParameterReference", "=", "LiteralValue")),
    ('Parameter("U") = "" Or Parameter("U") = "<skip>"',
     ("Or", [("ParameterReference", "=", "LiteralValue")] * 2)),
    ('a = 1 Or b = 2 And c = 3',
     ("Or", [("VariableReference", "=", "LiteralValue"),
             ("And", [("VariableReference", "=", "LiteralValue")] * 2)])),
    ('Not Browser("B").Exist(0)', ("Not", "ExistCondition")),
    ('x = "a Or b = c"', ("VariableReference", "=", "LiteralValue")),
    ('Organization <> "x"', ("VariableReference", "<>", "LiteralValue")),
    (ELEMENT + '.GetROProperty("innertext") = Parameter("R")',
     ("ObjectPropertyReference", "=", "ParameterReference")),
])
def test_conditions_parse_by_vbscript_precedence(text, expected):
    assert shape(condition_of(text)) == expected


def bindings(analysis, selector=True):
    binding = build_binding(analysis, [])
    if selector:
        binding["objects"] = [{
            "uft": {"browser": "B", "page": "P", "object_type": "WebElement", "logical_name": "Role"},
            "selector": "<html title='T' /><webctrl id='role' />",
            "accepted_for_generation": True, "verification_status": "accepted_unverified",
            "input_method": "Simulate", "timeout_ms": 30000, "browser_type": "Edge",
        }]
    return binding


def emit(source, selector=True):
    analysis = analyze_source(source)
    return ComponentEmitter("1", analysis, bindings(analysis, selector)).generate()


def if_condition(root):
    return root.find(".//" + q("If")).attrib["Condition"]


def test_property_comparison_reads_attribute_then_compares_strings():
    source = f'If {ELEMENT}.GetROProperty("innertext") = Parameter("Role") Then\nWait 1\nEnd If'
    root, report = emit(source)
    assert report["status"] == "mapped_unverified"
    assert report["trace"][0]["activity"] == "GetAttribute + If"
    read = root.find(".//" + q("GetAttribute", UI))
    assert read.attrib["Attribute"] == "innertext"
    assert read.find(".//" + q("Target", UI)).attrib["Selector"] == \
        '["<html title=\'T\' /><webctrl id=\'role\' />"]'
    assert read.find(".//" + q("OutArgument")).text == "[property_1]"
    assert if_condition(root) == '[(System.Convert.ToString(property_1) ?? "") == (in_param_Role ?? "")]'
    variables = {v.attrib["Name"]: v.attrib[q("TypeArguments", X)] for v in root.iter(q("Variable"))}
    assert variables == {"property_1": "x:Object"}


def test_logical_and_not_conditions_combine_their_operands():
    root, report = emit(f'If Not {ELEMENT}.Exist(5) Or Parameter("A") <> "" Then\nEnd If')
    assert report["status"] == "mapped_unverified"
    assert if_condition(root) == '[(!(exists_1)) || ((in_param_A ?? "") != "")]'


@pytest.mark.parametrize("source, expected", [
    ("n = 1\nIf n >= 2 Then\nEnd If", "[(n) >= (2)]"),
    ('s = "a"\nIf s < "b" Then\nEnd If', '[string.CompareOrdinal((s ?? ""), "b") < 0]'),
    ("f = True\nIf f Then\nEnd If", "[f]"),
])
def test_typed_comparisons_and_boolean_values(source, expected):
    root, report = emit(source)
    assert report["status"] == "mapped_unverified"
    assert if_condition(root) == expected


@pytest.mark.parametrize("source, message", [
    ('If Parameter("A") = False Then\nEnd If', "needs an explicit conversion"),
    (f'If {ELEMENT}.GetROProperty("visible") = "True" Then\nEnd If', "No verified UiPath attribute"),
    ("f = True\nIf f > False Then\nEnd If", "only be compared for equality"),
])
def test_conditions_that_would_need_guessing_block(source, message):
    root, report = emit(source)
    assert report["status"] == "blocked"
    assert any(message in issue["message"] for issue in report["issues"])


def test_blocked_condition_leaves_no_partial_activities():
    # The property read succeeds, the comparison then fails: nothing of it may remain.
    source = f'If {ELEMENT}.GetROProperty("innertext") = 5 Then\nEnd If'
    root, report = emit(source)
    assert report["status"] == "blocked"
    assert root.find(".//" + q("GetAttribute", UI)) is None
    assert if_condition(root) == "[false]"


def test_property_read_in_assignment_and_without_selector():
    root, report = emit(f'x = {ELEMENT}.GetROProperty("value")')
    assert report["status"] == "mapped_unverified"
    assert root.find(".//" + q("GetAttribute", UI)).attrib["Attribute"] == "value"
    root, report = emit(f'x = {ELEMENT}.GetROProperty("value")', selector=False)
    assert report["status"] == "blocked"
    assert root.find(".//" + q("GetAttribute", UI)) is None
