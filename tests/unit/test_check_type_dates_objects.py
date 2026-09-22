# Tests check boxes and radio buttons (Set -> Check/Uncheck), Type (Type Into
# without clearing), date functions (DateTime), FileSystemObject methods (System.IO)
# and built-ins called as statements (no effect).
import pytest

from uft2uipath.mapping.acceptance import build_binding
from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_generation.emitter import UI, X, ComponentEmitter, q

WINDOW = 'Window("W")'


def bindings(analysis, objects=()):
    binding = build_binding(analysis, [])
    binding["objects"] = [{
        "uft": {"path": [{"class": "Window", "name": "W"}, {"class": kind, "name": name}]},
        "kind": "desktop", "selector": f"<wnd title='W' /><ctrl name='{name}' />", "verified": True,
        "input_method": "Simulate", "timeout_ms": 30000,
    } for kind, name in objects]
    return binding


def emit(source, objects=()):
    analysis = analyze_source(source)
    return ComponentEmitter("1", analysis, bindings(analysis, objects)).generate()


def assigned(root):
    return {a.find(".//" + q("OutArgument")).text[1:-1]: a.find(".//" + q("InArgument")).text[1:-1]
            for a in root.iter(q("Assign"))}


@pytest.mark.parametrize("statement, action", [
    (f'{WINDOW}.WinCheckBox("Keep").Set "ON"', "Check"),
    (f'{WINDOW}.WinCheckBox("Keep").Set ("off")', "Uncheck"),
    (f'{WINDOW}.WinRadioButton("Keep").Set', "Check"),
])
def test_check_boxes_and_radio_buttons_become_check(statement, action):
    kind = "WinRadioButton" if "Radio" in statement else "WinCheckBox"
    root, report = emit(statement, [(kind, "Keep")])
    assert report["status"] == "mapped_unverified"
    check = root.find(".//" + q("Check", UI))
    assert check.attrib["Action"] == action
    # Desktop actions attach to their window, like Click and Type Into.
    assert root.find(".//" + q("WindowScope", UI)) is not None


def test_check_box_state_must_be_a_literal():
    root, report = emit(f'state = "ON"\n{WINDOW}.WinCheckBox("Keep").Set state', [("WinCheckBox", "Keep")])
    assert report["status"] == "blocked"
    assert any("literal ON or OFF" in i["message"] for i in report["issues"])


def test_type_appends_without_clearing_the_field():
    root, report = emit(f'{WINDOW}.WinEdit("Date").Type "121220"', [("WinEdit", "Date")])
    assert report["status"] == "mapped_unverified"
    typed = root.find(".//" + q("TypeInto", UI))
    assert typed.attrib["EmptyField"] == "False"
    assert typed.attrib["Text"] == '["121220"]'


def test_type_with_a_key_constant_blocks():
    root, report = emit(f'{WINDOW}.WinEdit("Date").Type micTab', [("WinEdit", "Date")])
    assert report["status"] == "blocked"
    assert any("micTab" in i["message"] for i in report["issues"])


def test_date_functions_are_typed_datetime_and_int():
    root, report = emit("d = Date\nm = Month(Date)\nw = Weekday(Now)")
    assert report["status"] == "mapped_unverified"
    code = assigned(root)
    assert code == {"d": "System.DateTime.Today", "m": "(System.DateTime.Today).Month",
                    "w": "((int)(System.DateTime.Now).DayOfWeek + 1)"}
    variables = {v.attrib["Name"]: v.attrib[q("TypeArguments", X)] for v in root.iter(q("Variable"))}
    assert variables["d"] == "s:DateTime" and variables["m"] == "x:Int32"


def test_dates_as_text_block_because_formatting_differs():
    root, report = emit("s = CStr(Date)")
    assert report["status"] == "blocked"
    assert any("formatted differently" in i["message"] for i in report["issues"])


CHECK_FILE = "\n".join([
    'Set fso = CreateObject("Scripting.FileSystemObject")',
    'p = "C:\\app.exe"',
    'found = fso.FileExists(p)',
    'name = fso.GetBaseName(p)',
    'Set fso = Nothing',
])


def test_file_system_object_methods_become_system_io():
    root, report = emit(CHECK_FILE)
    assert report["status"] == "mapped_unverified"
    code = assigned(root)
    assert code["found"] == "System.IO.File.Exists(p)"
    assert code["name"] == 'System.IO.Path.GetFileNameWithoutExtension((p ?? ""))'
    activities = [t.get("activity") for t in report["trace"]]
    assert activities[0] == "(no effect)" and activities[-1] == "(no effect)"


@pytest.mark.parametrize("source, reason", [
    ('Set sh = CreateObject("WScript.Shell")', "has no UiPath mapping"),
    ('Set o = Browser("B")', "other than CreateObject"),
    ("x = fso.FileExists(p)", "holds no supported object"),
    ('Set fso = CreateObject("Scripting.FileSystemObject")\nx = fso.DeleteFolder("a")', "has no UiPath mapping"),
])
def test_unsupported_objects_block_with_the_reason(source, reason):
    root, report = emit(source)
    assert report["status"] == "blocked"
    assert any(reason in i["message"] for i in report["issues"]), report["issues"]


def test_pure_built_in_called_as_statement_has_no_effect_but_msgbox_blocks():
    root, report = emit('x = 1\nCStr(x)')
    assert report["status"] == "mapped_unverified"
    assert report["trace"][-1]["activity"] == "(no effect)"
    root, report = emit('MsgBox "hi"')
    assert report["status"] == "blocked"
