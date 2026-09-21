"""
Step Entity Parser

Responsibility
--------------
Converts one ALM COMPONENT_STEP row into a Step AST object.

A Step is the smallest executable unit that will later
be translated into one or more UiPath activities.
"""

from typing import Any

from uft2uipath.ast import Step, StepType


class StepEntityParser:
    """
    Maps ALM COMPONENT_STEP rows to AST Step objects.
    """

    def parse(self, row: dict[str, Any]) -> Step:
        return Step(
            id=self._to_int(row.get("CS_STEP_ID")),
            order=self._to_int(row.get("CS_STEP_ORDER")),
            name=str(row.get("CS_STEP_NAME") or "Unnamed Step"),
            description=row.get("CS_DESCRIPTION"),
            expected_result=row.get("CS_EXPECTED"),
            type=StepType.UNKNOWN,
            raw=row,
        )

    def _to_int(self, value: Any) -> int | None:
        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None