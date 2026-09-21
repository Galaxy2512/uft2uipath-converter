# Tests the UFT Object Repository reader (uft/object_repository.py) and the
# Berkeley DB B-tree reader beneath it: object hierarchy, properties and
# identification sets, case-insensitive lookup, and isolated handling of
# checkpoints, missing streams and corrupt files.
import pytest

from bdb_fixtures import VT_BOOL, VT_BSTR, VT_I4, btree_file, object_repository, object_stream
from uft2uipath.uft.berkeley_db import BerkeleyDbError, is_berkeley_btree, read_databases
from uft2uipath.uft.object_repository import ObjectRepositoryError, read_object_repository

WEB_TREE = [("Browser", [("B", "1", "Browser", [
    ("Page", [("Welcome", "2", "Page", [
        ("WebEdit", [("userName", "3", "WebEdit", []), ("password", "4", "WebEdit", [])]),
        ("Image", [("Sign-In", "5", "Image", [])]),
    ])]),
])])]


def web_repository(**overrides):
    objects = {
        "1": object_stream([("micclass", VT_BSTR, "Browser")], ["micclass"]),
        "2": object_stream([("title", VT_BSTR, "Welcome: Mercury Tours"), ("micclass", VT_BSTR, "Page")],
                           ["micclass"]),
        "3": object_stream([("micclass", VT_BSTR, "WebEdit"), ("type", VT_BSTR, "text"),
                            ("name", VT_BSTR, "userName"), ("html tag", VT_BSTR, "INPUT"),
                            ("visible", VT_BOOL, True), ("source_index", VT_I4, 204)],
                           ["micclass", "type", "name", "html tag"], ["visible"]),
        "4": object_stream([("micclass", VT_BSTR, "WebEdit"), ("name", VT_BSTR, "password")],
                           ["micclass", "name"]),
        "5": object_stream([("micclass", VT_BSTR, "Image"), ("alt", VT_BSTR, "Sign-In")],
                           ["micclass", "alt"]),
    }
    objects.update(overrides)
    return object_repository(WEB_TREE, objects)


def test_reads_hierarchy_properties_and_identification():
    repository = read_object_repository(web_repository())

    assert [(o.id, o.test_object_class, o.logical_name) for o in repository.objects] == [
        ("1", "Browser", "B"), ("2", "Page", "Welcome"),
        ("3", "WebEdit", "userName"), ("4", "WebEdit", "password"), ("5", "Image", "Sign-In"),
    ]
    edit = repository.find([("Browser", "B"), ("Page", "Welcome"), ("WebEdit", "userName")])
    assert edit.mandatory == ["micclass", "type", "name", "html tag"]
    assert edit.assistive == ["visible"]
    assert edit.value("NAME") == "userName" and edit.value("source_index") == 204
    assert edit.issue is None


def test_lookup_is_case_insensitive_and_path_aware():
    repository = read_object_repository(web_repository())

    assert repository.find([("browser", "b"), ("PAGE", "welcome"), ("webedit", "PASSWORD")]).id == "4"
    assert repository.find([("Browser", "B"), ("WebEdit", "userName")]) is None


def test_checkpoints_and_missing_streams_are_marked_not_dropped():
    tree = [("CheckPoint", [("Frankfurt", "9", "VerifyObj", [])]),
            ("Browser", [("B", "7", "Browser", [])])]
    repository = read_object_repository(object_repository(tree, {"9": object_stream([])}))

    assert [(o.id, o.issue) for o in repository.objects] == [
        ("9", "checkpoint"), ("7", "missing_object_stream"),
    ]


def test_unreadable_object_stream_is_isolated_to_that_object():
    repository = read_object_repository(web_repository(**{"3": b"\xff\x01" + b"\x00" * 60}))

    objects = {o.id: o for o in repository.objects}
    assert objects["3"].issue.startswith("unreadable_object")
    assert objects["4"].issue is None


def test_rejects_files_that_are_not_object_repositories():
    assert not is_berkeley_btree(b"nope")
    with pytest.raises(ObjectRepositoryError):
        read_object_repository(b"nope")
    with pytest.raises(ObjectRepositoryError, match="index stream"):
        read_object_repository(btree_file({"A": {b"x": b"y"}}))


def test_berkeley_reader_returns_records_including_overflow_values():
    payload = bytes(range(256)) * 8
    data = btree_file({"first": {b"small": b"value", b"large": payload}, "second": {b"k": b"v"}})

    databases = read_databases(data)

    assert databases["first"] == {b"small": b"value", b"large": payload}
    assert databases["second"] == {b"k": b"v"}


def test_berkeley_reader_reports_corrupt_files():
    data = bytearray(btree_file({"a": {b"k": b"v"}}))
    data[20:24] = (99).to_bytes(4, "little")
    with pytest.raises(BerkeleyDbError, match="page size"):
        read_databases(bytes(data))
