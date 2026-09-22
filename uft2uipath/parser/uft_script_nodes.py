"""
UFT Script AST Nodes

Responsibility
--------------
Defines a neutral representation of executable UFT/VBScript operations.

These objects represent what the UFT script means, not how it was
written and not how it will later look in UiPath.

Example
-------
UFT:

    Browser("Browser").Page("Page").WebButton("Login").Click

Neutral representation:

    ClickOperation(
        target=ObjectReference(
            object_type="WebButton",
            logical_name="Login",
        )
    )

Later, the UiPath mapper can translate this into a Click activity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ======================================================================
# VALUE EXPRESSIONS
# ======================================================================


@dataclass
class ValueExpression:
    """
    Base class for values used by UFT operations.
    """

    raw: str


@dataclass
class UnknownValueExpression(ValueExpression):
    """Preserve an expression that has not been interpreted."""
    reason: str = "Unsupported or malformed value expression"


@dataclass
class LiteralValue(ValueExpression):
    """
    Represents a literal value such as:

        "Admin"
        10
        -1
    """

    value: Any = None


@dataclass
class ParameterReference(ValueExpression):
    """
    Represents:

        Parameter("Input_User")
    """

    name: str = ""


@dataclass
class ConcatenationExpression(ValueExpression):
    """
    Represents VBScript string concatenation: a & b & c.
    """

    parts: list[ValueExpression] = field(default_factory=list)


@dataclass
class VariableReference(ValueExpression):
    """
    Represents a plain VBScript variable used as a value.
    """

    name: str = ""


@dataclass
class FunctionCall(ValueExpression):
    """
    Represents a call used as a value: Len(x), CStr(n), Rnd, or a library function.
    """

    name: str = ""
    arguments: list[ValueExpression] = field(default_factory=list)


@dataclass
class MethodCall(ValueExpression):
    """
    Represents a method of an object held in a variable: fso.FileExists(path).
    """

    object: str = ""
    method: str = ""
    arguments: list[ValueExpression] = field(default_factory=list)


@dataclass
class BinaryExpression(ValueExpression):
    """
    Represents arithmetic: a + b, a - b, a * b, a / b, a \\ b, a Mod b, a ^ b.
    """

    operator: str = ""
    left: ValueExpression | None = None
    right: ValueExpression | None = None


@dataclass
class UnaryExpression(ValueExpression):
    """
    Represents a negated value: -a.
    """

    operator: str = ""
    operand: ValueExpression | None = None


@dataclass
class DataTableReference(ValueExpression):
    """
    Represents DataTable("Column", sheet): a value taken from the run data.
    """

    column: str = ""
    sheet: str | None = None


@dataclass
class EnvironmentReference(ValueExpression):
    """
    Represents:

        Environment("TestName")
    """

    name: str = ""


# ======================================================================
# OBJECT REFERENCES
# ======================================================================


@dataclass
class ObjectReference:
    """
    Represents one logical UFT Object Repository target.

    The complete hierarchy is preserved because UiPath selectors may
    need Browser, Page and control information. It can be any application:
    web (Browser/Page/...) or desktop (Window/Dialog/...).

    Example:

        Browser("MyBrowser")
            .Page("MyPage")
            .WebEdit("UserName")
    """

    browser: str | None = None
    page: str | None = None
    object_type: str | None = None
    logical_name: str | None = None
    raw: str = ""
    # Full hierarchy as written, including desktop classes the web fields cannot hold.
    path: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ObjectPropertyReference(ValueExpression):
    """
    Represents a run-time property read from a test object:

        Browser("B").Page("P").WebElement("E").GetROProperty("innertext")
    """

    target: ObjectReference | None = None
    property: str = ""


# ======================================================================
# OPERATIONS
# ======================================================================


@dataclass
class ScriptOperation:
    """
    Base class for every parsed UFT operation.
    """

    raw: str
    line_number: int | None = None
    # UFT's OptionalStep modifier: the step is skipped instead of failing.
    optional: bool = False


@dataclass
class ExistCondition:
    """
    Represents an Exist check used as an If condition.
    """

    target: ObjectReference
    timeout: ValueExpression | None = None
    raw: str = ""


@dataclass
class ComparisonCondition:
    """
    Represents a comparison used as an If condition, e.g. x = "a" or n > 1.
    """

    left: ValueExpression | None = None
    operator: str = ""
    right: ValueExpression | None = None
    raw: str = ""


@dataclass
class LogicalCondition:
    """
    Represents a And b And c, or a Or b: operands are conditions or values.
    """

    operator: str = ""
    operands: list[Any] = field(default_factory=list)
    raw: str = ""


@dataclass
class NotCondition:
    """
    Represents Not a.
    """

    operand: Any = None
    raw: str = ""


@dataclass
class IfOperation(ScriptOperation):
    """
    Represents a VBScript If / Else / End If block.

    ElseIf is represented as a nested IfOperation inside else_operations.
    """

    condition: Any = None
    then_operations: list[ScriptOperation] = field(default_factory=list)
    else_operations: list[ScriptOperation] = field(default_factory=list)


@dataclass
class SetTextOperation(ScriptOperation):
    """
    Represents WebEdit.Set.
    """

    target: ObjectReference | None = None
    value: ValueExpression | None = None


@dataclass
class SetSecureTextOperation(ScriptOperation):
    """
    Represents WebEdit.SetSecure.
    """

    target: ObjectReference | None = None
    value: ValueExpression | None = None


@dataclass
class ClickOperation(ScriptOperation):
    """
    Represents an object Click operation, optionally at recorded coordinates.
    """

    target: ObjectReference | None = None
    x: int | None = None
    y: int | None = None


@dataclass
class CheckOperation(ScriptOperation):
    """
    Represents Set on a check box ("ON"/"OFF") or a radio button (no value).
    """

    target: ObjectReference | None = None
    value: ValueExpression | None = None


@dataclass
class TypeOperation(ScriptOperation):
    """
    Represents Object.Type: keystrokes sent to the object, added to what it holds.
    """

    target: ObjectReference | None = None
    value: ValueExpression | None = None


@dataclass
class SelectOperation(ScriptOperation):
    """
    Represents Select on a list, combo box or radio group.
    """

    target: ObjectReference | None = None
    value: ValueExpression | None = None


@dataclass
class NavigateOperation(ScriptOperation):
    """
    Represents Browser.Navigate.
    """

    target: ObjectReference | None = None
    value: ValueExpression | None = None


@dataclass
class SyncOperation(ScriptOperation):
    """
    Represents Sync: wait until the page finished loading.
    """

    target: ObjectReference | None = None


@dataclass
class ActivateOperation(ScriptOperation):
    """
    Represents Activate: bring a window or dialog to the front.
    """

    target: ObjectReference | None = None


@dataclass
class CloseOperation(ScriptOperation):
    """
    Represents Close on a browser, window or dialog.
    """

    target: ObjectReference | None = None


@dataclass
class BackOperation(ScriptOperation):
    """
    Represents Browser.Back.
    """

    target: ObjectReference | None = None


@dataclass
class WaitOperation(ScriptOperation):
    """
    Represents the UFT Wait statement, in seconds.
    """

    seconds: ValueExpression | None = None


@dataclass
class AssignOperation(ScriptOperation):
    """
    Represents a VBScript assignment to a variable.
    """

    name: str = ""
    value: ValueExpression | None = None


@dataclass
class FunctionDefinitionOperation(ScriptOperation):
    """
    Represents a Function/Sub definition. Its body runs only when called.
    """

    keyword: str = "Function"
    name: str = ""
    parameters: list[str] = field(default_factory=list)
    body: list["ScriptOperation"] = field(default_factory=list)


@dataclass
class CheckpointOperation(ScriptOperation):
    """
    Represents <object>.Check CheckPoint("name"): a UFT checkpoint.
    """

    target: ObjectReference | None = None
    name: str = ""


@dataclass
class ParameterAssignmentOperation(ScriptOperation):
    """
    Represents Parameter("name") = value: an output parameter of the action.
    """

    name: str = ""
    value: ValueExpression | None = None


@dataclass
class ObjectAssignmentOperation(ScriptOperation):
    """
    Represents Set name = <expression>: a reference to an object, not a value.
    """

    name: str = ""
    expression: str = ""


@dataclass
class NoEffectOperation(ScriptOperation):
    """
    Represents a statement with no equivalent effect to migrate, e.g. Randomize.
    """

    keyword: str = ""


@dataclass
class DeclarationOperation(ScriptOperation):
    """
    Represents Dim/Option statements, which declare rather than act.
    """

    keyword: str = ""
    names: list[str] = field(default_factory=list)


@dataclass
class ReportEventOperation(ScriptOperation):
    """
    Represents Reporter.ReportEvent.
    """

    status: str | None = None
    title: ValueExpression | None = None
    message: ValueExpression | None = None


@dataclass
class ExitTestOperation(ScriptOperation):
    """
    Represents ExitTest.
    """

    code: ValueExpression | None = None


@dataclass
class CaseClause:
    """
    One Case of a Select Case: the values it matches and the statements it runs.
    """

    raw: str = ""
    line_number: int | None = None
    values: list[ValueExpression] = field(default_factory=list)
    operations: list[ScriptOperation] = field(default_factory=list)


@dataclass
class SelectCaseOperation(ScriptOperation):
    """
    Represents Select Case subject ... Case a, b ... Case Else ... End Select.
    """

    subject: ValueExpression | None = None
    cases: list[CaseClause] = field(default_factory=list)
    else_operations: list[ScriptOperation] = field(default_factory=list)


@dataclass
class RunApplicationOperation(ScriptOperation):
    """
    Represents SystemUtil.Run file, [parameters], [directory], [operation], [mode].
    """

    file: ValueExpression | None = None
    parameters: ValueExpression | None = None
    directory: ValueExpression | None = None
    operation: ValueExpression | None = None
    mode: ValueExpression | None = None


@dataclass
class CallOperation(ScriptOperation):
    """
    Represents a function or sub called as a statement:

        InvokeFlightApp
        OpenApp "C:\\app.exe"
        Call FillSearchOrderCriteria(name, date, number)
    """

    name: str = ""
    arguments: list[ValueExpression] = field(default_factory=list)


@dataclass
class UnknownScriptOperation(ScriptOperation):
    """
    Preserves unsupported or currently unrecognized VBScript.

    Unknown lines must never be silently discarded.
    """

    reason: str = "Unsupported UFT/VBScript statement"