from uft2uipath.alm.schema import AlmSchemaReader
from uft2uipath.alm.table_reader import AlmTableReader


def test_table_reader_combines_schema_and_ptd_values(tmp_path):
    schema_file = tmp_path / "db_xmlmap.xml"
    schema_file.write_text(
        """
        <Scheme>
            <t name="TEST">
                <c name="TS_TEST_ID" type="int" />
                <c name="TS_NAME" type="varchar" />
            </t>
        </Scheme>
        """,
        encoding="utf-8",
    )

    ptd_file = tmp_path / "TEST_!000001.ptd"
    ptd_file.write_bytes(b"\x00\x01Simply_BPT_TestCase\x00BUSINESS-PROCESS")

    schema = AlmSchemaReader().read(schema_file)
    table_data = AlmTableReader().read_table(schema, "TEST", ptd_file)

    assert table_data.name == "TEST"
    assert table_data.columns == ["TS_TEST_ID", "TS_NAME"]
    assert "Simply_BPT_TestCase" in table_data.values
    assert "BUSINESS-PROCESS" in table_data.values
