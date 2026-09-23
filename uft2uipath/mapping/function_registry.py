"""Which VBScript built-in functions a migrated expression may use, as data.

A name in a UFT script is one of three things, and a report has to tell them
apart: a VBScript built-in this table classifies, a Function/Sub defined in the
action or one of its libraries (translated into its own workflow), or a name
nothing in the export defines. Only the first kind belongs here.

The table says what is trusted, not how it is written: the C# each supported
function becomes lives in script_generation.emitters.functions, which is
checked against this table at import.
"""
from __future__ import annotations

from dataclasses import dataclass

from uft2uipath.contracts.status import EMITTED, PLANNED, REQUIRES_STRATEGY, STATUSES, SUPPORTED
from uft2uipath.contracts.value_types import VALUE_TYPES


@dataclass(frozen=True)
class FunctionMapping:
    """One VBScript built-in: how far it is migrated, and what it returns.

    name is lower case, because VBScript does not care about case. vbscript is
    the call as a person writes it. returns is None when the result type
    depends on the arguments (Abs) or when nothing is emitted at all.
    """
    name: str
    vbscript: str
    status: str
    returns: str | None = None
    notes: str = ""


def _group(status: str, names: str, notes: str = "") -> tuple[FunctionMapping, ...]:
    """Entries that share a status and a reason, e.g. everything blocked on arrays."""
    return tuple(FunctionMapping(name, name, status, notes=notes) for name in names.split())


def F(name: str, vbscript: str, returns: str | None = None, notes: str = "") -> FunctionMapping:
    """A built-in the converter translates."""
    return FunctionMapping(name, vbscript, SUPPORTED, returns, notes)


TABLE = (
    # Strings.
    F("len", "Len(s)", "Int32"),
    F("lcase", "LCase(s)", "String"),
    F("ucase", "UCase(s)", "String"),
    F("trim", "Trim(s)", "String", "VBScript trims spaces only, not tabs or line breaks."),
    F("ltrim", "LTrim(s)", "String"),
    F("rtrim", "RTrim(s)", "String"),
    F("left", "Left(s, n)", "String"),
    F("right", "Right(s, n)", "String"),
    F("mid", "Mid(s, start[, length])", "String", "1-based start; past the end gives \"\"."),
    F("instr", "InStr(s, part)", "Int32",
      "Two-argument form only; a start position or compare mode blocks."),
    F("instrrev", "InStrRev(s, part)", "Int32", "Two-argument form only."),
    F("replace", "Replace(s, find, with)", "String"),
    F("space", "Space(n)", "String"),
    F("chr", "Chr(code)", "String", "UTF-16 code; VBScript uses the ANSI code page above 127."),

    # Numbers and conversions.
    F("cstr", "CStr(x)", "String"),
    F("cint", "CInt(x)", "Int32", "Rounds half to even, as VBScript does."),
    F("clng", "CLng(x)", "Int32", "Int32 range, not VBScript's Long promotion."),
    F("cdbl", "CDbl(x)", "Double"),
    F("int", "Int(n)", "Int32", "Returns Int32; VBScript keeps a Double subtype with the same value."),
    F("fix", "Fix(n)", "Int32"),
    F("abs", "Abs(n)", None, "Keeps the type of its argument."),
    F("rnd", "Rnd", "Double",
      "Randomize seeds from the clock in UFT; a shared random generator is equivalent."),

    # Date and time.
    F("date", "Date", "DateTime"),
    F("now", "Now", "DateTime"),
    F("day", "Day(d)", "Int32"),
    F("month", "Month(d)", "Int32"),
    F("year", "Year(d)", "Int32"),
    F("hour", "Hour(d)", "Int32"),
    F("minute", "Minute(d)", "Int32"),
    F("second", "Second(d)", "Int32"),
    F("weekday", "Weekday(d)", "Int32",
      "Default first day (Sunday) only; a firstdayofweek argument blocks."),

    # Known built-ins with a clear C# equivalent that nobody has written yet.
    *_group(PLANNED, "cbool cbyte ccur cdate csng sgn round exp log sqr sin cos tan atn hex oct "
                     "strcomp strreverse string isdate isnumeric monthname weekdayname rgb time "
                     "timer timeserial timevalue dateadd datediff datepart dateserial datevalue "
                     "formatnumber formatcurrency formatpercent formatdatetime escape unescape"),

    # Blocked on a decision, not on effort.
    *_group(REQUIRES_STRATEGY, "array lbound ubound split join filter",
            "Arrays are not migrated yet: a VBScript array has no typed UiPath equivalent."),
    *_group(REQUIRES_STRATEGY, "isempty isnull isarray isobject vartype typename",
            "Asks what a Variant currently holds; migrated values have one static type."),
    *_group(REQUIRES_STRATEGY, "asc ascb ascw chrb chrw instrb leftb lenb midb rightb",
            "Byte and code-page semantics that .NET strings (UTF-16) do not reproduce."),
    *_group(REQUIRES_STRATEGY, "createobject getobject getref eval",
            "Creates or calls something chosen at run time; the target must be known to migrate it. "
            "CreateObject in Set x = ... is handled as an object assignment instead."),
    *_group(REQUIRES_STRATEGY, "msgbox inputbox",
            "Interrupts the run for a person; an automated test has nowhere to show it."),
    *_group(REQUIRES_STRATEGY, "getlocale setlocale scriptengine loadpicture",
            "Belongs to the VBScript host itself, not to the automation."),
)


def _index(table: tuple[FunctionMapping, ...]) -> dict[str, FunctionMapping]:
    """Check the table and index it by name; a mistake here is a programming error."""
    registry: dict[str, FunctionMapping] = {}
    for entry in table:
        if entry.status not in STATUSES:
            raise ValueError(f"Unknown status {entry.status!r} for {entry.name}.")
        if entry.returns is not None and entry.returns not in VALUE_TYPES:
            raise ValueError(f"Unknown return type {entry.returns!r} for {entry.name}.")
        if entry.name != entry.name.lower() or entry.name in registry:
            raise ValueError(f"Duplicate or non-lower-case function entry {entry.name!r}.")
        registry[entry.name] = entry
    return registry


REGISTRY: dict[str, FunctionMapping] = _index(TABLE)
#: Every VBScript built-in the converter knows of, mapped or not.
BUILTINS = frozenset(REGISTRY)


def lookup(name: str | None) -> FunctionMapping | None:
    """The entry for a function name, whatever its case; None for a name VBScript does not define."""
    return REGISTRY.get((name or "").lower())


def status_of(name: str | None) -> str:
    """Status of a called name: its own, or "unknown" for a user or library function."""
    entry = lookup(name)
    return entry.status if entry else "unknown"


def implemented(names: set[str]) -> None:
    """Check that exactly the supported built-ins are implemented; called by the emitter."""
    promised = {name for name, entry in REGISTRY.items() if entry.status in EMITTED}
    if missing := promised - names:
        raise ValueError(f"Built-ins promised by the registry but not implemented: {sorted(missing)}.")
    if extra := names - promised:
        raise ValueError(f"Built-ins implemented without a supported registry entry: {sorted(extra)}.")


def capabilities() -> dict[str, list[dict]]:
    """Registry entries grouped by status, for coverage reports."""
    grouped: dict[str, list[dict]] = {status: [] for status in STATUSES}
    for entry in sorted(REGISTRY.values(), key=lambda e: e.name):
        grouped[entry.status].append({"name": entry.name, "vbscript": entry.vbscript,
                                      "returns": entry.returns, "notes": entry.notes})
    return grouped
