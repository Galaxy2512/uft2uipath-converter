# Keeps the layers of the converter pointing one way. What the mapping decides
# must not depend on how XAML is written, or the two drift into needing each
# other: the shared vocabulary belongs in uft2uipath.contracts instead.
import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "uft2uipath"
# layer -> the layers it may not import (directly or through a submodule).
FORBIDDEN = {
    "contracts": ("mapping", "script_generation", "script_analysis", "parser", "alm", "uft"),
    "parser": ("mapping", "script_generation"),
    "script_analysis": ("script_generation",),
    "mapping": ("script_generation",),
}


def imported_packages(path: Path) -> set[str]:
    """Names of uft2uipath subpackages a module imports, however it spells the import."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return {name.split(".")[1] for name in names
            if name.split(".")[0] == "uft2uipath" and "." in name}


@pytest.mark.parametrize("layer, forbidden", sorted(FORBIDDEN.items()))
def test_layer_does_not_import_a_later_one(layer, forbidden):
    for path in sorted((PACKAGE / layer).rglob("*.py")):
        offending = imported_packages(path) & set(forbidden)
        assert not offending, f"{path.relative_to(PACKAGE)} imports {', '.join(sorted(offending))}"
