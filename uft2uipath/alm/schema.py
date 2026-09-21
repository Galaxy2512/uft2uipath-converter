"""
ALM Schema Reader

Responsibility
--------------
Reads HP ALM/QC database schema information from db_xmlmap.xml.

Why this exists
---------------
A QCP archive does not contain simple Test.xml / Component.xml files.
Instead, it contains:

- db_xmlmap.xml  -> database schema
- tables/*.ptd   -> database table data

This module reads the schema part only.

It does NOT read PTD data.
It does NOT create UiPath files.
It only answers questions like:

- Which tables exist?
- Which columns belong to a table?
- What are the column types?

This is the foundation for the ALM database reader.
"""

from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass
class AlmColumn:
    """
    Represents one ALM database column.
    """

    name: str
    datatype: str | None = None
    size: int | None = None
    nullable: bool = True
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class AlmTable:
    """
    Represents one ALM database table.
    """

    name: str
    columns: list[AlmColumn] = field(default_factory=list)

    def column_names(self) -> list[str]:
        """
        Return column names in their original ALM order.
        """
        return [column.name for column in self.columns]


@dataclass
class AlmSchema:
    """
    Represents the parsed ALM database schema.
    """

    tables: dict[str, AlmTable] = field(default_factory=dict)

    def get_table(self, name: str) -> AlmTable | None:
        """
        Find a table by name, case-insensitive.
        """
        return self.tables.get(name.upper())


class AlmSchemaReader:
    """
    Reads db_xmlmap.xml and builds an AlmSchema object.
    """

    def read(self, xml_file: str | Path) -> AlmSchema:
        """
        Parse db_xmlmap.xml.

        Parameters
        ----------
        xml_file:
            Path to db_xmlmap.xml.

        Returns
        -------
        AlmSchema
            Parsed schema with tables and columns.
        """

        path = Path(xml_file)

        if not path.exists():
            raise FileNotFoundError(path)

        root = ET.parse(path).getroot()
        schema = AlmSchema()

        # In db_xmlmap.xml, actual table definitions are stored in <t> nodes.
        # Example:
        # <t name="TEST">
        #     <c name="TS_TEST_ID" type="int" />
        #     <c name="TS_NAME" type="varchar" size="255" />
        # </t>
        for table_node in root.iter():
            if table_node.tag.lower() != "t":
                continue

            table_name = table_node.attrib.get("name")

            if not table_name:
                continue

            table = AlmTable(name=table_name)

            for child in table_node:
                if child.tag.lower() != "c":
                    continue

                column_name = child.attrib.get("name")

                if not column_name:
                    continue

                table.columns.append(
                    AlmColumn(
                        name=column_name,
                        datatype=child.attrib.get("type"),
                        size=self._parse_int(child.attrib.get("size")),
                        nullable=child.attrib.get("null", "Y") != "N",
                        raw=dict(child.attrib),
                    )
                )

            schema.tables[table_name.upper()] = table

        return schema

    def _parse_int(self, value: str | None) -> int | None:
        """
        Safely convert XML numeric attributes to int.
        """
        if value is None:
            return None

        try:
            return int(value)
        except ValueError:
            return None