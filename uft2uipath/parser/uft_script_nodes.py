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
    need Browser, Page and control information.

    Example:

        Browser("OrangeHRM_BrowserObject")
            .Page("OrangeHRM_PageObject")
            .WebEdit("username_WebEdit")
    """

    browser: str | None = None
    page: str | None = None
    object_type: str | None = None
    logical_name: str | None = None
    raw: str = ""


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


@dataclass
class ExistCondition:
    """
    Represents an Exist check used as an If condition.
    """

    target: ObjectReference
    timeout: ValueExpression | None = None
    raw: str = ""


@dataclass
class IfOperation(ScriptOperation):
    """
    Represents a VBScript If / Else / End If block.
    """

    condition: ExistCondition | None = None
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
    Represents an object Click operation.
    """

    target: ObjectReference | None = None


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
class UnknownScriptOperation(ScriptOperation):
    """
    Preserves unsupported or currently unrecognized VBScript.

    Unknown lines must never be silently discarded.
    """

    reason: str = "Unsupported UFT/VBScript statement"