"""Extracts test-object references (Class("name").Class("name")...) from UFT scripts.

Each argument is either a repository logical name or, in descriptive
programming, one or more "property:=value" strings. Arguments that are not
plain string literals (variables, concatenation) are reported as dynamic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_STRING = r'"(?:[^"]|"")*"'
_STEP = re.compile(r'([A-Za-z_]\w*)\s*\(\s*(' + _STRING + r'(?:\s*,\s*' + _STRING + r')*)\s*\)')
_DYNAMIC_STEP = re.compile(r'([A-Za-z_]\w*)\s*\(([^()"]*[&+][^()]*|[A-Za-z_]\w*)\)\s*\.')
_ARGUMENT = re.compile(_STRING)
_STARTS_CHAIN = re.compile(r'(?:^|[^.\w]|\bOptionalStep\s*\.)\s*$', re.IGNORECASE)
_NOT_OBJECTS = {"datatable", "parameter", "environment", "reporter", "msgbox", "runaction",
                "call", "createobject", "getobject", "setting", "systemutil", "array", "cstr",
                "cint", "left", "right", "mid", "instr", "replace", "trim", "split", "join"}
# Test-object methods that take string arguments; they end a chain, they are not objects.
_METHODS = {"set", "setsecure", "select", "type", "navigate", "getroproperty", "gettoproperty",
            "settoproperty", "waitproperty", "check", "output", "capturebitmap", "selectcell",
            "getcelldata", "setcelldata", "extendselect", "deselect", "sendkeys", "submit",
            "fireevent", "object", "childobjects", "highlight", "setfocus", "open", "setcaretpos"}


@dataclass
class ObjectStep:
    """One step of a test-object chain: a class with a logical name or an inline description."""
    test_object_class: str
    name: str | None = None
    description: dict[str, str] = field(default_factory=dict)


@dataclass
class ObjectReference:
    """A test-object chain found in a script line."""
    line: int
    path: list[ObjectStep]
    source: str
    dynamic: bool = False

    @property
    def descriptive(self) -> bool:
        """True if any step is described inline (descriptive programming)."""
        return any(step.description for step in self.path)

    def key(self) -> tuple:
        """Case-insensitive identity used to group repeated references."""
        return tuple((s.test_object_class.casefold(), (s.name or "").casefold(),
                      tuple(sorted(s.description.items()))) for s in self.path)


def split_chain(expression: str) -> tuple[list[ObjectStep], str]:
    """Splits a leading object chain from what follows it (e.g. '.Click 14, 11')."""
    code = expression.strip()
    steps, position = [], 0
    while True:
        match = _STEP.match(code, position)
        if match is None or match.group(1).casefold() in _NOT_OBJECTS:
            break
        steps.append(_step(match.group(1), match.group(2)))
        position = match.end()
        if position >= len(code) or code[position] != ".":
            break
        following = _STEP.match(code, position + 1)
        if following is None or following.group(1).casefold() in _NOT_OBJECTS | _METHODS:
            break
        position += 1
    return steps, code[position:]


def parse_chain(expression: str) -> list[ObjectStep] | None:
    """Returns the steps when the expression is exactly one object chain."""
    steps, remainder = split_chain(expression)
    return steps if steps and not remainder.strip() else None


def extract_references(text: str) -> list[ObjectReference]:
    """Every object chain in a script, per line; dynamic arguments are flagged, not resolved."""
    references = []
    for number, line in enumerate(text.splitlines(), 1):
        code = _code(line)
        if not code:
            continue
        for chain in _chains(code):
            references.append(ObjectReference(number, chain, code))
        for match in _DYNAMIC_STEP.finditer(code):
            if match.group(1).casefold() not in _NOT_OBJECTS:
                references.append(ObjectReference(number, [ObjectStep(match.group(1))], code, dynamic=True))
    return references


def _code(line: str) -> str:
    """A script line without UFT step metadata, a trailing comment or a REM line."""
    code = line.split(" @@ ", 1)[0]
    # Strip a trailing comment that is outside string literals.
    in_string = False
    for index, char in enumerate(code):
        if char == '"':
            in_string = not in_string
        elif char == "'" and not in_string:
            code = code[:index]
            break
    code = code.strip()
    return "" if code.lower().startswith("rem ") else code


def _chains(code: str) -> list[list[ObjectStep]]:
    """Object chains in one line of code; methods end a chain."""
    chains, current, last_end = [], [], None
    for match in _STEP.finditer(code):
        name = match.group(1)
        if name.casefold() in _NOT_OBJECTS:
            continue
        joined = last_end is not None and code[last_end:match.start()].strip() == "."
        # A call after a dot belongs to whatever precedes it; only OptionalStep may prefix a chain.
        if not joined and not _STARTS_CHAIN.search(code[:match.start()]):
            continue
        if joined and name.casefold() in _METHODS:
            chains.append(current)
            current, last_end = [], None
            continue
        if current and not joined:
            chains.append(current)
            current = []
        current.append(_step(name, match.group(2)))
        last_end = match.end()
        # A chain only continues when the next object follows a dot.
        if not code[last_end:].lstrip().startswith("."):
            chains.append(current)
            current, last_end = [], None
    if current:
        chains.append(current)
    return chains


def _step(test_object_class: str, arguments: str) -> ObjectStep:
    """An object step from its string arguments: a logical name or property:=value pairs."""
    values = [literal[1:-1].replace('""', '"') for literal in _ARGUMENT.findall(arguments)]
    if all(":=" in value for value in values):
        return ObjectStep(test_object_class, description=dict(v.split(":=", 1) for v in values))
    return ObjectStep(test_object_class, name=values[0] if len(values) == 1 else ", ".join(values))
