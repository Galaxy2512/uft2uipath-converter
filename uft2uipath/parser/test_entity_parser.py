"""
Test Entity Parser

Responsibility
--------------
Converts one ALM TEST table row into a UftTestCase AST object.

Input
-----
Dictionary representing one row from the ALM TEST table.

Output
------
UftTestCase

Why this exists
---------------
The UiPath generator must not know anything about ALM column names
such as TS_TEST_ID or TS_NAME.

This parser isolates ALM-specific field mapping in one place.
"""

from typing import Any

from uft2uipath.ast import UftTestCase


class TestEntityParser:
    """
    Maps ALM TEST table rows to AST test cases.
    """

    def parse(self, row: dict[str, Any]) -> UftTestCase:
        """
        Convert one ALM TEST row into UftTestCase.
        """

        return UftTestCase(
            id=self._to_int(row.get("TS_TEST_ID")),
            name=str(row.get("TS_NAME") or "UnnamedTest"),
            alm_status=row.get("TS_STATUS"),
            test_type=row.get("TS_TYPE"),
            execution_status=row.get("TS_EXEC_STATUS"),
            description=row.get("TS_DESCRIPTION"),
            raw=row,
        )

    def _to_int(self, value: Any) -> int | None:
        """
        Safely convert ALM numeric values to int.
        """

        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None