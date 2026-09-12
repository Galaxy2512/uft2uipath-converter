"""
UFT VBScript Parser

Responsibility
--------------
Parses a supported subset of UFT/VBScript into neutral script AST nodes.

Initially supported
-------------------
- If <object>.Exist(timeout) Then
- Else
- End If
- Reporter.ReportEvent
- ExitTest
- WebEdit.Set
- WebEdit.SetSecure
- Click
- Parameter("...")
- Environment("...")
- string and numeric literals

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
    ClickOperation,
    EnvironmentReference,
    ExistCondition,
    ExitTestOperation,
    IfOperation,
    LiteralValue,
    ObjectReference,
    ParameterReference,
    ReportEventOperation,
    ScriptOperation,
    SetSecureTextOperation,
    SetTextOperation,
    UnknownScriptOperation,
    UnknownValueExpression,
    ValueExpression,
)


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
        r'(?P<type>Browser|Page|WebEdit|WebButton|WebElement)'
        r'\(\s*"(?P<name>[^"]+)"\s*\)',
        re.IGNORECASE,
    )

    IF_EXIST_PATTERN = re.compile(
        r"^\s*If\s+(?P<object>.+?)"
        r"\.Exist\s*\(\s*(?P<timeout>.*?)\s*\)"
        r"\s+Then\s*$",
        re.IGNORECASE,
    )

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

    SET_SECURE_PATTERN = re.compile(
        r"^\s*(?P<object>.+?)"
        r"\.SetSecure\s+(?P<value>.+?)\s*$",
        re.IGNORECASE,
    )

    SET_PATTERN = re.compile(
        r"^\s*(?P<object>.+?)"
        r"\.Set\s+(?P<value>.+?)\s*$",
        re.IGNORECASE,
    )

    CLICK_PATTERN = re.compile(
        r"^\s*(?P<object>.+?)"
        r"\.Click\s*$",
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
            normalized = line.strip().lower()

            # Empty lines and VBScript comments do not generate operations.
            if not normalized or normalized.startswith("'"):
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

            if_match = self.IF_EXIST_PATTERN.match(line)

            if if_match:
                if_operation, index = self._parse_if(
                    lines=lines,
                    if_index=index,
                    match=if_match,
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
        match: re.Match[str],
    ) -> tuple[IfOperation, int]:
        """
        Parse an If / Else / End If block.
        """

        raw_if = lines[if_index]

        condition = ExistCondition(
            target=self._parse_object_reference(match.group("object")),
            timeout=self._parse_value(match.group("timeout")),
            raw=match.group(0),
        )

        # Parse everything after If until Else or End If.
        then_operations, index, terminator = self._parse_block(
            lines=lines,
            start_index=if_index + 1,
            expected_terminators={"else", "end_if"},
        )

        else_operations: list[ScriptOperation] = []

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
                    condition=condition,
                    then_operations=then_operations,
                    else_operations=else_operations,
                ),
                index,
            )

        return (
            IfOperation(
                raw=raw_if,
                line_number=if_index + 1,
                condition=condition,
                then_operations=then_operations,
                else_operations=else_operations,
            ),
            index + 1,
        )

    def _parse_statement(
        self,
        line: str,
        line_number: int,
    ) -> ScriptOperation:
        """
        Parse one non-block VBScript statement.
        """

        report_match = self.REPORT_EVENT_PATTERN.match(line)

        if report_match:
            return ReportEventOperation(
                raw=line,
                line_number=line_number,
                status=report_match.group("status").strip(),
                title=self._parse_value(report_match.group("title")),
                message=self._parse_value(report_match.group("message")),
            )

        exit_match = self.EXIT_TEST_PATTERN.match(line)

        if exit_match:
            return ExitTestOperation(
                raw=line,
                line_number=line_number,
                code=self._parse_value(exit_match.group("code")),
            )

        set_secure_match = self.SET_SECURE_PATTERN.match(line)

        if set_secure_match:
            return SetSecureTextOperation(
                raw=line,
                line_number=line_number,
                target=self._parse_object_reference(
                    set_secure_match.group("object")
                ),
                value=self._parse_value(
                    set_secure_match.group("value")
                ),
            )

        set_match = self.SET_PATTERN.match(line)

        if set_match:
            return SetTextOperation(
                raw=line,
                line_number=line_number,
                target=self._parse_object_reference(
                    set_match.group("object")
                ),
                value=self._parse_value(
                    set_match.group("value")
                ),
            )

        click_match = self.CLICK_PATTERN.match(line)

        if click_match:
            return ClickOperation(
                raw=line,
                line_number=line_number,
                target=self._parse_object_reference(
                    click_match.group("object")
                ),
            )

        return UnknownScriptOperation(
            raw=line,
            line_number=line_number,
        )

    def _parse_object_reference(self, expression: str) -> ObjectReference:
        """
        Parse a UFT object hierarchy.

        Example
        -------
        Browser("B").Page("P").WebEdit("Username")
        """

        browser: str | None = None
        page: str | None = None
        object_type: str | None = None
        logical_name: str | None = None

        for match in self.OBJECT_PART_PATTERN.finditer(expression):
            current_type = match.group("type")
            current_name = match.group("name")

            if current_type.lower() == "browser":
                browser = current_name
            elif current_type.lower() == "page":
                page = current_name
            else:
                object_type = current_type
                logical_name = current_name

        return ObjectReference(
            browser=browser,
            page=page,
            object_type=object_type,
            logical_name=logical_name,
            raw=expression.strip(),
        )

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