"""
ALM Table Reader

Responsibility
--------------
Combines ALM schema information with PTD table data.

Input
-----
- AlmSchema from db_xmlmap.xml
- One .ptd table file

Output
------
A lightweight AlmTableData object containing:
- table name
- column names
- extracted raw values

Important
---------
This is still an intermediate step.

We do not yet fully decode PTD records into rows.
The goal is to centralize table-level reading before building
the full ALM database reader.
"""

from dataclasses import dataclass, field
from pathlib import Path

from uft2uipath.alm.ptd_reader import PtdReader
from uft2uipath.alm.schema import AlmSchema


@dataclass
class AlmTableData:
    """
    Represents raw data extracted from one ALM table.
    """

    name: str
    columns: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    source_file: Path | None = None


class AlmTableReader:
    """
    Reads one ALM table by combining schema metadata and PTD content.
    """

    def __init__(self, ptd_reader: PtdReader | None = None):
        self.ptd_reader = ptd_reader or PtdReader()

    def read_table(
        self,
        schema: AlmSchema,
        table_name: str,
        ptd_file: str | Path,
    ) -> AlmTableData:
        """
        Read one ALM table.

        Parameters
        ----------
        schema:
            Parsed ALM schema.

        table_name:
            Logical ALM table name, for example TEST or COMPONENT.

        ptd_file:
            Path to the matching .ptd file.

        Returns
        -------
        AlmTableData:
            Table metadata and extracted values.
        """

        table = schema.get_table(table_name)

        if table is None:
            raise KeyError(f"Table not found in schema: {table_name}")

        path = Path(ptd_file)

        values = self.ptd_reader.read_strings(path)

        return AlmTableData(
            name=table.name,
            columns=table.column_names(),
            values=values,
            source_file=path,
        )