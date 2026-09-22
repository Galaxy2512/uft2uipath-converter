"""Finds the Functions/Subs an action can call and which of them it actually calls.

UFT resolves a call by name: first a function defined in the action itself,
then the associated function libraries in their configured order. Each
definition keeps its own source text, so it can be compiled into a workflow
and its object references resolved like the action's.
"""
from __future__ import annotations

import re
from typing import Any

from uft2uipath.parser.uft_script_nodes import FunctionDefinitionOperation
from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser
from uft2uipath.script_analysis.analyzer import typed

LOCAL_ORIGIN = "this action"
_END = re.compile(r"^\s*End\s+(Function|Sub)\b", re.IGNORECASE)
_NOT_LITERAL = object()


def function_sources(text: str) -> dict[str, tuple[str, str]]:
    """Source text of every Function/Sub in a script: lower-case name -> (name, source)."""
    parsed = UftVbScriptParser().parse(text)
    lines = parsed.source_lines
    sources: dict[str, tuple[str, str]] = {}
    for operation in parsed.operations:
        if not isinstance(operation, FunctionDefinitionOperation) or not operation.line_number:
            continue
        start = operation.line_number - 1
        end = next((i for i in range(start + 1, len(lines)) if _END.match(lines[i])), None)
        if end is not None:
            sources.setdefault(operation.name.casefold(),
                               (operation.name, "\n".join(lines[start:end + 1])))
    return sources


def library_constants(text: str) -> dict[str, Any]:
    """Library globals set once to a literal at load time: lower-case name -> value.

    UFT runs a library's top-level code when it loads, so IgnoredStringValue =
    "<SKIP>" there makes the value visible to every function of the library.
    A name assigned more than once, or to anything but a literal, is not a constant.
    """
    assigned: dict[str, list[Any]] = {}
    for operation in typed(UftVbScriptParser().parse(text).operations):
        if operation.get("node_type") == "AssignOperation":
            value = operation.get("value") or {}
            literal = value.get("value") if value.get("node_type") == "LiteralValue" else _NOT_LITERAL
            assigned.setdefault(operation["name"].casefold(), []).append(literal)
    return {name: values[0] for name, values in assigned.items()
            if len(values) == 1 and values[0] is not _NOT_LITERAL}


def definitions_for(action_text: str, libraries: list[tuple[str, str]]) -> dict[str, dict[str, Any]]:
    """Functions an action can call, in UFT's lookup order: the action first, then each library.

    libraries: (library path, text) in the order the test associates them.
    Returns lower-case name -> {"name", "origin", "source", "constants"}; constants
    are the library's load-time literal globals (none for the action's own functions).
    """
    definitions: dict[str, dict[str, Any]] = {}
    sources = [(LOCAL_ORIGIN, action_text, {})]
    sources += [(f"library {path}", text, library_constants(text)) for path, text in libraries]
    for origin, text, constants in sources:
        for key, (name, source) in function_sources(text).items():
            definitions.setdefault(key, {"name": name, "origin": origin, "source": source,
                                         "constants": constants})
    return definitions


def called_names(text: str) -> set[str]:
    """Lower-case names of everything a script calls, as statement or inside values."""
    names: set[str] = set()

    def walk(value):
        """Collect call names below a node, skipping bodies of definitions."""
        if isinstance(value, dict):
            # A bare name may be a call without parentheses; callers intersect with definitions.
            if value.get("node_type") in ("FunctionCall", "CallOperation", "VariableReference"):
                names.add((value.get("name") or "").casefold())
            # A definition's body only runs when the function is called.
            if value.get("node_type") != "FunctionDefinitionOperation":
                for item in value.values():
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(typed(UftVbScriptParser().parse(text).operations))
    return names


def reachable(action_text: str, definitions: dict[str, dict[str, Any]]) -> list[str]:
    """Defined functions the action calls, directly or through other functions, in call order."""
    order: list[str] = []
    pending = sorted(called_names(action_text) & set(definitions))
    while pending:
        name = pending.pop(0)
        if name in order:
            continue
        order.append(name)
        body = definitions[name]["source"].split("\n", 1)[1] if "\n" in definitions[name]["source"] else ""
        pending += sorted((called_names(body) & set(definitions)) - set(order))
    return order
