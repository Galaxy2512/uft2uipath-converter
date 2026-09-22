"""VBScript Functions and Subs as UiPath workflows (library functions, strategy A).

Every Function/Sub a migrated action calls - defined in the action itself or in
an associated function library - becomes its own workflow under Functions\\,
called with Invoke Workflow File:

- each VBScript parameter becomes an In argument typed from the call's argument;
  one the body assigns becomes InOut, so a ByRef caller variable changes as in
  VBScript (ByVal, or an argument that is no variable, passes a copy);
- the return value (FunctionName = value) becomes the Out argument out_result;
- values the body takes from the test (Environment, Parameter, DataTable) become
  In arguments of the same name the calling action passes on;
- library globals set once to a literal at load time are read as constants; a
  local Dim of the same name shadows them, changing them without one blocks;
- a reported failure sets the shared InOut failure flag, as in an action.

VBScript is untyped, so a function is compiled once per combination of argument
types and of the object selectors its body uses. What the converter cannot
reproduce blocks the function, and every call to it, with the reason.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from uft2uipath.mapping.acceptance import build_binding
from uft2uipath.script_analysis.analyzer import analyze_function
from uft2uipath.script_generation.emitter import RESULT_ARGUMENT, ComponentEmitter, target_key

FOLDER = "Functions"
_INVALID = re.compile(r"[^A-Za-z0-9_]")
_PARAMETER = re.compile(r"^(?:(?P<mode>ByVal|ByRef)\s+)?(?P<name>[A-Za-z_]\w*)$", re.IGNORECASE)
# Analysis findings about the body that do not block by themselves.
_INFORMATIONAL = {"function_definition_not_migrated"}


@dataclass
class CompiledFunction:
    """One workflow generated for a function: how to call it and whether it is complete."""
    name: str
    origin: str
    workflow: str | None
    # Per parameter, in call order: {"vb", "argument", "kind", "direction", "byref"}.
    # A parameter the body assigns is InOut; byref says whether the caller's variable changes.
    parameters: list[dict[str, Any]]
    result: str | None
    # Arguments the caller supplies from its own: environment/parameter/data values, failure flag.
    context_arguments: dict[str, str] = field(default_factory=dict)
    directions: dict[str, str] = field(default_factory=dict)
    exits_test: bool = False
    status: str = "mapped_unverified"
    reason: str | None = None
    # An empty Function/Sub: calling it does nothing, so no workflow is needed.
    empty: bool = False
    report: dict[str, Any] = field(default_factory=dict)


class UserFunctions:
    """Project-wide catalog of compiled functions; its workflows are written with the project."""

    def __init__(self):
        """Start empty; functions are compiled when an action first calls them."""
        self.compiled: dict[tuple, CompiledFunction] = {}
        # Workflow file name -> XAML root, written to Functions\\ by the project emitter.
        self.workflows: dict[str, Any] = {}
        self._analyses: dict[tuple[str, str], dict | None] = {}
        self._names: dict[str, int] = {}
        self._stack: list[tuple[str, str]] = []

    def compile(self, definition: dict, name: str, argument_types: list[str], objects: list[dict],
                definitions: dict) -> CompiledFunction:
        """Workflow for a call to name with these argument types, compiling it on first use.

        definition is {"origin", "source"} of the function; objects are the
        caller's selector bindings; definitions are the functions the body may call.
        """
        origin = definition["origin"]
        analysis = self._analysis(origin, name, definition["source"])
        if analysis is None:
            return self._blocked(name, origin, "its definition could not be parsed")
        used = {target_key(obj) for obj in analysis["references"]["objects"]}
        relevant = sorted((o for o in objects if target_key(o.get("uft") or {}) in used),
                          key=lambda o: json.dumps(o, sort_keys=True))
        key = (origin.casefold(), name.casefold(), tuple(argument_types),
               json.dumps(relevant, sort_keys=True))
        if key in self.compiled:
            return self.compiled[key]
        if (origin.casefold(), name.casefold()) in self._stack:
            return self._blocked(name, origin, "it calls itself recursively")
        self._stack.append((origin.casefold(), name.casefold()))
        try:
            compiled = self._compile(name, origin, analysis, argument_types, relevant, definitions,
                                     definition.get("constants") or {})
        finally:
            self._stack.pop()
        self.compiled[key] = compiled
        return compiled

    def reports(self) -> dict[str, dict]:
        """Generation report of every compiled function workflow, by workflow path."""
        return {c.workflow: c.report for c in self.compiled.values() if c.workflow}

    def _analysis(self, origin, name, source):
        """Analysis of a function's body, parsed once per function."""
        key = (origin.casefold(), name.casefold())
        if key not in self._analyses:
            self._analyses[key] = analyze_function(source)
        return self._analyses[key]

    def _compile(self, name, origin, analysis, argument_types, objects, definitions,
                 constants) -> CompiledFunction:
        """Compile one signature of a function into a workflow and describe how to call it.

        Blocks, with the reason, what cannot be reproduced: unsupported parameters,
        a wrong argument count, output parameters or secure values in the body.
        """
        assigned, declared = _assigned_and_declared(analysis["operations"])
        parameters = []
        for raw, kind in zip(analysis["parameters"], argument_types):
            match = _PARAMETER.match(raw.strip())
            if match is None:
                return self._blocked(name, origin, f"parameter {raw!r} (optional or array) is not supported")
            vb_name = match.group("name")
            written = vb_name.casefold() in assigned
            parameters.append({
                "vb": vb_name, "kind": kind,
                "argument": ("io_arg_" if written else "in_arg_") + _INVALID.sub("_", vb_name),
                "direction": "InOut" if written else "In",
                # VBScript passes ByRef unless ByVal says otherwise.
                "byref": written and (match.group("mode") or "ByRef").lower() == "byref",
            })
        if len(analysis["parameters"]) != len(argument_types):
            return self._blocked(name, origin, f"it takes {len(parameters)} arguments, "
                                               f"called with {len(argument_types)}")
        if not analysis["operations"]:
            return CompiledFunction(name=name, origin=origin, workflow=None, parameters=[],
                                    result=None, empty=True)
        references = analysis["references"]
        if references["outputs"] or references["secure"]:
            return self._blocked(name, origin, "it writes output parameters or secure values")
        bindings = build_binding(analysis, [])
        bindings["objects"] = objects
        file_name = self._file_name(name)
        emitter = ComponentEmitter(
            f"{origin}:{name}", {**analysis, "function_definitions": definitions,
                                 "issues": [i for i in analysis["issues"] if i["code"] not in _INFORMATIONAL]},
            bindings, workflow_name=file_name, functions=self,
            # A local Dim of a library global's name makes it a local variable instead.
            function={"name": name, "parameters": parameters,
                      "constants": {k: v for k, v in constants.items() if k not in declared}},
        )
        root, report = emitter.generate()
        report.update(function=name, origin=origin, workflow=f"{FOLDER}\\{file_name}.xaml")
        own = {p["argument"] for p in parameters} | {RESULT_ARGUMENT}
        compiled = CompiledFunction(
            name=name, origin=origin, workflow=f"{FOLDER}\\{file_name}.xaml", parameters=parameters,
            result=emitter.result_type,
            context_arguments={a: k for a, k in report["arguments"].items() if a not in own},
            directions=dict(report.get("argument_directions", {})),
            exits_test=bool(report.get("exits_test")),
            status=report["status"], report=report,
        )
        if report["status"] == "blocked":
            first = report["issues"][0]
            compiled.reason = f"line {first.get('line_number')}: {first.get('message')}"
        self.workflows[file_name] = root
        return compiled

    def _file_name(self, name: str) -> str:
        """Workflow name for a function; a second signature gets a numbered name."""
        base = "Function_" + _INVALID.sub("_", name)
        count = self._names.get(base.casefold(), 0) + 1
        self._names[base.casefold()] = count
        # A second signature (other argument types or selectors) gets its own workflow.
        return base if count == 1 else f"{base}_{count}"

    @staticmethod
    def _blocked(name, origin, reason) -> CompiledFunction:
        """A function that cannot be called, with the reason every call reports."""
        return CompiledFunction(name=name, origin=origin, workflow=None, parameters=[], result=None,
                                status="blocked", reason=reason)


def _assigned_and_declared(operations) -> tuple[set[str], set[str]]:
    """Lower-case names a body assigns, and the names it declares with Dim, anywhere in it."""
    assigned, declared = set(), set()

    def walk(value):
        """Collect assigned and Dim-declared names below a node."""
        if isinstance(value, dict):
            if value.get("node_type") == "AssignOperation":
                assigned.add((value.get("name") or "").casefold())
            if value.get("node_type") == "DeclarationOperation" and (value.get("keyword") or "").lower() == "dim":
                declared.update(n.split("(")[0].strip().casefold() for n in value.get("names") or [])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(operations)
    return assigned, declared
