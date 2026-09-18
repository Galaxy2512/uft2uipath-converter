"""Decoded row access to every ALM table in an extracted QCP export."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from uft2uipath.alm.ptd_reader import PtdFormatError, PtdReader
from uft2uipath.alm.schema import AlmSchema, AlmSchemaReader


class AlmTables:
    def __init__(self, root: str | Path, reader: PtdReader | None = None):
        self.root = Path(root)
        schema_file = self.root / "db_xmlmap.xml"
        if not schema_file.is_file():
            raise FileNotFoundError(f"Not an extracted ALM export (missing db_xmlmap.xml): {self.root}")
        self.schema: AlmSchema = AlmSchemaReader().read(schema_file)
        self._reader = reader or PtdReader()
        self._cache: dict[str, list[dict[str, Any]]] = {}
        # Large tables may be split into NAME_!000001.ptd, NAME_!000002.ptd, ...
        self._files: dict[str, list[Path]] = defaultdict(list)
        for path in sorted((self.root / "tables").glob("*_!*.ptd")):
            self._files[path.name.split("_!", 1)[0].upper()].append(path)

    def names(self) -> list[str]:
        return sorted(self._files)

    def has(self, name: str) -> bool:
        return name.upper() in self._files

    def rows(self, name: str) -> list[dict[str, Any]]:
        key = name.upper()
        if key not in self._cache:
            table = self.schema.get_table(key)
            if table is None:
                raise PtdFormatError(f"Table {key} has data files but no schema definition.")
            rows = []
            for path in self._files.get(key, []):
                rows.extend(self._reader.read_rows(path, table.columns))
            self._cache[key] = rows
        return self._cache[key]
