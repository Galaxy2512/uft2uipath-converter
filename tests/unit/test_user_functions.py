# Tests library-function strategy A: Functions/Subs defined in the action or an
# associated library become their own workflows (Functions\Function_<Name>.xaml)
# called with Invoke Workflow File. Covers call parsing, definition lookup and
# library constants, typed parameters and return values, ByRef/ByVal semantics,
# context arguments (Environment, failure flag), and what must block.
import pytest

from uft2uipath.mapping.acceptance import build_binding
from uft2uipath.mapping.inventory import categorize
from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser
from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_analysis.function_definitions import (
    LOCAL_ORIGIN, definitions_for, library_constants, reachable,
)
from uft2uipath.script_generation import project_emitter
from uft2uipath.script_generation.emitter import FAILED_FLAG, RESULT_ARGUMENT, UI, X, ComponentEmitter, q
from uft2uipath.script_generation.user_functions import UserFunctions
from uft2uipath.studio_validation import validate_project

LIBRARY = "\n".join([
    'Dim IgnoredStringValue',
    'IgnoredStringValue = "<SKIP>"',
    'Function Add(a, b)',
    '  Add = a + b',
    'End Function',
    'Function GetCount',
    '  GetCount = 3',
    'End Function',
    'Sub Log(text)',
    '  Reporter.ReportEvent micFail, Environment("TestName"), text',
    'End Sub',
    'Function Bump(n)',
    '  n = n + 1',
    '  Bump = n',
    'End Function',
    'Function Copy(ByVal n)',
    '  n = n + 1',
    '  Copy = n',
    'End Function',
    'Function IsSkipped(value)',
    '  IsSkipped = value = IgnoredStringValue',
    'End Function',
    'Function Shadow(value)',
    '  Dim IgnoredStringValue',
    '  IgnoredStringValue = value',
    '  Shadow = IgnoredStringValue',
    'End Function',
    'Function Overwrite(value)',
    '  IgnoredStringValue = value',
    '  Overwrite = value',
    'End Function',
    'Function Broken(x)',
    '  Broken = CreateObject("Scripting.FileSystemObject")',
    'End Function',
    'Function Loop(x)',
    '  Loop = Loop(x)',
    'End Function',
    'Sub Nothing2()',
    'End Sub',
])


def emit(source, functions=None):
    analysis = analyze_source(source)
    analysis["function_definitions"] = definitions_for(source, [("Lib.qfl", LIBRARY)])
    functions = functions if functions is not None else UserFunctions()
    root, report = ComponentEmitter("1", analysis, build_binding(analysis, []), functions=functions).generate()
    return root, report, functions


def invokes(root):
    return [i for i in root.iter(q("InvokeWorkflowFile", UI))]


def arguments_of(invoke):
    container = invoke.find(q("InvokeWorkflowFile.Arguments", UI))
    return {} if container is None else {
        a.attrib[q("Key", X)]: (a.tag.split("}")[-1], a.text) for a in container}


# --- parsing and lookup -----------------------------------------------------------

@pytest.mark.parametrize("source, name, count", [
    ("InvokeFlightApp", "InvokeFlightApp", 0),
    ('OpenApp ("C:/app.exe")', "OpenApp", 1),
    ("Call Fill(a, b, c)", "Fill", 3),
    ('AddToTestResults micPass, "a", "b"', "AddToTestResults", 3),
])
def test_calls_as_statements_parse(source, name, count):
    op = UftVbScriptParser().parse(source).operations[0]
    assert type(op).__name__ == "CallOperation"
    assert (op.name, len(op.arguments)) == (name, count)


@pytest.mark.parametrize("source", ["ExitComponent", "On Error Resume Next", "Exit Function",
                                    "Call Foo 1", 'Wrapper().Browser("B").Page("P").Sync'])
def test_statements_that_only_look_like_calls_are_not_calls(source):
    op = UftVbScriptParser().parse(source).operations[0]
    assert type(op).__name__ != "CallOperation"


def test_definitions_follow_uft_lookup_order_and_keep_their_source():
    action = "Function Add(a, b)\n  Add = a - b\nEnd Function\nx = Add(1, 2)"
    definitions = definitions_for(action, [("Lib.qfl", LIBRARY)])
    assert definitions["add"]["origin"] == LOCAL_ORIGIN
    assert definitions["getcount"]["origin"] == "library Lib.qfl"
    assert definitions["getcount"]["source"].splitlines() == ["Function GetCount", "  GetCount = 3", "End Function"]
    assert library_constants(LIBRARY) == {"ignoredstringvalue": "<SKIP>"}


def test_reachable_functions_are_followed_through_calls():
    library = "Function A()\n  A = B()\nEnd Function\nFunction B()\n  B = 1\nEnd Function\nFunction C()\nEnd Function"
    definitions = definitions_for("x = A()", [("L", library)])
    assert reachable("x = A()", definitions) == ["a", "b"]
    # A call without parentheses is found too.
    assert reachable("y = C", definitions) == ["c"]


# --- calls and functions ------------------------------------------------------------

def test_statement_call_invokes_the_function_workflow():
    root, report, functions = emit('Log "broken"')
    assert report["status"] == "mapped_unverified"
    (invoke,) = invokes(root)
    assert invoke.attrib["WorkflowFileName"] == "Functions\\Function_Log.xaml"
    bound = arguments_of(invoke)
    assert bound["in_arg_text"] == ("InArgument", '["broken"]')
    # The Sub reports a failure and reads the test name: both come from the caller.
    assert bound[FAILED_FLAG] == ("InOutArgument", f"[{FAILED_FLAG}]")
    assert bound["in_env_TestName"] == ("InArgument", "[in_env_TestName]")
    assert report["arguments"]["in_env_TestName"] == "String"
    assert "Function_Log" in functions.workflows


def test_value_calls_return_a_typed_result():
    root, report, functions = emit("x = Add(1, 2)\nn = GetCount")
    assert report["status"] == "mapped_unverified"
    add, count = invokes(root)
    assert arguments_of(add)[RESULT_ARGUMENT] == ("OutArgument", "[result_1]")
    assert arguments_of(count)[RESULT_ARGUMENT][0] == "OutArgument"
    variables = {v.attrib["Name"]: v.attrib[q("TypeArguments", X)] for v in root.iter(q("Variable"))}
    assert variables["x"] == "x:Int32" and variables["n"] == "x:Int32"
    function = functions.compiled[next(k for k in functions.compiled if k[1] == "add")]
    assert function.result == "Int32"
    assert [p["argument"] for p in function.parameters] == ["in_arg_a", "in_arg_b"]


def test_byref_parameter_changes_the_callers_variable_but_not_a_literal():
    root, report, _ = emit("k = 1\ny = Bump(k)\nz = Bump(5)")
    assert report["status"] == "mapped_unverified"
    first, second = invokes(root)
    assert arguments_of(first)["io_arg_n"] == ("InOutArgument", "[k]")
    # A literal cannot change: the function gets a copy.
    assert arguments_of(second)["io_arg_n"][1].startswith("[arg_")


def test_byval_parameter_always_gets_a_copy():
    root, report, _ = emit("k = 1\ny = Copy(k)")
    assert report["status"] == "mapped_unverified"
    (invoke,) = invokes(root)
    assert arguments_of(invoke)["io_arg_n"][1] != "[k]"


def test_library_constants_are_read_and_can_be_shadowed_by_a_local_dim():
    root, report, functions = emit('a = IsSkipped("x")\nb = Shadow("y")')
    assert report["status"] == "mapped_unverified"
    is_skipped = functions.workflows["Function_IsSkipped"]
    conditions = [e.text for e in is_skipped.iter(q("InArgument")) if e.text and "<SKIP>" in e.text]
    assert conditions


@pytest.mark.parametrize("source, reason", [
    ('x = Overwrite("v")', "library global"),
    ('x = Broken("v")', "not fully migrated"),
    ('x = Loop("v")', "calls itself recursively"),
    ("x = Missing(1)", "not included in the export"),
    ('Log "a", "b"', "takes 1 arguments"),
    ("x = Nothing2()", "returns no value"),
])
def test_calls_that_cannot_be_migrated_block_with_the_reason(source, reason):
    root, report, _ = emit(source)
    assert report["status"] == "blocked"
    messages = [i["message"] for i in report["issues"]]
    assert any(reason in m for m in messages), messages
    assert not invokes(root)


def test_blocked_function_calls_count_as_library_blockers():
    issue = {"code": "unsupported_mapping",
             "message": "Function Broken from library Lib.qfl is not fully migrated: line 2: x."}
    assert categorize(issue) == "library"


def test_empty_sub_is_called_as_nothing():
    root, report, _ = emit("Call Nothing2()")
    assert report["status"] == "mapped_unverified"
    assert not invokes(root)
    assert report["trace"][0]["activity"] == "(empty function)"


def test_one_workflow_per_signature_shared_by_callers():
    functions = UserFunctions()
    emit("x = Add(1, 2)", functions)
    emit("y = Add(3, 4)", functions)
    emit('z = Add("a", "b")', functions)
    assert sorted(functions.workflows) == ["Function_Add", "Function_Add_2"]


def test_project_writes_function_workflows_and_stays_valid(tmp_path):
    source = 'Log "broken"'
    analysis = analyze_source(source)
    analysis["function_definitions"] = definitions_for(source, [("Lib.qfl", LIBRARY)])
    plan = project_emitter.ActionPlan("c/Action1", "Action_c_Action1", analysis, build_binding(analysis, []))
    test = project_emitter.TestPlan(1, "T", "resolved",
                                    [{"asset": "c", "action": "Action1", "order": 1, "action_name": "A"}])
    report = project_emitter.generate(tmp_path / "p", "P", {"c/Action1": plan}, [test])
    assert (tmp_path / "p" / "Functions" / "Function_Log.xaml").is_file()
    assert report["functions"]["Functions\\Function_Log.xaml"]["status"] == "mapped_unverified"
    assert validate_project(tmp_path / "p")["static_validation_passed"] is True
