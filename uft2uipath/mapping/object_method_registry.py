"""Methods called on an object: what they mean in UiPath, as data.

Three kinds of owner appear in UFT scripts, and a report has to tell them apart:

    test object   Browser(...).Page(...).WebEdit(...).Click and everything else
                  called on a repository object. Most are parsed into their own
                  operation; the entry then names that node type, so a blocked
                  line is not reported as an unmapped method.
    COM object    a variable holding CreateObject("..."), e.g. FileSystemObject.
    data accessor Environment.Value, DataTable.Value: not automation at all, but
                  values bound to workflow arguments.

The C# and activities live in script_generation.emitters; this table is only
what is trusted, so coverage reports can read it without the generator.
"""
from __future__ import annotations

from dataclasses import dataclass

from uft2uipath.contracts.status import (
    EMITTED, NO_EFFECT, PLANNED, REQUIRES_STRATEGY, STATUSES, SUPPORTED,
)
from uft2uipath.contracts.value_types import VALUE_TYPES

#: Owners a method can be called on.
TEST_OBJECT = "UFT test object"
FILE_SYSTEM_OBJECT = "Scripting.FileSystemObject"
DATA = "UFT data accessor"
OWNERS = (TEST_OBJECT, FILE_SYSTEM_OBJECT, DATA)


@dataclass(frozen=True)
class MethodMapping:
    """One method on one kind of owner.

    node_type names the parser operation a test-object method is parsed into;
    such a method is migrated through mapping.operation_registry, and an entry
    here only says so. returns is set for methods that are values.
    """
    owner: str
    method: str
    uft: str
    status: str
    returns: str | None = None
    node_type: str | None = None
    notes: str = ""


def _test_object(names: str, status: str, notes: str = "") -> tuple[MethodMapping, ...]:
    """Test-object methods that share a status and a reason."""
    return tuple(MethodMapping(TEST_OBJECT, name, f".{name}", status, notes=notes)
                 for name in names.split())


def _operation(name: str, node_type: str, uft: str, returns: str | None = None) -> MethodMapping:
    """A test-object method the parser turns into its own operation."""
    return MethodMapping(TEST_OBJECT, name, uft, SUPPORTED, returns, node_type,
                         notes=f"Parsed as {node_type}; see the operation registry.")


def _fso(name: str, uft: str, returns: str, status: str = SUPPORTED,
         notes: str = "") -> MethodMapping:
    """A FileSystemObject method."""
    return MethodMapping(FILE_SYSTEM_OBJECT, name, uft, status, returns, notes=notes)


TABLE = (
    # Test-object methods that are operations of their own.
    _operation("click", "ClickOperation", "obj.Click"),
    _operation("set", "SetTextOperation", 'obj.Set "text"'),
    _operation("setsecure", "SetSecureTextOperation", "obj.SetSecure encoded"),
    _operation("type", "TypeOperation", 'obj.Type "text"'),
    _operation("select", "SelectOperation", 'obj.Select "item"'),
    _operation("sync", "SyncOperation", "obj.Sync"),
    _operation("exist", "ExistCondition", "obj.Exist(n)", "Boolean"),
    _operation("getroproperty", "ObjectPropertyReference", 'obj.GetROProperty("p")', "String"),
    MethodMapping(TEST_OBJECT, "navigate", 'Browser.Navigate "url"', PLANNED,
                  node_type="NavigateOperation"),
    MethodMapping(TEST_OBJECT, "close", "Browser.Close", PLANNED, node_type="CloseOperation"),
    MethodMapping(TEST_OBJECT, "back", "Browser.Back", PLANNED, node_type="BackOperation"),
    MethodMapping(TEST_OBJECT, "activate", "Window.Activate", PLANNED,
                  node_type="ActivateOperation"),

    # Test-object methods with no operation yet.
    *_test_object("setfocus maximize minimize restore submit refresh home forward", PLANNED,
                  "A window or browser command with a modern equivalent; not written yet."),
    *_test_object("deletecookies", PLANNED,
                  "UiPath clears cookies through the browser scope, not per element."),
    *_test_object("drag drop", PLANNED,
                  "UFT's Drag and Drop pair becomes one UiPath drag activity; the pairing has to "
                  "be reconstructed from the two lines."),
    *_test_object("capture", PLANNED, "A screenshot of the element or window."),
    *_test_object("highlight", NO_EFFECT, "Marks the element while a person watches; a run has "
                                          "nothing to show it to."),
    *_test_object("waitproperty", REQUIRES_STRATEGY,
                  "Returns True or False in UFT; UiPath's Wait Attribute throws on timeout, so "
                  "the surrounding If has to be rewritten."),
    *_test_object("gettoproperty settoproperty getproperty setproperty", REQUIRES_STRATEGY,
                  "Changes how the object is identified at run time: descriptive programming, "
                  "which the selector model does not cover yet."),
    *_test_object("childobjects childitemcount getitem getitemscount getcontent getvisibletext",
                  REQUIRES_STRATEGY,
                  "Reads a collection of elements; needs a strategy for lists of UI elements."),
    *_test_object("output", REQUIRES_STRATEGY,
                  "Writes into a UFT checkpoint or data table, which the migration does not have."),

    # Scripting.FileSystemObject.
    _fso("fileexists", "fso.FileExists(path)", "Boolean"),
    _fso("folderexists", "fso.FolderExists(path)", "Boolean"),
    _fso("getfilename", "fso.GetFileName(path)", "String"),
    _fso("getbasename", "fso.GetBaseName(path)", "String"),
    _fso("getextensionname", "fso.GetExtensionName(path)", "String"),
    _fso("getparentfoldername", "fso.GetParentFolderName(path)", "String"),
    _fso("buildpath", "fso.BuildPath(a, b)", "String"),
    _fso("copyfile", "fso.CopyFile(from, to)", "String", PLANNED),
    _fso("movefile", "fso.MoveFile(from, to)", "String", PLANNED),
    _fso("deletefile", "fso.DeleteFile(path)", "String", PLANNED),
    _fso("createfolder", "fso.CreateFolder(path)", "String", PLANNED),
    _fso("deletefolder", "fso.DeleteFolder(path)", "String", PLANNED),
    _fso("getabsolutepathname", "fso.GetAbsolutePathName(path)", "String", PLANNED),
    _fso("gettempname", "fso.GetTempName()", "String", PLANNED),
    _fso("createtextfile", "fso.CreateTextFile(path)", None, REQUIRES_STRATEGY,
         "Returns a TextStream the script then writes to; objects with a lifetime are not "
         "migrated yet."),
    _fso("opentextfile", "fso.OpenTextFile(path)", None, REQUIRES_STRATEGY,
         "Returns a TextStream; see CreateTextFile."),
    _fso("getfile", "fso.GetFile(path)", None, REQUIRES_STRATEGY, "Returns a File object."),
    _fso("getfolder", "fso.GetFolder(path)", None, REQUIRES_STRATEGY, "Returns a Folder object."),

    # Data accessors: values, not automation.
    MethodMapping(DATA, "value", 'Environment.Value("X"), DataTable.Value("C")', SUPPORTED, "String",
                  notes="Bound to a workflow argument by the conversion plan, not emitted as an "
                        "activity."),
)


def _index(table: tuple[MethodMapping, ...]) -> dict[tuple[str, str], MethodMapping]:
    """Check the table and index it by owner and method; a mistake here is a programming error."""
    registry: dict[tuple[str, str], MethodMapping] = {}
    for entry in table:
        if entry.owner not in OWNERS:
            raise ValueError(f"Unknown owner {entry.owner!r} for {entry.method}.")
        if entry.status not in STATUSES:
            raise ValueError(f"Unknown status {entry.status!r} for {entry.method}.")
        if entry.returns is not None and entry.returns not in VALUE_TYPES:
            raise ValueError(f"Unknown return type {entry.returns!r} for {entry.method}.")
        key = (entry.owner, entry.method)
        if entry.method != entry.method.lower() or key in registry:
            raise ValueError(f"Duplicate or non-lower-case method entry {key}.")
        registry[key] = entry
    return registry


REGISTRY: dict[tuple[str, str], MethodMapping] = _index(TABLE)


def lookup(owner: str, method: str | None) -> MethodMapping | None:
    """The entry for one owner's method, whatever its case."""
    return REGISTRY.get((owner, (method or "").lower()))


def find(method: str | None) -> MethodMapping | None:
    """The entry for a method name when the owner is not known, e.g. from a report message.

    A name used by several owners resolves to the most migrated entry, because
    the question a report asks is whether the name is migrated at all.
    """
    name = (method or "").lower()
    entries = [entry for (_, other), entry in REGISTRY.items() if other == name]
    return min(entries, key=lambda e: STATUSES.index(e.status)) if entries else None


def status_of(method: str | None) -> str:
    """Status of a called method name, or "unknown" when nothing here defines it."""
    entry = find(method)
    return entry.status if entry else "unknown"


def implemented(owner: str, names: set[str]) -> None:
    """Check that exactly the supported methods of an owner are implemented."""
    promised = {method for (other, method), entry in REGISTRY.items()
                if other == owner and entry.status in EMITTED and entry.node_type is None}
    if missing := promised - names:
        raise ValueError(f"{owner} methods promised by the registry but not implemented: {sorted(missing)}.")
    if extra := names - promised:
        raise ValueError(f"{owner} methods implemented without a supported registry entry: {sorted(extra)}.")


def capabilities() -> dict[str, list[dict]]:
    """Registry entries grouped by status, for coverage reports."""
    grouped: dict[str, list[dict]] = {status: [] for status in STATUSES}
    for entry in sorted(REGISTRY.values(), key=lambda e: (e.owner, e.method)):
        grouped[entry.status].append({"owner": entry.owner, "method": entry.method,
                                      "uft": entry.uft, "returns": entry.returns,
                                      "node_type": entry.node_type, "notes": entry.notes})
    return grouped
