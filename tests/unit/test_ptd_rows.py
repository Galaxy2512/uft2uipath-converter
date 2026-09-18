import pytest

from ptd_fixtures import NULL, TEST_COLUMNS, encode_rows, write_export
from uft2uipath.alm.ptd_reader import PtdFormatError, PtdReader
from uft2uipath.alm.schema import AlmColumn
from uft2uipath.alm.tables import AlmTables


def columns(spec):
    return [AlmColumn(name=name, datatype=datatype) for name, datatype in spec]


def test_decodes_every_supported_type_and_nulls(tmp_path):
    spec = TEST_COLUMNS + [("TS_STEPS", "short"), ("TS_DATA", "blob")]
    ptd = tmp_path / "TEST_!000001.ptd"
    ptd.write_bytes(encode_rows(spec, [
        {"TS_TEST_ID": 58, "TS_NAME": "Book Flight", "TS_TYPE": "MANUAL",
         "TS_CREATION_DATE": 1421877600000, "TS_DESCRIPTION": "Zürich <b>ok</b>",
         "TS_STEPS": -3, "TS_DATA": b"\x00\xff"},
        {"TS_TEST_ID": 59, "TS_NAME": "", "TS_TYPE": NULL, "TS_CREATION_DATE": NULL,
         "TS_DESCRIPTION": NULL, "TS_STEPS": NULL, "TS_DATA": NULL},
    ]))

    rows = PtdReader().read_rows(ptd, columns(spec))

    assert rows == [
        {"TS_TEST_ID": 58, "TS_NAME": "Book Flight", "TS_TYPE": "MANUAL",
         "TS_CREATION_DATE": "2015-01-21T22:00:00+00:00", "TS_DESCRIPTION": "Zürich <b>ok</b>",
         "TS_STEPS": -3, "TS_DATA": "00ff"},
        {"TS_TEST_ID": 59, "TS_NAME": "", "TS_TYPE": None, "TS_CREATION_DATE": None,
         "TS_DESCRIPTION": None, "TS_STEPS": None, "TS_DATA": None},
    ]


def test_empty_file_is_an_empty_table(tmp_path):
    ptd = tmp_path / "EMPTY_!000001.ptd"
    ptd.write_bytes(b"")
    assert PtdReader().read_rows(ptd, columns(TEST_COLUMNS)) == []


def test_truncated_row_is_reported(tmp_path):
    ptd = tmp_path / "TEST_!000001.ptd"
    data = encode_rows(TEST_COLUMNS, [{"TS_TEST_ID": 1, "TS_NAME": "Login"}])
    ptd.write_bytes(data[:-3])
    with pytest.raises(PtdFormatError, match="truncated"):
        PtdReader().read_rows(ptd, columns(TEST_COLUMNS))


def test_schema_mismatch_is_reported_not_guessed(tmp_path):
    ptd = tmp_path / "TEST_!000001.ptd"
    ptd.write_bytes(b"\x07\x00\x00\x00\x01")
    with pytest.raises(PtdFormatError, match="null flag 7"):
        PtdReader().read_rows(ptd, columns([("TS_TEST_ID", "int")]))


def test_tables_concatenate_split_files_and_allow_missing_data(tmp_path):
    spec = [("CO_ID", "int"), ("CO_NAME", "varchar")]
    root = write_export(tmp_path / "export", {
        "COMPONENT": (spec, [{"CO_ID": 1, "CO_NAME": "Login"}]),
        "COMPONENT_STEP": ([("CS_STEP_ID", "int")], []),
    })
    (root / "tables" / "COMPONENT_!000002.ptd").write_bytes(
        encode_rows(spec, [{"CO_ID": 2, "CO_NAME": "Logout"}])
    )
    (root / "tables" / "COMPONENT_STEP_!000001.ptd").unlink()

    tables = AlmTables(root)

    assert tables.names() == ["COMPONENT"]
    assert [row["CO_ID"] for row in tables.rows("component")] == [1, 2]
    assert tables.rows("COMPONENT_STEP") == []


def test_tables_require_an_alm_export(tmp_path):
    with pytest.raises(FileNotFoundError, match="db_xmlmap.xml"):
        AlmTables(tmp_path)
