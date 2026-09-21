"""Constructs taken from the real ALM_DEMO and Migration_BPT scripts."""
from uft2uipath.parser.uft_script_nodes import (
    ActivateOperation, AssignOperation, BackOperation, CheckpointOperation, ClickOperation,
    CloseOperation, ComparisonCondition, DataTableReference, DeclarationOperation, ExistCondition,
    FunctionDefinitionOperation, IfOperation, LiteralValue, NavigateOperation, NoEffectOperation,
    ObjectAssignmentOperation, ParameterAssignmentOperation, ParameterReference, SelectOperation,
    SetSecureTextOperation, SetTextOperation, SyncOperation, UnknownScriptOperation,
    VariableReference, WaitOperation,
)
from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser

WELCOME = 'Browser("Browser").Page("Welcome: Mercury")'


def parse(source):
    return UftVbScriptParser().parse(source).operations


def test_step_metadata_is_not_part_of_the_value():
    line = (f'{WELCOME}.WebEdit("userName").Set DataTable("Username", dtLocalSheet)'
            ' @@ hightlight id_;_Browser("Browser")_;_script infofile_;_userName0.inf_;_')

    [operation] = parse(line)

    assert isinstance(operation, SetTextOperation)
    assert isinstance(operation.value, DataTableReference)
    assert (operation.value.column, operation.value.sheet) == ("Username", "dtLocalSheet")
    # The original line is preserved for review.
    assert operation.raw == line


def test_optional_step_is_recorded_not_dropped():
    [operation] = parse('OptionalStep.Browser("B").Dialog("Internet Explorer").WinButton("&Yes").Click @@ x')

    assert isinstance(operation, ClickOperation)
    assert operation.optional is True
    assert [step["class"] for step in operation.target.path] == ["Browser", "Dialog", "WinButton"]
    assert operation.target.logical_name == "&Yes"


def test_desktop_hierarchies_are_parsed_like_web_ones():
    [operation] = parse('Dialog("Login").WinEdit("Agent Name:").Set Parameter("AgentName")')

    assert isinstance(operation, SetTextOperation)
    assert [(s["class"], s["name"]) for s in operation.target.path] == [
        ("Dialog", "Login"), ("WinEdit", "Agent Name:"),
    ]


def test_click_keeps_recorded_coordinates():
    [with_coordinates] = parse(f'{WELCOME}.Image("Sign-In").Click 14, 11')
    [plain] = parse(f'{WELCOME}.Image("Sign-In").Click')

    assert (with_coordinates.x, with_coordinates.y) == (14, 11)
    assert (plain.x, plain.y) == (None, None)


def test_browser_and_window_methods_become_typed_operations():
    operations = parse("\n".join([
        f'{WELCOME}.Sync',
        'Browser("B").Back',
        'Browser("B").Close',
        'Dialog("Login").Activate',
        'Browser("B").Navigate(URL)',
        'Browser("B").Page("P").WebList("fromPort").Select "London"',
        f'{WELCOME}.WebEdit("password").SetSecure "encoded"',
    ]))

    assert [type(operation) for operation in operations] == [
        SyncOperation, BackOperation, CloseOperation, ActivateOperation,
        NavigateOperation, SelectOperation, SetSecureTextOperation,
    ]
    assert isinstance(operations[4].value, VariableReference)
    assert operations[4].value.name == "URL"
    assert operations[5].value.value == "London"


def test_unmapped_methods_stay_unsupported_with_a_reason():
    [operation] = parse(f'{WELCOME}.WebEdit("userName").GetROProperty("value")')

    assert isinstance(operation, UnknownScriptOperation)
    assert "GetROProperty" in operation.reason


def test_declarations_assignments_and_wait():
    operations = parse('Option Explicit\nDim a, b\nURL = "http://newtours.demoaut.com/"\nWait 10')

    assert [type(operation) for operation in operations] == [
        DeclarationOperation, DeclarationOperation, AssignOperation, WaitOperation,
    ]
    assert operations[1].names == ["a", "b"]
    assert (operations[2].name, operations[2].value.value) == ("URL", "http://newtours.demoaut.com/")
    assert operations[3].seconds.value == 10


def test_elseif_chain_and_comparison_conditions():
    [operation] = parse("\n".join([
        'If sUser = "admin" Then',
        f'{WELCOME}.Image("Sign-In").Click',
        'ElseIf sUser <> "" Then',
        'Browser("B").Back',
        "Else",
        'Browser("B").Close',
        "End If",
    ]))

    assert isinstance(operation.condition, ComparisonCondition)
    assert operation.condition.operator == "="
    assert isinstance(operation.condition.left, VariableReference)
    assert isinstance(operation.condition.right, LiteralValue)
    [nested] = operation.else_operations
    assert isinstance(nested, IfOperation) and nested.condition.operator == "<>"
    assert isinstance(nested.then_operations[0], BackOperation)
    assert isinstance(nested.else_operations[0], CloseOperation)


def test_exist_condition_without_timeout_is_still_recognised():
    [operation] = parse(f'If {WELCOME}.WebEdit("userName").Exist Then\nBrowser("B").Close\nEnd If')

    assert isinstance(operation.condition, ExistCondition)
    assert operation.condition.target.logical_name == "userName"


def test_function_bodies_do_not_become_main_flow_steps():
    operations = parse("\n".join([
        f'{WELCOME}.Image("Sign-In").Click',
        "Function Helper(ByVal x, y)",
        f'{WELCOME}.WebEdit("userName").Set "only when called"',
        "Exit Function",
        "End Function",
        'Browser("B").Close',
    ]))

    assert [type(operation) for operation in operations] == [
        ClickOperation, FunctionDefinitionOperation, CloseOperation,
    ]
    definition = operations[1]
    assert (definition.keyword, definition.name, definition.parameters) == (
        "Function", "Helper", ["ByVal x", "y"])
    assert isinstance(definition.body[0], SetTextOperation)


def test_with_block_statements_get_their_object_and_original_line_numbers():
    operations = parse("\n".join([
        'With Browser("Browser")',
        ".Sync",
        '.Page("P").WebEdit("userName").Set "admin"',
        "End With",
        'Browser("B").Close',
    ]))

    assert [type(operation) for operation in operations] == [
        SyncOperation, SetTextOperation, CloseOperation,
    ]
    assert [operation.line_number for operation in operations] == [2, 3, 5]
    assert operations[1].target.browser == "Browser"
    assert operations[1].target.logical_name == "userName"


def test_checkpoints_output_parameters_and_object_assignments_are_named():
    operations = parse("\n".join([
        'Browser("F").Page("S").Check CheckPoint("Frankfurt")',
        'Parameter("OrderNumber") = "A1"',
        "Set oItem = Nothing",
        "Randomize",
    ]))

    assert [type(operation) for operation in operations] == [
        CheckpointOperation, ParameterAssignmentOperation, ObjectAssignmentOperation,
        NoEffectOperation,
    ]
    assert operations[0].name == "Frankfurt"
    assert operations[0].target.page == "S"
    assert (operations[1].name, operations[1].value.value) == ("OrderNumber", "A1")
    assert (operations[2].name, operations[2].expression) == ("oItem", "Nothing")


def test_concatenated_values_keep_every_part():
    [operation] = parse(f'{WELCOME}.WebEdit("userName").Set Parameter("First") & " " & sUser')

    assert [type(part) for part in operation.value.parts] == [
        ParameterReference, LiteralValue, VariableReference,
    ]


def test_comments_after_code_are_not_parsed_as_statements():
    operations = parse('Browser("B").Close \' close the browser\n\' Browser("B").Back')

    assert [type(operation) for operation in operations] == [CloseOperation]
