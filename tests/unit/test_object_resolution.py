from bdb_fixtures import VT_BSTR, object_repository, object_stream
from uft2uipath.alm.resources import ResourceIndex, parse_reference
from uft2uipath.uft.object_references import extract_references
from uft2uipath.uft.object_repository import read_object_repository
from uft2uipath.uft.object_resolution import resolve_objects


def repository(logical_name, properties):
    tree = [("Browser", [("B", "1", "Browser", [
        ("Page", [("P", "2", "Page", [("WebEdit", [(logical_name, "3", "WebEdit", [])])])])])])]
    return read_object_repository(object_repository(tree, {
        "1": object_stream([("micclass", VT_BSTR, "Browser")], ["micclass"]),
        "2": object_stream([("micclass", VT_BSTR, "Page"), ("title", VT_BSTR, "Welcome")], ["micclass"]),
        "3": object_stream([("micclass", VT_BSTR, "WebEdit")] + properties,
                           ["micclass"] + [name for name, _, _ in properties]),
    }))


def statuses(objects):
    return {tuple(step["name"] or "" for step in entry["path"]): entry["status"] for entry in objects}


def test_object_references_ignore_methods_comments_and_member_calls():
    text = "\n".join([
        'Browser("B").Page("P").WebEdit("userName").Set DataTable("User", dtLocalSheet) @@ hightlight id_;_x',
        'OptionalStep.Browser("B").Dialog("IE").WinButton("&Yes").Click',
        'Reporter.ReportEvent micFail, Environment.Value("TestName"), "x"',
        'Setting.WebPackage("ReplayType") = 1',
        "' Browser(\"Commented\").Page(\"P\").Click",
        'v = Browser("B").Page("P").WebList("fromPort").GetROProperty("value")',
    ])

    references = extract_references(text)

    assert [[(s.test_object_class, s.name) for s in r.path] for r in references] == [
        [("Browser", "B"), ("Page", "P"), ("WebEdit", "userName")],
        [("Browser", "B"), ("Dialog", "IE"), ("WinButton", "&Yes")],
        [("Browser", "B"), ("Page", "P"), ("WebList", "fromPort")],
    ]


def test_repeated_references_are_grouped_with_their_line_numbers():
    text = ('Browser("B").Page("P").WebEdit("userName").Set "a"\n'
            'Browser("B").Page("P").WebEdit("userName").Set "b"')

    objects = resolve_objects(text, [("local", repository("userName", [("name", VT_BSTR, "userName")]))])

    assert len(objects) == 1
    assert objects[0]["lines"] == [1, 2]
    assert objects[0]["status"] == "resolved"
    assert objects[0]["uft"] == {"browser": "B", "page": "P",
                                 "object_type": "WebEdit", "logical_name": "userName"}


def test_shared_repository_is_searched_after_the_local_one():
    local = repository("password", [("name", VT_BSTR, "password")])
    shared = repository("userName", [("name", VT_BSTR, "userName")])
    text = ('Browser("B").Page("P").WebEdit("userName").Set "a"\n'
            'Browser("B").Page("P").WebEdit("password").Set "b"')

    objects = resolve_objects(text, [("local.bdb", local), ("shared.tsr", shared)])

    sources = {entry["path"][-1]["name"]: entry.get("repository") for entry in objects}
    assert sources == {"userName": "shared.tsr", "password": "local.bdb"}


def test_unknown_objects_checkpoints_and_dynamic_names_are_classified():
    text = "\n".join([
        'Browser("B").Page("P").WebEdit("missing").Set "a"',
        'Browser("B").Page("P").Check CheckPoint("Frankfurt")',
        'Browser("B").Page("P").Link(linkName).Click',
    ])

    objects = resolve_objects(text, [("local", repository("userName", [("name", VT_BSTR, "userName")]))])

    assert statuses(objects) == {
        ("B", "P", "missing"): "not_in_repository",
        ("B", "P"): "resolved",
        ("Frankfurt",): "checkpoint",
        ("",): "dynamic",
    }
    assert all(entry["candidate"] is None for entry in objects if entry["status"] != "resolved")


def test_without_any_repository_nothing_is_invented():
    objects = resolve_objects('Browser("B").Page("P").WebEdit("userName").Set "a"', [])

    assert objects[0]["status"] == "no_repository"
    assert objects[0]["candidate"] is None


def test_descriptive_programming_is_resolved_from_the_script_itself():
    text = 'Browser("title:=Mercury").Page("title:=Welcome").WebEdit("name:=userName", "html tag:=INPUT").Set "a"'

    objects = resolve_objects(text, [])

    assert objects[0]["status"] == "descriptive"
    assert objects[0]["candidate"]["selector"] == (
        '<html title="Welcome" /><webctrl name="userName" tag="INPUT" />'
    )


def test_resource_references_resolve_through_folder_and_file_name():
    folders = [{"RFO_ID": 1, "RFO_NAME": "Resources", "RFO_PARENT_ID": 0},
               {"RFO_ID": 2, "RFO_NAME": "BPT Resources", "RFO_PARENT_ID": 1},
               {"RFO_ID": 3, "RFO_NAME": "Object Repositories", "RFO_PARENT_ID": 2},
               {"RFO_ID": 4, "RFO_NAME": "Object Repositories", "RFO_PARENT_ID": 1}]
    resources = [{"RSC_ID": 10, "RSC_NAME": "WinFlight.tsr", "RSC_FILE_NAME": "WinFlight.tsr",
                  "RSC_PARENT_ID": 3},
                 {"RSC_ID": 11, "RSC_NAME": "Other.tsr", "RSC_FILE_NAME": "WinFlight.tsr",
                  "RSC_PARENT_ID": 4},
                 {"RSC_ID": 12, "RSC_NAME": "Flight_Application.tsr", "RSC_FILE_NAME": "adi.tsr",
                  "RSC_PARENT_ID": 3}]
    index = ResourceIndex(resources, folders)

    reference = "[QC-RESOURCE];;Resources\\BPT Resources\\Object Repositories;;\\WinFlight.tsr"
    assert parse_reference(reference) == ("Resources\\BPT Resources\\Object Repositories", "WinFlight.tsr")
    assert index.find(*parse_reference(reference)) == "resources\\10\\WinFlight.tsr"
    assert index.find("Resources\\Object Repositories", "WinFlight.tsr") == "resources\\11\\WinFlight.tsr"
    # The logical resource name resolves to the stored file name.
    assert index.find("Resources\\BPT Resources\\Object Repositories",
                      "Flight_Application.tsr") == "resources\\12\\adi.tsr"
    assert index.find("Resources\\Missing", "WinFlight.tsr") is None
    assert parse_reference("C:\\local\\WinFlight.tsr") is None
