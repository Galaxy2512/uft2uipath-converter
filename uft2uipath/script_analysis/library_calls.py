"""Names the function library behind a call the converter cannot map.

A call to a function defined in a .qfl/.txt library is still a blocker, but
"calls Excel_ReadValue, defined in Flight_utils.qfl" is reviewable while
"unsupported statement" is not.
"""

from __future__ import annotations

import re
from typing import Any

CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
BLOCKED_CODES = {"unsupported_statement", "unsupported_expression"}


def annotate_library_calls(analysis: dict[str, Any], functions: dict[str, str]) -> None:
    """functions maps a lower-case function name to the library that defines it."""
    if not functions:
        return
    for issue in analysis.get("issues", []):
        if issue.get("code") not in BLOCKED_CODES:
            continue
        called = [name for name in CALL.findall(issue.get("raw") or "")
                  if name.casefold() in functions]
        if called:
            issue["library_functions"] = [
                {"name": name, "library": functions[name.casefold()]} for name in dict.fromkeys(called)
            ]
