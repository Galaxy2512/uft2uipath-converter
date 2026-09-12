from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser
from uft2uipath.parser.uft_script_nodes import (
    ClickOperation, IfOperation, LiteralValue, ParameterReference,
    SetTextOperation, UnknownValueExpression,
)

TARGET = 'Browser("B").Page("P").WebEdit("Username")'


def test_spaced_end_if_keeps_following_steps_outside_branch():
    for terminator in ("End  If", "End\tIf", "eNd   iF", "EndIf"):
        source = (
            'If Browser("B").Page("P").WebElement("Ready").Exist(10) Then\n'
            'Reporter.ReportEvent micPass, "Title", "OK"\n'
            'Else\nExitTest(-1)\n'
            f'{terminator}\n{TARGET}.Set Parameter("Input_User")\n'
            'Browser("B").Page("P").WebButton("Login").Click'
        )
        result = UftVbScriptParser().parse(source)
        assert len(result.operations) == 3
        block, set_user, click = result.operations
        assert isinstance(block, IfOperation)
        assert len(block.then_operations) == len(block.else_operations) == 1
        assert isinstance(set_user, SetTextOperation)
        assert isinstance(set_user.value, ParameterReference)
        assert isinstance(click, ClickOperation)
        assert click.line_number == 7


def test_unparsed_values_are_not_literals():
    for expression in (
        '"Admin" Parameter("Input_User")',
        '"Admin" & "User"',
        'sUser',
    ):
        source = f"{TARGET}.Set {expression}"
        operation = UftVbScriptParser().parse(source).operations[0]
        assert isinstance(operation, SetTextOperation)
        assert operation.raw == source
        assert isinstance(operation.value, UnknownValueExpression)
        assert operation.value.raw == expression
        assert not isinstance(operation.value, LiteralValue)


def test_string_literals_decode_doubled_quotes():
    for expression, expected in (
        ('"Admin"', "Admin"),
        ('""', ""),
        ('"Say ""hello"""', 'Say "hello"'),
    ):
        operation = UftVbScriptParser().parse(
            f"{TARGET}.Set {expression}"
        ).operations[0]
        assert isinstance(operation.value, LiteralValue)
        assert operation.value.value == expected
        assert operation.value.raw == expression


def test_spaced_unexpected_end_if_preserves_remainder():
    result = UftVbScriptParser().parse(
        f'End  If\n{TARGET}.Set "Admin"'
    )
    assert len(result.operations) == 2
    assert result.operations[0].raw == "End  If"
    assert isinstance(result.operations[1], SetTextOperation)
