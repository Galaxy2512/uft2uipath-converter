# Tests the two registries that classify what a UFT script calls: VBScript
# built-in functions and methods on objects. They must agree with what the
# emitters actually translate, classify every name the emitters can meet, and
# tell a library function apart from a built-in nobody has mapped yet.
import pytest

from uft2uipath.contracts.status import EMITTED, STATUSES
from uft2uipath.mapping import function_registry, object_method_registry
from uft2uipath.mapping.inventory import build_inventory
from uft2uipath.script_generation.emitters.functions import FUNCTIONS
from uft2uipath.script_generation.emitters.objects import FILE_SYSTEM_METHODS


def blocked(raw, message="Unsupported or malformed value expression"):
    """An inventory over one blocked line whose expression is the given source."""
    return build_inventory([{
        "project_name": "P",
        "workflows": {"a/A": {
            "trace": [{"line_number": 1, "node_type": "AssignOperation", "status": "blocked"}],
            "issues": [{"code": "unsupported_expression", "line_number": 1,
                        "message": message, "raw": raw}]}},
        "tests": [],
    }])


def test_the_registries_and_the_emitters_promise_the_same_names():
    # Each registry checks this at import too; here it is a test failure, not a crash.
    function_registry.implemented(set(FUNCTIONS))
    object_method_registry.implemented(object_method_registry.FILE_SYSTEM_OBJECT,
                                       set(FILE_SYSTEM_METHODS))
    for entry in function_registry.REGISTRY.values():
        assert entry.status in STATUSES
        assert (entry.name in FUNCTIONS) == (entry.status in EMITTED)


def test_an_unmapped_builtin_says_why_it_is_not_mapped():
    assert function_registry.status_of("Split") == "requires_strategy"
    assert "array" in function_registry.lookup("split").notes.lower()
    assert function_registry.status_of("Round") == "planned"
    assert function_registry.lookup("CSTR").status == "supported"


def test_a_name_no_vbscript_defines_is_not_a_builtin():
    assert function_registry.lookup("Excel_ReadValue") is None
    assert function_registry.status_of("Excel_ReadValue") == "unknown"


def test_method_lookup_knows_the_owner_and_the_operation_behind_it():
    fso = object_method_registry.lookup(object_method_registry.FILE_SYSTEM_OBJECT, "BuildPath")
    assert fso.status == "supported" and fso.returns == "String"
    assert object_method_registry.find("WaitProperty").status == "requires_strategy"
    assert object_method_registry.find("Click").node_type == "ClickOperation"
    assert object_method_registry.status_of("NoSuchMethod") == "unknown"


@pytest.mark.parametrize("name, source, status", [
    ("Excel_ReadValue", "user_or_library", "unknown"),
    ("Split", "vbscript_builtin", "requires_strategy"),
    ("Len", "vbscript_builtin", "supported"),
])
def test_a_blocked_line_reports_what_each_call_is(name, source, status):
    fact = blocked(f'x = {name}("a")')["blocked_calls"]["functions"][name]
    assert (fact["source"], fact["status"], fact["count"]) == (source, status, 1)


def test_missing_work_is_listed_before_names_that_are_already_translated():
    order = list(blocked('x = CStr(Excel_ReadValue("A1"))')["blocked_calls"]["functions"])
    assert order == ["Excel_ReadValue", "CStr"]
