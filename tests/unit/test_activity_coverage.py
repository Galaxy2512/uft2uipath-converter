"""Emitter mappings for the operations added for real UFT scripts."""
import xml.etree.ElementTree as ET

from uft2uipath.script_analysis.analyzer import analyze_source
from uft2uipath.script_generation.emitter import ComponentEmitter, UI, X, q

OBJECTS = (("WebEdit", "User"), ("WebList", "fromPort"), ("WebButton", "Go"), ("Page", "P"))


def bindings():
    return {
        "data": {"Username": {"name": "in_data_Username", "type": "String", "direction": "In"}},
        "objects": [
            {"uft": {"browser": "B", "page": "P", "object_type": kind, "logical_name": name},
             "selector": f"<html title='Fixture' /><webctrl id='{name}' />",
             "verified": True, "input_method": "Simulate", "timeout_ms": 30000,
             "browser_type": "Edge"}
            for kind, name in OBJECTS
        ],
    }


def emit(source):
    root, report = ComponentEmitter("10", analyze_source(source), bindings()).generate()
    return ET.fromstring(ET.tostring(root)), report


def test_select_becomes_select_item_inside_a_browser_scope():
    root, report = emit('Browser("B").Page("P").WebList("fromPort").Select "London"')

    select = root.find(".//" + q("SelectItem", UI))
    assert select is not None and select.attrib["Item"] == '["London"]'
    assert root.find(".//" + q("BrowserScope", UI)) is not None
    assert report["status"] == "mapped_unverified"


def test_sync_waits_for_the_page_and_records_the_approximation():
    root, report = emit('Browser("B").Page("P").Sync')

    assert root.find(".//" + q("WaitUiElementAppear", UI)) is not None
    assert "approximated" in report["trace"][0]["note"]
    # The page wait is not scoped to an attached browser.
    assert root.find(".//" + q("BrowserScope", UI)) is None


def test_wait_becomes_a_delay():
    root, report = emit("Wait 5")

    delay = root.find(".//" + q("Delay"))
    assert delay.attrib["Duration"] == "[TimeSpan.FromSeconds(5)]"
    assert report["status"] == "mapped_unverified"


def test_assignment_declares_a_string_variable_and_can_be_used_later():
    root, report = emit('URL = "http://x/"\nBrowser("B").Page("P").WebEdit("User").Set URL')

    variables = root.find(".//" + q("Sequence.Variables"))
    assert [v.attrib["Name"] for v in variables] == ["URL"]
    assert variables[0].attrib[q("TypeArguments", X)] == "x:String"
    assert root.find(".//" + q("TypeInto", UI)).attrib["Text"] == "[URL]"
    assert report["status"] == "mapped_unverified"


def test_unassigned_variables_block_instead_of_becoming_text():
    root, report = emit('Browser("B").Page("P").WebEdit("User").Set sUser')

    assert report["status"] == "blocked"
    assert root.find(".//" + q("TypeInto", UI)) is None
    assert any("sUser is not assigned" in issue["message"] for issue in report["issues"])


def test_datatable_values_become_workflow_arguments():
    root, report = emit('Browser("B").Page("P").WebEdit("User").Set DataTable("Username", dtLocalSheet)')

    assert report["arguments"] == {"in_data_Username": "String"}
    assert root.find(".//" + q("TypeInto", UI)).attrib["Text"] == "[in_data_Username]"


def test_unbound_datatable_column_blocks():
    root, report = emit('Browser("B").Page("P").WebEdit("User").Set DataTable("Missing", dtLocalSheet)')

    assert report["status"] == "blocked"
    assert any("data:Missing" in issue["message"] for issue in report["issues"])


def test_click_coordinates_do_not_silently_change_the_click():
    root, report = emit('Browser("B").Page("P").WebButton("Go").Click 14, 11')

    # The click is emitted, and the report says the offset is not reproduced.
    assert root.find(".//" + q("Click", UI)) is not None
    assert report["status"] == "mapped_unverified"
    assert "(14, 11) is not reproduced" in report["trace"][0]["note"]
