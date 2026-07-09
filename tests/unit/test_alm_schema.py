from uft2uipath.alm.schema import AlmSchemaReader


def test_schema_reader_reads_tables_and_columns(tmp_path):
    xml = tmp_path / "db_xmlmap.xml"

    xml.write_text(
        """
        <Scheme>
            <t name="TEST">
                <c name="TS_TEST_ID" type="int" null="N" />
                <c name="TS_NAME" type="varchar" size="255" />
            </t>
        </Scheme>
        """,
        encoding="utf-8",
    )

    schema = AlmSchemaReader().read(xml)

    test_table = schema.get_table("TEST")

    assert test_table is not None
    assert test_table.name == "TEST"
    assert test_table.column_names() == ["TS_TEST_ID", "TS_NAME"]
    assert test_table.columns[0].nullable is False
    assert test_table.columns[1].size == 255