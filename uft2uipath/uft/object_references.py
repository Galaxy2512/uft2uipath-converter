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
    test_object_class: str
    name: str | None = None
    description: dict[str, str] = field(default_factory=dict)


@dataclass
class ObjectReference:
    line: int
    path: list[ObjectStep]
    source: str
    dynamic: bool = False

    @property
    def descriptive(self) -> bool:
        return any(step.description for step in self.path)

    def key(self) -> tuple:
        return tuple((s.test_object_class.casefold(), (s.name or "").casefold(),
                      tuple(sorted(s.description.items()))) for s in self.path)


def extract_references(text: str) -> list[ObjectReference]:
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
    values = [literal[1:-1].replace('""', '"') for literal in _ARGUMENT.findall(arguments)]
    if all(":=" in value for value in values):
        return ObjectStep(test_object_class, description=dict(v.split(":=", 1) for v in values))
    return ObjectStep(test_object_class, name=values[0] if len(values) == 1 else ", ".join(values))
