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

This reader starts with a safe first step:
extracting printable string values from PTD files.

It does NOT yet fully decode records.

This module will gradually evolve into the production PTD parser.
"""

from pathlib import Path


class PtdReader:
    """
    Reads values from ALM PTD files.

    Current capability:
    - extract printable strings in file order

    Future capability:
    - decode complete rows
    - map row values to schema columns
    - preserve numeric and null values
    """

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