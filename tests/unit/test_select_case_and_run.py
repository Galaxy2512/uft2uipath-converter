# Tests Select Case (subject evaluated once, Cases as an If/Else chain, Case Is
# and Case To blocked) and SystemUtil.Run (Start Process with file, parameters
# and directory; only the default "open" operation).
import pytest

from uft2uipath.mapping.acceptance import build_binding
from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser
from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_generation.emitter import UI, X, ComponentEmitter, q

SELECT = "\n".join([
    'Select Case Parameter("Class")',
    '  Case "Economy"',
    '    x = 1',
    '  Case "Business", "First"',
    '    x = 2',
    '  Case Else',
    '    x = 3',
    'End Select',
])


def emit(source):
    analysis = analyze_source(source)
    return ComponentEmitter("1", analysis, build_binding(analysis, [])).generate()


def children(element):
    return [child.tag.split("}")[-1] for child in element]


def test_select_case_parses_cases_and_else():
    op = UftVbScriptParser().parse(SELECT).operations[0]
    assert type(op).__name__ == "SelectCaseOperation"
    assert [len(case.values) for case in op.cases] == [1, 2]
    assert [case.line_number for case in op.cases] == [2, 4]
    assert len(op.else_operations) == 1


@pytest.mark.parametrize("source", [
    "Select Case x\n  Case 1\n    y = 1",  # no End Select
    "Select Case x\n  y = 0\n  Case 1\n    y = 1\nEnd Select",  # statement before the first Case
    "Case 1",
])
def test_malformed_select_case_is_preserved_as_unknown(source):
    op = UftVbScriptParser().parse(source).operations[0]
    assert type(op).__name__ == "UnknownScriptOperation"


def test_select_case_becomes_subject_variable_and_if_chain():
    root, report = emit(SELECT)
    assert report["status"] == "mapped_unverified"
    sequence = root.find(q("Sequence"))
    assert children(sequence)[-2:] == ["Assign", "If"]
    first = sequence[-1]
    assert first.attrib["Condition"] == '[(case_1 ?? "") == "Economy"]'
    second = first.find(q("If.Else") + "/" + q("Sequence") + "/" + q("If"))
    assert second.attrib["Condition"] == '[((case_1 ?? "") == "Business") || ((case_1 ?? "") == "First")]'
    case_else = second.find(q("If.Else") + "/" + q("Sequence"))
    assert children(case_else) == ["Assign"]
    variables = {v.attrib["Name"]: v.attrib[q("TypeArguments", X)] for v in root.iter(q("Variable"))}
    assert variables["case_1"] == "x:String"


@pytest.mark.parametrize("case, message", [
    ("Case Is > 5", "Case Is"),
    ("Case 1 To 3", "Case Is"),
    ("Case 7", "Case value '7' is Int32"),
])
def test_select_cases_that_would_need_guessing_block(case, message):
    root, report = emit(f'Select Case Parameter("Class")\n  {case}\n    x = 1\nEnd Select')
    assert report["status"] == "blocked"
    assert any(message in issue["message"] for issue in report["issues"]), report["issues"]
    assert root.find(".//" + q("If")) is None


def test_system_util_run_starts_the_process():
    root, report = emit('SystemUtil.Run "C:\\app.exe", "-x", "C:\\work", "open", 3')
    assert report["status"] == "mapped_unverified"
    start = root.find(".//" + q("StartProcess", UI))
    # Expressions stay attributes until studio_xaml writes them (see the test below).
    assert start.attrib["FileName"] == '["C:\\\\app.exe"]'
    assert start.attrib["Arguments"] == '["-x"]'
    assert start.attrib["WorkingDirectory"] == '["C:\\\\work"]'
    assert "not reproduced" in report["trace"][0]["note"]


def test_system_util_run_with_another_operation_blocks():
    root, report = emit('SystemUtil.Run "C:\\doc.txt", "", "", "print"')
    assert report["status"] == "blocked"
    assert root.find(".//" + q("StartProcess", UI)) is None


def test_start_process_properties_become_csharp_arguments(tmp_path):
    from uft2uipath.script_generation.emitter import write_xaml
    import xml.etree.ElementTree as ET
    root, _ = emit('SystemUtil.Run "C:\\app.exe", "-x"')
    write_xaml(tmp_path / "w.xaml", root)
    start = ET.parse(tmp_path / "w.xaml").getroot().find(".//" + q("StartProcess", UI))
    assert "FileName" not in start.attrib and "Arguments" not in start.attrib
    assert [child.tag.split("}")[-1] for child in start] == ["StartProcess.FileName", "StartProcess.Arguments"]
