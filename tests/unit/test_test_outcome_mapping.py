# Tests the test-outcome mappings: Reporter.ReportEvent -> Log Message (micFail
# logs an error, continues, and fails the calling test at its end), ExitTest ->
# a marked exception the test catches, typed String/Int32/Boolean assignments,
# and output parameters as Out arguments exposed per step by the test.
import xml.etree.ElementTree as ET

import pytest

from uft2uipath.mapping.acceptance import build_binding
from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser
from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_generation.emitter import (
    EXIT_FAILED_SUFFIX, EXIT_TEST_MARKER, FAILED_FLAG, UI, X, ComponentEmitter, q,
)
from uft2uipath.script_generation import project_emitter
from uft2uipath.script_generation.project_emitter import TEST_FAILED, _emit_test


def parse_one(source):
    return UftVbScriptParser().parse(source).operations[0]


def emit(source):
    analysis = analyze_source(source)
    return ComponentEmitter("1", analysis, build_binding(analysis, [])).generate()


def members(root):
    return {p.attrib["Name"]: p.attrib["Type"] for p in root.iter(q("Property", X))}


# --- parser -------------------------------------------------------------

def test_report_event_arguments_split_outside_strings_and_calls():
    op = parse_one('Reporter.ReportEvent micFail, "Step, 1", "a, b" & Environment.Value("X")')
    assert type(op).__name__ == "ReportEventOperation"
    assert op.status == "micFail"
    assert op.title.value == "Step, 1"
    assert [type(p).__name__ for p in op.message.parts] == ["LiteralValue", "EnvironmentReference"]


def test_report_event_with_wrong_argument_count_is_not_guessed():
    op = parse_one('Reporter.ReportEvent micFail, "only title"')
    assert type(op).__name__ == "UnknownScriptOperation"


@pytest.mark.parametrize("source, code", [("ExitTest", None), ("ExitTest(-1)", -1), ("ExitTest 2", 2)])
def test_exit_test_forms(source, code):
    op = parse_one(source)
    assert type(op).__name__ == "ExitTestOperation"
    assert (op.code.value if op.code else None) == code


def test_boolean_literals_and_environment_value_form():
    assert parse_one("x = True").value.value is True
    assert parse_one("x = false").value.value is False
    assert parse_one('x = Environment.Value("TestName")').value.name == "TestName"


# --- ReportEvent / ExitTest ---------------------------------------------------

@pytest.mark.parametrize("status, level", [("micPass", "Info"), ("micDone", "Info"),
                                           ("micWarning", "Warn"), ("0", "Info")])
def test_non_failing_report_logs_without_failure_flag(status, level):
    root, report = emit(f'Reporter.ReportEvent {status}, Environment("TestName"), "done"')
    assert report["status"] == "mapped_unverified"
    log = root.find(".//" + q("LogMessage", UI))
    assert log.attrib["Level"] == level
    assert log.attrib["Message"].startswith('["[')
    assert FAILED_FLAG not in report["arguments"]


def test_fail_report_logs_error_continues_and_sets_inout_flag():
    root, report = emit('Reporter.ReportEvent micFail, "Step", "broken"\nWait 1')
    assert report["status"] == "mapped_unverified"
    assert root.find(".//" + q("LogMessage", UI)).attrib["Level"] == "Error"
    flag = [a for a in root.iter(q("Assign")) if a.find(".//" + q("OutArgument")).text == f"[{FAILED_FLAG}]"]
    assert flag and flag[0].find(".//" + q("InArgument")).text == "[true]"
    assert members(root)[FAILED_FLAG] == "InOutArgument(x:Boolean)"
    assert report["argument_directions"] == {FAILED_FLAG: "InOut"}
    # Execution continues after the failure, as in UFT.
    assert root.find(".//" + q("Delay")) is not None


def test_unknown_report_status_blocks():
    root, report = emit('Reporter.ReportEvent micCustom, "Step", "x"')
    assert report["status"] == "blocked"


def test_exit_test_throws_marked_exception_carrying_the_failure_flag():
    root, report = emit("ExitTest(-1)")
    assert report["status"] == "mapped_unverified"
    assert report["exits_test"] is True
    exception = root.find(".//" + q("Throw")).attrib["Exception"]
    assert "System.ApplicationException" in exception
    assert EXIT_TEST_MARKER in exception and FAILED_FLAG in exception and EXIT_FAILED_SUFFIX in exception


# --- typed assignments ---------------------------------------------------------

def test_int_and_boolean_assignments_declare_typed_variables():
    root, report = emit("max = 101\nflag = True\ncopy = max")
    assert report["status"] == "mapped_unverified"
    variables = {v.attrib["Name"]: v.attrib[q("TypeArguments", X)] for v in root.iter(q("Variable"))}
    assert variables == {"max": "x:Int32", "flag": "x:Boolean", "copy": "x:Int32"}


@pytest.mark.parametrize("source, message", [
    ('x = 1\nx = "a"', "another type"),
    ("int = 1", "C# keyword"),
    ('sValue = "a"\nsvalue = "b"', "case-insensitive"),
])
def test_assignments_that_cannot_be_typed_safely_block(source, message):
    root, report = emit(source)
    assert report["status"] == "blocked"
    assert any(message in issue["message"] for issue in report["issues"])


# --- output parameters -------------------------------------------------------------

def test_output_parameter_is_an_out_argument_and_reads_see_it():
    root, report = emit('Parameter("Result") = "ok"\nx = Parameter("Result")')
    assert report["status"] == "mapped_unverified"
    assert members(root) == {"out_param_Result": "OutArgument(x:String)"}
    targets = [a.find(".//" + q("OutArgument")).text for a in root.iter(q("Assign"))]
    values = [a.find(".//" + q("InArgument")).text for a in root.iter(q("Assign"))]
    assert targets == ["[out_param_Result]", "[x]"]
    assert values == ['["ok"]', "[out_param_Result]"]


# --- test wiring --------------------------------------------------------------------

def workflow(**extra):
    return {"workflow": "Workflows\\A.xaml", "status": "mapped_unverified", **extra}


def unit(order):
    return {"asset": "c", "action": "Action1", "order": order, "action_name": "A"}


def test_test_shares_one_failure_flag_and_fails_at_its_end():
    workflows = {"c/Action1": workflow(
        arguments={"in_param_X": "String", "out_param_Y": "String", FAILED_FLAG: "Boolean"},
        argument_directions={"out_param_Y": "Out", FAILED_FLAG: "InOut"})}
    root, report = _emit_test(project_emitter.TestPlan(7, "T", "resolved", [unit(1), unit(2)]), workflows)
    assert report["arguments"] == {"in_param_X_1": "String", "out_param_Y_1": "String",
                                   "in_param_X_2": "String", "out_param_Y_2": "String"}
    assert report["argument_directions"] == {"out_param_Y_1": "Out", "out_param_Y_2": "Out"}
    assert members(root)["out_param_Y_1"] == "OutArgument(x:String)"
    flags = [a for a in root.iter(q("InOutArgument")) if a.attrib[q("Key", X)] == FAILED_FLAG]
    assert [a.text for a in flags] == [f"[{TEST_FAILED}]"] * 2
    sequence = root.find(q("Sequence"))
    assert sequence[0].find(q("Variable")).attrib["Name"] == TEST_FAILED
    final = sequence[-1]
    assert final.tag == q("If") and final.attrib["Condition"] == f"[{TEST_FAILED}]"
    assert root.find(".//" + q("TryCatch")) is None


def test_exit_test_is_caught_other_exceptions_rethrown():
    workflows = {"c/Action1": workflow(arguments={FAILED_FLAG: "Boolean"},
                                       argument_directions={FAILED_FLAG: "InOut"}, exits_test=True)}
    root, report = _emit_test(project_emitter.TestPlan(7, "T", "resolved", [unit(1)]), workflows)
    sequence = root.find(q("Sequence"))
    trycatch = sequence.find(q("TryCatch"))
    assert trycatch is not None
    assert trycatch.find(".//" + q("InvokeWorkflowFile", UI)) is not None
    catch = trycatch.find(".//" + q("Catch"))
    assert catch.attrib[q("TypeArguments", X)] == "s:ApplicationException"
    assert catch.find(".//" + q("Rethrow")) is not None
    assert EXIT_FAILED_SUFFIX in ET.tostring(catch, encoding="unicode")
    # The failure check runs after the steps, whether or not ExitTest stopped them.
    assert list(sequence).index(trycatch) < len(sequence) - 1
    assert sequence[-1].tag == q("If")
