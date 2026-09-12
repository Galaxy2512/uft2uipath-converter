from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser
from uft2uipath.parser.uft_script_nodes import (
    ClickOperation, IfOperation, UnknownScriptOperation,
)


def test_unexpected_terminators_preserve_following_statements():
    click = 'Browser("B").Page("P").WebButton("OK").Click'
    for terminator in ("Else", "End If", "EndIf"):
        result = UftVbScriptParser().parse(
            f"{click}\n{terminator}\n{click}"
        )
        assert len(result.operations) == 3
        before, unknown, after = result.operations
        assert isinstance(before, ClickOperation)
        assert isinstance(unknown, UnknownScriptOperation)
        assert unknown.raw == terminator
        assert unknown.line_number == 2
        assert "Unexpected block terminator" in unknown.reason
        assert isinstance(after, ClickOperation)
        assert after.line_number == 3


def test_duplicate_else_preserves_branch_and_following_statement():
    click = 'Browser("B").Page("P").WebButton("OK").Click'
    source = (
        'If Browser("B").Page("P").WebElement("Ready").Exist(10) Then\n'
        f"{click}\nElse\nElse\n{click}\nEnd If\n{click}"
    )
    result = UftVbScriptParser().parse(source)
    assert len(result.operations) == 2
    block, after = result.operations
    assert isinstance(block, IfOperation)
    assert len(block.then_operations) == 1
    assert len(block.else_operations) == 2
    unknown, branch_click = block.else_operations
    assert isinstance(unknown, UnknownScriptOperation)
    assert unknown.line_number == 4
    assert isinstance(branch_click, ClickOperation)
    assert isinstance(after, ClickOperation)
    assert after.line_number == 7
