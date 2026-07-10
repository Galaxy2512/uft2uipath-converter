"""
Component Entity Parser

Responsibility
--------------
Converts one ALM COMPONENT table row into a BusinessComponent AST object.

The parser isolates ALM-specific column names from the neutral AST.
The UiPath generator therefore does not need to know about fields such as:

- CO_ID
- CO_NAME
- CO_STATUS
- CO_SCRIPT_TYPE
"""

from typing import Any

from uft2uipath.ast import BusinessComponent


class ComponentEntityParser:
    """
    Maps one decoded ALM COMPONENT row to BusinessComponent.
    """

    def parse(self, row: dict[str, Any]) -> BusinessComponent:
        """
        Convert an ALM COMPONENT row into a neutral AST object.

        Parameters
        ----------
        row:
            Dictionary containing one decoded COMPONENT table record.

        Returns
        -------
        BusinessComponent:
            Neutral Business Component representation.
        """

        return BusinessComponent(
            id=self._to_int(row.get("CO_ID")),
            name=str(row.get("CO_NAME") or "UnnamedComponent"),
            alm_status=row.get("CO_STATUS"),
            script_type=row.get("CO_SCRIPT_TYPE"),
            component_type=row.get("CO_BPTA_COMPONENT_TYPE"),
            description=row.get("CO_DESC"),
            raw=dict(row),
        )

    def _to_int(self, value: Any) -> int | None:
        """
        Safely convert an ALM numeric field to integer.
        """

        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None