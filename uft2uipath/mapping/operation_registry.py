"""What every UFT construct becomes in UiPath, as data.

Each parser node type has exactly one entry: what the UFT statement means,
which UiPath activities it becomes, and how far that mapping is trusted. The
table is the source of truth for both sides of the migration - the coverage
reports read it without generating anything, and script_generation.handlers
registers one handler per supported entry against it.

Deliberately declarative: no entry holds code, so the mapping can be read,
reported and reviewed without importing the XAML generator.
"""
from __future__ import annotations

from dataclasses import dataclass

from uft2uipath.contracts.status import EMITTED, STATUSES  # noqa: F401  (re-exported)
from uft2uipath.contracts.value_types import VALUE_TYPES
from uft2uipath.mapping.uipath_activity_catalog import require as require_activity

# Where the construct appears: a statement, the Boolean test of an If, or a value.
KINDS = ("operation", "condition", "expression")


@dataclass(frozen=True)
class OperationMapping:
    """Registry entry for one parser node type.

    node_type is the parser class name; uft and activities describe the mapping
    for people and for reports; returns is the value type of an expression when
    it is the same for every operand (otherwise the handler decides).
    """
    node_type: str
    uft: str
    activities: tuple[str, ...] = ()
    status: str = "supported"
    requires_selector: bool = False
    notes: str = ""
    kind: str = "operation"
    returns: str | None = None


TABLE = (
    # UI actions on a test object. Each needs a selector accepted for generation.
    OperationMapping('ClickOperation', '.Click', ('Click',), requires_selector=True,
                     notes='A recorded click offset is not reproduced.'),
    OperationMapping('SetTextOperation', '.Set', ('TypeInto',), requires_selector=True),
    OperationMapping('SetSecureTextOperation', '.SetSecure', ('TypeInto',), requires_selector=True,
                     notes='The UFT encoded value is not carried over; a secure argument supplies '
                           'it.'),
    OperationMapping('TypeOperation', '.Type', ('TypeInto',), requires_selector=True,
                     notes="Keeps the field's content, as UFT Type adds keystrokes; key constants "
                           '(micTab ...) block.'),
    OperationMapping('CheckOperation', 'CheckBox.Set "ON"/"OFF", RadioButton.Set', ('Check',),
                     requires_selector=True,
                     notes='The state must be a literal ON or OFF; a radio button is checked.'),
    OperationMapping('SelectOperation', '.Select', ('SelectItem',), requires_selector=True),
    OperationMapping('SyncOperation', '.Sync', ('WaitUiElementAppear',), requires_selector=True,
                     notes='Sync waits for load completion; waiting for the page element is close, '
                           'not identical.'),

    # Conditions: the Boolean test of an If.
    OperationMapping('ExistCondition', '.Exist(n)', ('UiElementExists',), requires_selector=True,
                     kind='condition',
                     notes='Timeout must be a positive literal number of seconds.'),
    OperationMapping('ComparisonCondition', 'a = b, a <> b, a < b ...', kind='condition',
                     notes="Both sides must have the same static type; VBScript's implicit "
                           "conversions are not reproduced. Strings compare ordinally, as VBScript's "
                           'default binary compare.'),
    OperationMapping('LogicalCondition', 'a And b, a Or b', kind='condition'),
    OperationMapping('NotCondition', 'Not a', kind='condition'),

    # Values: everything that appears on the right-hand side of an expression.
    OperationMapping('ObjectPropertyReference', '.GetROProperty("property")', ('GetAttribute',),
                     requires_selector=True, kind='expression', returns='String',
                     notes='Read with the full selector, outside any browser scope. The attribute is '
                           "converted to String, as GetROProperty's value is compared in UFT."),
    OperationMapping('FunctionCall', 'Len(x), CStr(n), Rnd ...', kind='expression',
                     notes='VBScript built-ins: abs, cdbl, chr, cint, clng, cstr, date, day, fix, '
                           'hour, instr, instrrev, int, lcase, left, len, ltrim, mid, minute, month, '
                           'now, replace, right, rnd, rtrim, second, space, trim, ucase, weekday, '
                           'year. Functions defined in the action or an associated library are '
                           'called as their own workflow; others block.'),
    OperationMapping('MethodCall', 'fso.FileExists(path) ...', kind='expression',
                     notes='FileSystemObject: buildpath, fileexists, folderexists, getbasename, '
                           'getextensionname, getfilename, getparentfoldername.'),
    OperationMapping('BinaryExpression', 'a + b, a - b, a * b, a / b, a \\ b, a Mod b, a ^ b',
                     kind='expression',
                     notes='Operands must be numbers, or both strings for +. Int32 overflow wraps '
                           'instead of promoting to Long/Double as VBScript does.'),
    OperationMapping('UnaryExpression', '-a', kind='expression'),

    # Flow, assignment and calls.
    OperationMapping('IfOperation', 'If ... Then ... Else ... End If', ('If',)),
    OperationMapping('SelectCaseOperation',
                     'Select Case x ... Case a, b ... Case Else ... End Select', ('Assign', 'If'),
                     notes='The subject is evaluated once into a variable, then each Case is an '
                           'If/Else in order; Case Is and Case a To b block.'),
    OperationMapping('AssignOperation', 'x = value', ('Assign',),
                     notes='String, Int32 and Boolean; a variable keeps one type for the whole '
                           'action.'),
    OperationMapping('ParameterAssignmentOperation', 'Parameter("X") = value', ('Assign',),
                     notes='Writes an Out argument of the action workflow; the test exposes it per '
                           'step.'),
    OperationMapping('WaitOperation', 'Wait n', ('Delay',)),
    OperationMapping('CallOperation', 'Name args / Call Name(args)', ('InvokeWorkflowFile',),
                     notes='Calls a Function/Sub compiled into its own workflow; VBScript built-ins '
                           'called as statements (MsgBox ...) are not mapped.'),

    # Test outcome.
    OperationMapping('ReportEventOperation', 'Reporter.ReportEvent', ('LogMessage',),
                     notes='micFail logs an error and continues, as UFT does; the calling test fails '
                           'at its end. A screenshot argument is not carried over.'),
    OperationMapping('ExitTestOperation', 'ExitTest', ('Throw',),
                     notes='The calling test catches it: the run stops, and fails only if a failure '
                           'was reported.'),

    # The application under test and COM objects.
    OperationMapping('RunApplicationOperation',
                     'SystemUtil.Run file, [parameters], [directory], [operation], [mode]',
                     ('StartProcess',),
                     notes="Only the default 'open' operation; the window mode is not carried over."),
    OperationMapping('ObjectAssignmentOperation', 'Set x = CreateObject("...") / Set x = Nothing',
                     status='no_effect',
                     notes='Scripting.FileSystemObject only: its methods become System.IO calls, so '
                           'the object itself needs no activity. Other ProgIDs and test objects in '
                           'variables block.'),

    # Statements with nothing to emit, by design.
    OperationMapping('DeclarationOperation', 'Dim / Option Explicit', status='no_effect',
                     notes='Declarations become workflow variables where they are used.'),
    OperationMapping('NoEffectOperation', 'Randomize and similar', status='no_effect'),
    OperationMapping('FunctionDefinitionOperation', 'Function / Sub definition',
                     status='no_effect',
                     notes='The definition is not part of the flow; calls to it block instead.'),

    # Not mapped yet. Moving one to "supported" means writing its handler in
    # script_generation.handlers and changing the status here.
    OperationMapping('NavigateOperation', 'Browser.Navigate', ('NGoToUrl',), status='planned',
                     requires_selector=True),
    OperationMapping('CloseOperation', 'Browser/Window.Close', ('NCloseApplication',),
                     status='planned', requires_selector=True),
    OperationMapping('ActivateOperation', 'Window.Activate', ('NApplicationCard',),
                     status='planned', requires_selector=True),
    OperationMapping('BackOperation', 'Browser.Back', ('NGoBack',), status='planned',
                     requires_selector=True),
    OperationMapping('CheckpointOperation', 'Checkpoint', ('VerifyExpression',),
                     status='requires_strategy',
                     notes='Checkpoint criteria live in the UFT resource files, not in the script.'),
    OperationMapping('UnknownScriptOperation', '(unparsed statement)', status='unsupported'),
)


def _index(table: tuple[OperationMapping, ...]) -> dict[str, OperationMapping]:
    """Check the table and index it by node type; a mistake here is a programming error."""
    registry: dict[str, OperationMapping] = {}
    for entry in table:
        if entry.status not in STATUSES:
            raise ValueError(f"Unknown mapping status {entry.status!r} for {entry.node_type}.")
        if entry.kind not in KINDS:
            raise ValueError(f"Unknown mapping kind {entry.kind!r} for {entry.node_type}.")
        if entry.returns is not None and entry.returns not in VALUE_TYPES:
            raise ValueError(f"Unknown return type {entry.returns!r} for {entry.node_type}.")
        for activity_id in entry.activities:
            require_activity(activity_id)
        if entry.node_type in registry:
            raise ValueError(f"Duplicate registry entry for {entry.node_type}.")
        registry[entry.node_type] = entry
    return registry


REGISTRY: dict[str, OperationMapping] = _index(TABLE)


def lookup(node_type: str | None) -> OperationMapping | None:
    """The entry for a parser node type, or None when the parser node is unknown here."""
    return REGISTRY.get(node_type)


def capabilities() -> dict[str, list[dict]]:
    """Registry entries grouped by status, for coverage reports."""
    grouped: dict[str, list[dict]] = {status: [] for status in STATUSES}
    for entry in sorted(REGISTRY.values(), key=lambda e: e.node_type):
        grouped[entry.status].append({
            "node_type": entry.node_type, "kind": entry.kind, "uft": entry.uft,
            "activities": list(entry.activities),
            "activity_specs": [
                {
                    "activity_id": spec.activity_id,
                    "display_name": spec.display_name,
                    "package": spec.package,
                    "category": spec.category,
                    "target": spec.target,
                    "backend": spec.backend,
                    "status": spec.status,
                }
                for spec in (require_activity(activity_id) for activity_id in entry.activities)
            ],
            "requires_selector": entry.requires_selector, "notes": entry.notes,
        })
    return grouped
