"""
UFT VBScript Parser

Responsibility
--------------
Parses a supported subset of UFT/VBScript into neutral script AST nodes.

Supported
--------
- object statements over any test-object hierarchy: Set, SetSecure, Click
  (with recorded coordinates), Select, Navigate, Sync, Activate, Close, Back
- OptionalStep. prefixed steps, and UFT's " @@ ..." step metadata
- If / ElseIf / Else / End If, with Exist or a comparison as the condition
- Wait, Dim, Option, assignments to variables
- Reporter.ReportEvent, ExitTest
- Parameter("..."), Environment("..."), DataTable("...", sheet),
  string and numeric literals

Important
---------
This is intentionally not a complete VBScript parser yet.

Unsupported statements are preserved as UnknownScriptOperation objects.
Nothing is silently discarded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from uft2uipath.parser.uft_script_nodes import (
    ActivateOperation,
    AssignOperation,
    BackOperation,
    CheckpointOperation,
    ClickOperation,
    CloseOperation,
    ComparisonCondition,
    ConcatenationExpression,
    DataTableReference,
    DeclarationOperation,
    FunctionDefinitionOperation,
    NoEffectOperation,
    ObjectAssignmentOperation,
    ParameterAssignmentOperation,
    EnvironmentReference,
    ExistCondition,
    ExitTestOperation,
    IfOperation,
    LiteralValue,
    NavigateOperation,
    ObjectReference,
    ParameterReference,
    ReportEventOperation,
    ScriptOperation,
    SelectOperation,
    SetSecureTextOperation,
    SetTextOperation,
    SyncOperation,
    UnknownScriptOperation,
    UnknownValueExpression,
    ValueExpression,
    VariableReference,
    WaitOperation,
)
from uft2uipath.uft.object_references import split_chain


@dataclass
class ParsedScript:
    """
    Result of parsing one UFT script.
    """

    operations: list[ScriptOperation]
    source_lines: list[str]


class UftVbScriptParser:
    """
    Parses line-oriented UFT/VBScript source.
    """

    # Matches one item in the UFT object hierarchy:
    #
    # Browser("BrowserName")
    # Page("PageName")
    # WebEdit("Username")
    OBJECT_PART_PATTERN = re.compile(
        r'(?P<type>[A-Za-z_]\w*)'
        r'\(\s*"(?P<name>[^"]+)"\s*\)',
    )

    IF_PATTERN = re.compile(
        r"^\s*(?P<keyword>ElseIf|If)\s+(?P<condition>.+?)\s+Then\s*$",
        re.IGNORECASE,
    )

    EXIST_PATTERN = re.compile(
        r"^(?P<object>.+?)\.Exist\s*(?:\(\s*(?P<timeout>.*?)\s*\))?\s*$",
        re.IGNORECASE,
    )

    COMPARISON_PATTERN = re.compile(
        r"^(?P<left>.+?)\s*(?P<operator><>|<=|>=|=|<|>)\s*(?P<right>.+)$",
    )

    # Statement metadata UFT appends to recorded steps.
    METADATA = " @@ "
    OPTIONAL_STEP = re.compile(r"^\s*OptionalStep\s*\.\s*", re.IGNORECASE)

    FUNCTION_PATTERN = re.compile(
        r"^\s*(?:(?P<scope>Public|Private)\s+)?(?:Default\s+)?"
        r"(?P<keyword>Function|Sub)\s+(?P<name>[A-Za-z_]\w*)\s*(?:\((?P<parameters>.*)\))?\s*$",
        re.IGNORECASE,
    )
    WITH_PATTERN = re.compile(r"^\s*With\s+(?P<target>.+?)\s*$", re.IGNORECASE)
    CHECKPOINT_PATTERN = re.compile(
        r'^\s*Check\s+CheckPoint\s*\(\s*"(?P<name>(?:[^"]|"")*)"\s*\)\s*$', re.IGNORECASE,
    )
    PARAMETER_ASSIGNMENT_PATTERN = re.compile(
        r'^\s*Parameter\s*\(\s*"(?P<name>(?:[^"]|"")*)"\s*\)\s*=\s*(?P<value>.+?)\s*$', re.IGNORECASE,
    )
    OBJECT_ASSIGNMENT_PATTERN = re.compile(
        r"^\s*Set\s+(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<expression>.+?)\s*$", re.IGNORECASE,
    )
    NO_EFFECT_PATTERN = re.compile(r"^\s*(?P<keyword>Randomize)\s*$", re.IGNORECASE)
    WAIT_PATTERN = re.compile(r"^\s*Wait\s*\(?\s*(?P<seconds>[^),]+?)\s*\)?\s*$", re.IGNORECASE)
    DECLARATION_PATTERN = re.compile(r"^\s*(?P<keyword>Dim|Option)\s+(?P<names>.+?)\s*$", re.IGNORECASE)
    ASSIGNMENT_PATTERN = re.compile(r"^\s*(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<value>.+?)\s*$")
    METHOD_PATTERN = re.compile(r"^\.\s*(?P<method>[A-Za-z]\w*)\s*(?P<arguments>.*)$", re.DOTALL)
    COORDINATES_PATTERN = re.compile(r"^\(?\s*(?P<x>-?\d+)\s*,\s*(?P<y>-?\d+)\s*\)?$")
    DATA_TABLE_PATTERN = re.compile(
        r'^DataTable\s*\(\s*"(?P<column>(?:[^"]|"")*)"\s*(?:,\s*(?P<sheet>[^)]+?)\s*)?\)$',
        re.IGNORECASE,
    )
    VARIABLE_PATTERN = re.compile(r"^[A-Za-z_]\w*$")

    # Object methods that take no argument.
    SIMPLE_METHODS = {
        "sync": SyncOperation, "activate": ActivateOperation,
        "close": CloseOperation, "back": BackOperation,
    }
    # Object methods that take one value.
    VALUE_METHODS = {
        "set": SetTextOperation, "setsecure": SetSecureTextOperation,
        "select": SelectOperation, "navigate": NavigateOperation,
    }

    REPORT_EVENT_PATTERN = re.compile(
        r"^\s*Reporter\.ReportEvent\s+"
        r"(?P<status>[^,]+)\s*,\s*"
        r"(?P<title>[^,]+)\s*,\s*"
        r"(?P<message>.+?)\s*$",
        re.IGNORECASE,
    )

    EXIT_TEST_PATTERN = re.compile(
        r"^\s*ExitTest\s*\(\s*(?P<code>.*?)\s*\)\s*$",
        re.IGNORECASE,
    )

    PARAMETER_PATTERN = re.compile(
        r'^Parameter\(\s*"(?P<name>[^"]+)"\s*\)$',
        re.IGNORECASE,
    )

    ENVIRONMENT_PATTERN = re.compile(
        r'^Environment\(\s*"(?P<name>[^"]+)"\s*\)$',
        re.IGNORECASE,
    )

    STRING_LITERAL_PATTERN = re.compile(
        r'^"(?P<value>(?:[^"]|"")*)"$',
        re.DOTALL,
    )

    INTEGER_PATTERN = re.compile(r"^-?\d+$")

    def parse(self, source: str) -> ParsedScript:
        """
        Parse complete UFT/VBScript source.

        Parameters
        ----------
        source:
            Extracted readable UFT/VBScript.

        Returns
        -------
        ParsedScript:
            Parsed operations and normalized source lines.
        """

        source_lines = self._normalize_lines(source)

        operations, next_index, terminator = self._parse_block(
            lines=source_lines,
            start_index=0,
            expected_terminators=set(),
        )

        # At top level there must not be an unexpected Else or End If.
        if terminator is not None:
            operations.append(
                UnknownScriptOperation(
                    raw=source_lines[next_index],
                    line_number=next_index + 1,
                    reason=f"Unexpected block terminator: {terminator}",
                )
            )

        return ParsedScript(
            operations=operations,
            source_lines=source_lines,
        )

    def _parse_block(
        self,
        lines: list[str],
        start_index: int,
        expected_terminators: set[str],
    ) -> tuple[list[ScriptOperation], int, str | None]:
        """
        Parse statements until EOF or a block terminator is found.

        Returns
        -------
        tuple:
            operations, current index, terminator
        """

        operations: list[ScriptOperation] = []
        index = start_index

        while index < len(lines):
            line = lines[index]
            code = self._code(line)
            normalized = code.strip().lower()

            # Empty lines and VBScript comments do not generate operations.
            if not normalized:
                index += 1
                continue

            if normalized == "else":
                if "else" in expected_terminators:
                    return operations, index, "else"

                operations.append(
                    UnknownScriptOperation(
                        raw=line,
                        line_number=index + 1,
                        reason="Unexpected block terminator: else",
                    )
                )
                index += 1
                continue

            terminator = self._terminator(normalized)
            if terminator:
                if terminator in expected_terminators:
                    return operations, index, terminator
                operations.append(
                    UnknownScriptOperation(
                        raw=line, line_number=index + 1,
                        reason=f"Unexpected block terminator: {terminator}",
                    )
                )
                index += 1
                continue

            function_match = self.FUNCTION_PATTERN.match(code)
            if function_match:
                operation, index = self._parse_function(lines, index, function_match)
                operations.append(operation)
                continue

            with_match = self.WITH_PATTERN.match(code)
            if with_match and split_chain(with_match.group("target"))[0]:
                inner, index = self._parse_with(lines, index, with_match.group("target"))
                operations.extend(inner)
                continue

            if re.fullmatch(r"end[ \t]*if", normalized):
                if "end_if" in expected_terminators:
                    return operations, index, "end_if"

                operations.append(
                    UnknownScriptOperation(
                        raw=line,
                        line_number=index + 1,
                        reason="Unexpected block terminator: end_if",
                    )
                )
                index += 1
                continue

            if_match = self.IF_PATTERN.match(code)

            if if_match and if_match.group("keyword").lower() == "elseif":
                if "elseif" in expected_terminators:
                    return operations, index, "elseif"
                operations.append(
                    UnknownScriptOperation(
                        raw=line,
                        line_number=index + 1,
                        reason="Unexpected block terminator: elseif",
                    )
                )
                index += 1
                continue

            if if_match:
                if_operation, index = self._parse_if(
                    lines=lines,
                    if_index=index,
                    condition=if_match.group("condition"),
                )
                operations.append(if_operation)
                continue

            operations.append(
                self._parse_statement(
                    line=line,
                    line_number=index + 1,
                )
            )

            index += 1

        return operations, index, None

    def _parse_if(
        self,
        lines: list[str],
        if_index: int,
        condition: str,
    ) -> tuple[IfOperation, int]:
        """
        Parse an If / ElseIf / Else / End If block.
        """

        raw_if = lines[if_index]
        parsed_condition = self._parse_condition(condition)

        # Parse everything after If until ElseIf, Else or End If.
        then_operations, index, terminator = self._parse_block(
            lines=lines,
            start_index=if_index + 1,
            expected_terminators={"elseif", "else", "end_if"},
        )

        else_operations: list[ScriptOperation] = []

        if terminator == "elseif":
            # ElseIf continues the same block; represent it as a nested If.
            nested, index = self._parse_if(
                lines=lines,
                if_index=index,
                condition=self.IF_PATTERN.match(self._code(lines[index])).group("condition"),
            )
            return (
                IfOperation(
                    raw=raw_if,
                    line_number=if_index + 1,
                    condition=parsed_condition,
                    then_operations=then_operations,
                    else_operations=[nested],
                ),
                index,
            )

        if terminator == "else":
            # Continue after Else and stop at End If.
            else_operations, index, terminator = self._parse_block(
                lines=lines,
                start_index=index + 1,
                expected_terminators={"end_if"},
            )

        if terminator != "end_if":
            # Preserve malformed blocks instead of pretending they are valid.
            then_operations.append(
                UnknownScriptOperation(
                    raw=raw_if,
                    line_number=if_index + 1,
                    reason="If block does not contain a matching End If",
                )
            )

            return (
                IfOperation(
                    raw=raw_if,
                    line_number=if_index + 1,
                    condition=parsed_condition,
                    then_operations=then_operations,
                    else_operations=else_operations,
                ),
                index,
            )

        return (
            IfOperation(
                raw=raw_if,
                line_number=if_index + 1,
                condition=parsed_condition,
                then_operations=then_operations,
                else_operations=else_operations,
            ),
            index + 1,
        )

    def _terminator(self, normalized: str) -> str | None:
        if re.fullmatch(r"end[ \t]+(function|sub)", normalized):
            return "end_function"
        if re.fullmatch(r"end[ \t]+with", normalized):
            return "end_with"
        return None

    def _parse_function(self, lines, index, match) -> tuple[ScriptOperation, int]:
        """
        Parse Function/Sub ... End Function: its body is not part of the flow.
        """

        parameters = [p.strip() for p in (match.group("parameters") or "").split(",") if p.strip()]
        body, end_index, terminator = self._parse_block(
            lines=lines, start_index=index + 1, expected_terminators={"end_function"},
        )
        if terminator != "end_function":
            return UnknownScriptOperation(
                raw=lines[index], line_number=index + 1,
                reason=f"{match.group('keyword')} block has no matching End.",
            ), end_index
        return FunctionDefinitionOperation(
            raw=lines[index], line_number=index + 1,
            keyword=match.group("keyword").capitalize(), name=match.group("name"),
            parameters=parameters, body=body,
        ), end_index + 1

    def _parse_with(self, lines, index, target: str) -> tuple[list[ScriptOperation], int]:
        """
        Expand With <object> ... End With by prefixing its member statements.
        """

        prefix = target.strip()
        body: list[str] = []
        current = index + 1
        while current < len(lines):
            code = self._code(lines[current])
            if self._terminator(code.strip().lower()) == "end_with":
                break
            body.append(prefix + code.strip() if code.strip().startswith(".") else lines[current])
            current += 1
        operations, _, _ = self._parse_block(lines=body, start_index=0, expected_terminators=set())
        for operation in operations:
            # Keep the line numbers of the original script.
            operation.line_number = (operation.line_number or 1) + index + 1
        return operations, min(current + 1, len(lines))

    def _parse_condition(self, expression: str):
        """
        Parse an If condition: Exist, a comparison, or a preserved expression.
        """

        condition = expression.strip()

        exist_match = self.EXIST_PATTERN.match(condition)
        if exist_match:
            return ExistCondition(
                target=self._parse_object_reference(exist_match.group("object")),
                timeout=self._parse_value(exist_match.group("timeout") or ""),
                raw=condition,
            )

        comparison_match = self.COMPARISON_PATTERN.match(condition)
        if comparison_match:
            return ComparisonCondition(
                left=self._parse_value(comparison_match.group("left")),
                operator=comparison_match.group("operator"),
                right=self._parse_value(comparison_match.group("right")),
                raw=condition,
            )

        return self._parse_value(condition)

    def _parse_statement(
        self,
        line: str,
        line_number: int,
    ) -> ScriptOperation:
        """
        Parse one non-block VBScript statement.
        """

        code = self._code(line)
        optional = bool(self.OPTIONAL_STEP.match(code))
        if optional:
            code = self.OPTIONAL_STEP.sub("", code, count=1)

        operation = self._parse_code(code, line, line_number)
        operation.optional = optional
        return operation

    def _parse_code(self, code: str, line: str, line_number: int) -> ScriptOperation:
        steps, remainder = split_chain(code)
        if steps:
            return self._parse_object_statement(steps, remainder, code, line, line_number)

        parameter_match = self.PARAMETER_ASSIGNMENT_PATTERN.match(code)
        if parameter_match:
            return ParameterAssignmentOperation(
                raw=line, line_number=line_number,
                name=parameter_match.group("name").replace('""', '"'),
                value=self._parse_value(parameter_match.group("value")),
            )

        object_match = self.OBJECT_ASSIGNMENT_PATTERN.match(code)
        if object_match:
            return ObjectAssignmentOperation(
                raw=line, line_number=line_number,
                name=object_match.group("name"), expression=object_match.group("expression"),
            )

        no_effect_match = self.NO_EFFECT_PATTERN.match(code)
        if no_effect_match:
            return NoEffectOperation(raw=line, line_number=line_number,
                                     keyword=no_effect_match.group("keyword").capitalize())

        wait_match = self.WAIT_PATTERN.match(code)
        if wait_match:
            return WaitOperation(raw=line, line_number=line_number,
                                 seconds=self._parse_value(wait_match.group("seconds")))

        declaration_match = self.DECLARATION_PATTERN.match(code)
        if declaration_match:
            return DeclarationOperation(
                raw=line, line_number=line_number,
                keyword=declaration_match.group("keyword").capitalize(),
                names=[name.strip() for name in declaration_match.group("names").split(",")],
            )

        assignment_match = self.ASSIGNMENT_PATTERN.match(code)
        if assignment_match:
            return AssignOperation(raw=line, line_number=line_number,
                                   name=assignment_match.group("name"),
                                   value=self._parse_value(assignment_match.group("value")))

        return self._parse_keyword_statement(code, line, line_number)

    def _parse_object_statement(self, steps, remainder, code, line, line_number) -> ScriptOperation:
        """
        Parse <object hierarchy>.<method> <arguments>.
        """

        target = self._object_reference(steps, code[:len(code) - len(remainder)])
        method_match = self.METHOD_PATTERN.match(remainder.strip())
        if method_match is None:
            return UnknownScriptOperation(
                raw=line, line_number=line_number,
                reason="Object hierarchy is not followed by a supported method call.",
            )

        method = method_match.group("method").lower()
        arguments = method_match.group("arguments").strip()

        checkpoint_match = self.CHECKPOINT_PATTERN.match(remainder.strip().lstrip("."))
        if checkpoint_match:
            return CheckpointOperation(
                raw=line, line_number=line_number, target=target,
                name=checkpoint_match.group("name").replace('""', '"'),
            )

        if method == "click":
            coordinates = self.COORDINATES_PATTERN.match(arguments) if arguments else None
            if arguments and coordinates is None:
                return UnknownScriptOperation(
                    raw=line, line_number=line_number,
                    reason=f"Click arguments are not recorded coordinates: {arguments}",
                )
            return ClickOperation(
                raw=line, line_number=line_number, target=target,
                x=int(coordinates.group("x")) if coordinates else None,
                y=int(coordinates.group("y")) if coordinates else None,
            )

        if method in self.SIMPLE_METHODS:
            if arguments.strip("()"):
                return UnknownScriptOperation(
                    raw=line, line_number=line_number,
                    reason=f"{method} with arguments is not supported: {arguments}",
                )
            return self.SIMPLE_METHODS[method](raw=line, line_number=line_number, target=target)

        if method in self.VALUE_METHODS:
            if not arguments:
                return UnknownScriptOperation(
                    raw=line, line_number=line_number, reason=f"{method} requires a value.",
                )
            return self.VALUE_METHODS[method](
                raw=line, line_number=line_number, target=target,
                value=self._parse_value(self._unwrap(arguments)),
            )

        return UnknownScriptOperation(
            raw=line, line_number=line_number,
            reason=f"Object method has no validated mapping: {method_match.group('method')}",
        )

    def _parse_keyword_statement(self, code: str, line: str, line_number: int) -> ScriptOperation:
        report_match = self.REPORT_EVENT_PATTERN.match(code)

        if report_match:
            return ReportEventOperation(
                raw=line,
                line_number=line_number,
                status=report_match.group("status").strip(),
                title=self._parse_value(report_match.group("title")),
                message=self._parse_value(report_match.group("message")),
            )

        exit_match = self.EXIT_TEST_PATTERN.match(code)

        if exit_match:
            return ExitTestOperation(
                raw=line,
                line_number=line_number,
                code=self._parse_value(exit_match.group("code")),
            )

        return UnknownScriptOperation(
            raw=line,
            line_number=line_number,
        )

    def _parse_object_reference(self, expression: str) -> ObjectReference:
        """
        Parse a UFT object hierarchy, e.g. Browser("B").Page("P").WebEdit("u").
        """

        steps, _ = split_chain(expression)
        return self._object_reference(steps, expression)

    def _object_reference(self, steps, expression: str) -> ObjectReference:
        browser = page = object_type = logical_name = None

        for step in steps:
            kind = step.test_object_class
            if kind.lower() == "browser":
                browser = step.name
            elif kind.lower() == "page":
                page = step.name
            else:
                object_type = kind
                logical_name = step.name

        if object_type is None and page is not None:
            # A statement on the page itself, e.g. Page.Sync.
            object_type, logical_name = "Page", page

        return ObjectReference(
            browser=browser,
            page=page,
            object_type=object_type,
            logical_name=logical_name,
            raw=expression.strip(),
            path=[{"class": step.test_object_class, "name": step.name,
                   "description": dict(step.description)} for step in steps],
        )

    def _split_concatenation(self, value: str) -> list[str] | None:
        """
        Split a & b & c at the top level, ignoring & inside strings or calls.
        """

        parts, current, depth, in_string = [], "", 0, False
        for character in value:
            if character == '"':
                in_string = not in_string
            elif not in_string and character in "()":
                depth += 1 if character == "(" else -1
            elif not in_string and character == "&" and depth == 0:
                parts.append(current)
                current = ""
                continue
            current += character
        parts.append(current)
        stripped = [part.strip() for part in parts]
        return stripped if len(stripped) > 1 and all(stripped) else None

    def _unwrap(self, arguments: str) -> str:
        """
        Remove one pair of parentheses wrapping a whole argument: Navigate(URL).
        """

        value = arguments.strip()
        if not value.startswith("(") or not value.endswith(")"):
            return value
        depth = 0
        for index, character in enumerate(value):
            depth += (character == "(") - (character == ")")
            if depth == 0 and index < len(value) - 1:
                return value
        return value[1:-1].strip()

    def _code(self, line: str) -> str:
        """
        Strip UFT step metadata and a trailing comment outside string literals.
        """

        code = line.split(self.METADATA, 1)[0]
        in_string = False
        for index, character in enumerate(code):
            if character == '"':
                in_string = not in_string
            elif character == "'" and not in_string:
                code = code[:index]
                break
        code = code.strip()
        return "" if code.lower().startswith("rem ") else code

    def _parse_value(self, expression: str) -> ValueExpression:
        """
        Parse a supported UFT value expression.
        """

        value = expression.strip()

        parameter_match = self.PARAMETER_PATTERN.match(value)

        if parameter_match:
            return ParameterReference(
                raw=value,
                name=parameter_match.group("name"),
            )

        environment_match = self.ENVIRONMENT_PATTERN.match(value)

        if environment_match:
            return EnvironmentReference(
                raw=value,
                name=environment_match.group("name"),
            )

        data_table_match = self.DATA_TABLE_PATTERN.match(value)

        if data_table_match:
            return DataTableReference(
                raw=value,
                column=data_table_match.group("column").replace('""', '"'),
                sheet=(data_table_match.group("sheet") or "").strip() or None,
            )

        if self.VARIABLE_PATTERN.match(value) and value.lower() not in ("true", "false", "nothing"):
            return VariableReference(raw=value, name=value)

        parts = self._split_concatenation(value)
        if parts is not None:
            parsed = [self._parse_value(part) for part in parts]
            if not any(isinstance(part, UnknownValueExpression) for part in parsed):
                return ConcatenationExpression(raw=value, parts=parsed)

        string_match = self.STRING_LITERAL_PATTERN.match(value)

        if string_match:
            return LiteralValue(
                raw=value,
                value=string_match.group("value").replace('""', '"'),
            )

        if self.INTEGER_PATTERN.match(value):
            return LiteralValue(
                raw=value,
                value=int(value),
            )

        # Do not turn unparsed expressions into literal text.
        return UnknownValueExpression(raw=value)

    def _normalize_lines(self, source: str) -> list[str]:
        """
        Normalize line endings while preserving statement boundaries.
        """

        normalized = source.replace("\r\n", "\n").replace("\r", "\n")

        return [
            line.rstrip()
            for line in normalized.split("\n")
        ]