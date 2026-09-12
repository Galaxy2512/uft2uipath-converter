"""Typed, loss-aware analysis of the current supported parser subset."""
import re
from collections import Counter
from dataclasses import fields, is_dataclass

from uft2uipath.parser.uft_vbscript_parser import UftVbScriptParser
from uft2uipath.parser.uft_script_nodes import (
    EnvironmentReference, ExistCondition, ObjectReference, ParameterReference,
    ScriptOperation, UnknownScriptOperation, UnknownValueExpression,
)


def typed(value):
    """Keep node kinds: dataclasses.asdict alone loses expression identities."""
    if is_dataclass(value):
        return {"node_type": type(value).__name__,
                **{f.name: typed(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, list):
        return [typed(item) for item in value]
    if isinstance(value, dict):
        return {key: typed(item) for key, item in value.items()}
    return value


def analyze_source(source):
    parsed = UftVbScriptParser().parse(source)
    issues, parameters, environments, objects = [], set(), set(), []
    kinds = Counter()

    def issue(code, message, line, raw):
        issues.append({"code": code, "message": message,
                       "line_number": line, "raw": raw, "severity": "blocker"})

    def walk(value, line=None):
        if isinstance(value, ScriptOperation):
            line = value.line_number
            kinds[type(value).__name__] += 1
            if isinstance(value, UnknownScriptOperation):
                issue("unsupported_statement", value.reason, line, value.raw)
            # Reporter arguments must be split using VBScript quoting rules.
            # The legacy parser splits at commas; do not certify ambiguous calls.
            if type(value).__name__ == "ReportEventOperation":
                status = (value.status or "").lower()
                if status not in {"micpass", "micfail", "micdone", "micwarning", "0", "1", "2", "3"}:
                    issue("unresolved_report_status", "Report status needs interpretation.", line, value.raw)
                issue("assertion_mapping_required",
                      "Preserve report severity and test outcome; logging alone is insufficient.",
                      line, value.raw)
            if type(value).__name__ == "SetSecureTextOperation":
                issue("secure_value_mapping_required",
                      "UFT secure values need an explicit UiPath credential mapping.",
                      line, value.raw)
            if type(value).__name__ == "ExitTestOperation":
                issue("exit_mapping_required",
                      "ExitTest scope and outcome need explicit target semantics.",
                      line, value.raw)
        if isinstance(value, UnknownValueExpression):
            issue("unsupported_expression", value.reason, line, value.raw)
        if isinstance(value, ParameterReference):
            parameters.add(value.name)
            issue("parameter_binding_required",
                  "Reference preserved; argument direction, type and call binding are not resolved.",
                  line, value.raw)
        if isinstance(value, EnvironmentReference):
            environments.add(value.name)
            issue("environment_binding_required",
                  "Environment reference requires target mapping.", line, value.raw)
        if isinstance(value, ObjectReference):
            objects.append(typed(value))
            # Reject partial regex matches masquerading as complete object chains.
            pattern = UftVbScriptParser.OBJECT_PART_PATTERN
            matches = list(pattern.finditer(value.raw))
            residual = pattern.sub("", value.raw)
            types = [m.group("type").lower() for m in matches]
            if (
                not matches or re.sub(r"[. \t]", "", residual)
                or types[:2] != ["browser", "page"] or len(types) != 3
                or not value.object_type or not value.logical_name
            ):
                issue("unsupported_object_chain",
                      "Object hierarchy was not completely interpreted.", line, value.raw)
            issue("selector_mapping_required",
                  "Logical UFT object reference preserved; UiPath selector is unresolved.",
                  line, value.raw)
        if isinstance(value, ExistCondition):
            issue("exist_mapping_required",
                  "Exist timeout and Boolean result need equivalent UiPath behavior.",
                  line, value.raw)
        if is_dataclass(value):
            for field in fields(value):
                walk(getattr(value, field.name), line)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item, line)

    for operation in parsed.operations:
        walk(operation)
    operation_count = sum(kinds.values())
    unsupported = kinds.get("UnknownScriptOperation", 0)
    # Block markers/comments are retained in source, not counted as operations.
    if operation_count == 0:
        issue("empty_script", "No operations parsed; requires review.", None, "")
    return {
        "operations": typed(parsed.operations),
        "source_lines": parsed.source_lines,
        "references": {
            "parameters": sorted(parameters),
            "environment": sorted(environments),
            "objects": objects,
        },
        "coverage": {
            "operation_count": operation_count,
            "recognized_operation_count": operation_count - unsupported,
            "unsupported_statement_count": unsupported,
            "unsupported_expression_count": sum(
                item["code"] == "unsupported_expression" for item in issues
            ),
            "operation_kinds": dict(sorted(kinds.items())),
            "definition": "Recognition of parser nodes, not migration or execution success.",
        },
        "issues": issues,
        "executable_verified": False,
        "generation_ready": False,
    }
