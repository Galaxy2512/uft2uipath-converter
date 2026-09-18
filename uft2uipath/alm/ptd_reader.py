"""
ALM PTD Reader

Responsibility
--------------
Reads HP ALM/QC .ptd table export files.

Important
---------
PTD files are not simple CSV files.

They appear to be binary table dumps containing:
- numeric values
- null markers
- length-prefixed strings
- binary metadata

Row layout (verified on ALM 19 exports): rows are stored back to back with
no header, each column in schema order.

- timestamp: 8-byte big-endian epoch milliseconds, all 0xFF bytes = NULL
- every other type: 1 flag byte (0 = value, 1 = NULL), then
  - int/short: 4-byte big-endian signed integer
  - varchar/clob/blob: 4-byte big-endian length, then that many bytes
"""

import datetime
import struct
from pathlib import Path
from typing import Any

from uft2uipath.alm.schema import AlmColumn

_NULL_TIMESTAMP = b"\xff" * 8
_INTEGER_TYPES = {"int", "short"}
_TEXT_TYPES = {"varchar", "clob"}


class PtdFormatError(ValueError):
    pass


class PtdReader:
    """
    Reads values from ALM PTD files.
    """

    def read_rows(
        self,
        file: str | Path,
        columns: list[AlmColumn],
    ) -> list[dict[str, Any]]:
        path = Path(file)
        data = path.read_bytes()
        if not columns:
            raise PtdFormatError(f"{path.name}: schema defines no columns.")
        rows = []
        position = 0
        while position < len(data):
            row = {}
            for column in columns:
                try:
                    row[column.name], position = self._read_value(data, position, column)
                except (struct.error, IndexError):
                    raise PtdFormatError(
                        f"{path.name}: row {len(rows)} truncated at column {column.name}."
                    ) from None
            rows.append(row)
        return rows

    def _read_value(self, data: bytes, position: int, column: AlmColumn) -> tuple[Any, int]:
        datatype = (column.datatype or "").lower()
        if datatype == "timestamp":
            raw = data[position:position + 8]
            if len(raw) != 8:
                raise IndexError
            if raw == _NULL_TIMESTAMP:
                return None, position + 8
            milliseconds = struct.unpack(">q", raw)[0]
            moment = datetime.datetime.fromtimestamp(milliseconds / 1000, datetime.timezone.utc)
            return moment.isoformat(), position + 8

        flag = data[position]
        position += 1
        if flag == 1:
            return None, position
        if flag != 0:
            raise PtdFormatError(
                f"Invalid null flag {flag} at offset {position - 1} (column {column.name})."
            )

        if datatype in _INTEGER_TYPES:
            return struct.unpack(">i", data[position:position + 4])[0], position + 4

        length = struct.unpack(">i", data[position:position + 4])[0]
        position += 4
        raw = data[position:position + length]
        if length < 0 or len(raw) != length:
            raise IndexError
        position += length
        if datatype in _TEXT_TYPES:
            return raw.decode("utf-8"), position
        if datatype == "blob":
            return raw.hex(), position
        raise PtdFormatError(f"Unsupported column type {column.datatype!r} ({column.name}).")

    def read_strings(
        self,
        file: str | Path,
        min_length: int = 2,
    ) -> list[str]:
        """
        Extract printable strings from a PTD file.

        Parameters
        ----------
        file:
            Path to .ptd file.

        min_length:
            Ignore strings shorter than this value.

        Returns
        -------
        list[str]:
            Extracted printable strings.
        """

        path = Path(file)

        if not path.exists():
            raise FileNotFoundError(path)

        data = path.read_bytes()
        values: list[str] = []
        current = bytearray()

        for byte in data:
            if self._is_printable(byte):
                current.append(byte)
            else:
                self._flush(values, current, min_length)
                current.clear()

        self._flush(values, current, min_length)

        return values

    def _is_printable(self, byte: int) -> bool:
        """
        Return True if byte looks like printable text.

        We intentionally keep this conservative for now.
        """
        return 32 <= byte <= 126

    def _flush(
        self,
        values: list[str],
        buffer: bytearray,
        min_length: int,
    ) -> None:
        """
        Convert current buffer to text and append it to values.
        """

        if len(buffer) < min_length:
            return

        values.append(buffer.decode("latin1"))