from uft2uipath.parser.uft_script_nodes import (
    ClickOperation,
    EnvironmentReference,
    ExitTestOperation,
    IfOperation,
    ParameterReference,
    ReportEventOperation,
    SetSecureTextOperation,
    SetTextOperation,
    UnknownScriptOperation,
)
from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser


def test_parse_login_component_script():
    source = """
Option Explicit
Dim sUser, sPassword

If Browser("OrangeHRM_BrowserObject").Page("OrangeHRM_PageObject").WebElement("Innertext_WebElement").Exist(10) Then
    Reporter.ReportEvent micPass, Environment("TestName"), "URL loaded."
Else
    Reporter.ReportEvent micFail, Environment("TestName"), "URL failed."
    ExitTest(-1)
End If

Browser("OrangeHRM_BrowserObject").Page("OrangeHRM_PageObject").WebEdit("username_WebEdit").Set Parameter("Input_User")
Browser("OrangeHRM_BrowserObject").Page("OrangeHRM_PageObject").WebEdit("password_WebEdit").SetSecure Parameter("Input_Password")
Browser("OrangeHRM_BrowserObject").Page("OrangeHRM_PageObject").WebButton("Login_WebButton").Click
"""

    result = UftVbScriptParser().parse(source)

    # Option Explicit and Dim are currently preserved as unsupported.
    assert isinstance(result.operations[0], UnknownScriptOperation)
    assert isinstance(result.operations[1], UnknownScriptOperation)

    if_operation = result.operations[2]

    assert isinstance(if_operation, IfOperation)
    assert if_operation.condition is not None
    assert if_operation.condition.target.logical_name == "Innertext_WebElement"
    assert if_operation.condition.target.object_type == "WebElement"
    assert if_operation.condition.timeout.value == 10

    assert isinstance(
        if_operation.then_operations[0],
        ReportEventOperation,
    )
    assert isinstance(
        if_operation.then_operations[0].title,
        EnvironmentReference,
    )

    assert isinstance(
        if_operation.else_operations[0],
        ReportEventOperation,
    )
    assert isinstance(
        if_operation.else_operations[1],
        ExitTestOperation,
    )
    assert if_operation.else_operations[1].code.value == -1

    set_user = result.operations[3]

    assert isinstance(set_user, SetTextOperation)
    assert set_user.target.logical_name == "username_WebEdit"
    assert isinstance(set_user.value, ParameterReference)
    assert set_user.value.name == "Input_User"

    set_password = result.operations[4]

    assert isinstance(set_password, SetSecureTextOperation)
    assert set_password.target.logical_name == "password_WebEdit"
    assert isinstance(set_password.value, ParameterReference)
    assert set_password.value.name == "Input_Password"

    click = result.operations[5]

    assert isinstance(click, ClickOperation)
    assert click.target.logical_name == "Login_WebButton"


def test_unknown_statement_is_not_discarded():
    source = 'CustomFunction "value"'

    result = UftVbScriptParser().parse(source)

    assert len(result.operations) == 1
    assert isinstance(
        result.operations[0],
        UnknownScriptOperation,
    )
    assert result.operations[0].raw == 'CustomFunction "value"'


def test_parse_literal_set_value():
    source = (
        'Browser("B").Page("P")'
        '.WebEdit("Username").Set "Admin"'
    )

    result = UftVbScriptParser().parse(source)

    operation = result.operations[0]

    assert isinstance(operation, SetTextOperation)
    assert operation.value.value == "Admin"