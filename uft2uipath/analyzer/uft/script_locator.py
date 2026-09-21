"""
UFT Script Locator

Responsibility
--------------
Searches an extracted QCP project for byte patterns that look like
UFT/VBScript automation code.

Why this exists
---------------
ALM COMPONENT fields CO_DATA and CO_STEPS_DATA are CLOB fields.

Depending on the QCP export format, their content may be:

- stored directly inside COMPONENT_*.ptd
- stored in another binary file
- encoded as UTF-8
- encoded as UTF-16 LE
- referenced through CO_PHYSICAL_PATH
- stored as a compressed or serialized object

This analyzer searches every extracted file for recognizable UFT
automation signatures before we implement the final CLOB decoder.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScriptMatch:
    """
    One discovered UFT script signature.
    """

    file: Path
    relative_path: str
    signature: str
    encoding: str
    offset: int


class UftScriptLocator:
    """
    Searches extracted QCP files for common UFT script patterns.
    """

    DEFAULT_SIGNATURES = (
        "Browser(",
        "Page(",
        "WebEdit(",
        "WebButton(",
        "WebElement(",
        ".Navigate",
        ".Click",
        ".Set",
        ".Exist",
        "Reporter.ReportEvent",
        "DataTable.",
        "Environment.",
    )

    def search(
        self,
        project_folder: str | Path,
        signatures: tuple[str, ...] | None = None,
    ) -> list[ScriptMatch]:
        """
        Search every file below the supplied project folder.

        Both common encodings are checked:

        - UTF-8 / ASCII
        - UTF-16 little-endian

        Parameters
        ----------
        project_folder:
            Root folder of the extracted QCP project.

        signatures:
            Optional custom signatures. If omitted, common UFT
            signatures are used.

        Returns
        -------
        list[ScriptMatch]:
            Every matching file, pattern, encoding and byte offset.
        """

        root = Path(project_folder)

        if not root.exists():
            raise FileNotFoundError(root)

        patterns = signatures or self.DEFAULT_SIGNATURES
        matches: list[ScriptMatch] = []

        # --------------------------------------------------------------
        # STEP 1
        # Scan every extracted file as raw bytes.
        # --------------------------------------------------------------
        for path in root.rglob("*"):
            if not path.is_file():
                continue

            try:
                data = path.read_bytes()
            except OSError:
                # A single unreadable file must not stop project analysis.
                continue

            # ----------------------------------------------------------
            # STEP 2
            # Search using common text encodings.
            # ----------------------------------------------------------
            for signature in patterns:
                encoded_patterns = (
                    ("utf-8", signature.encode("utf-8")),
                    ("utf-16-le", signature.encode("utf-16-le")),
                )

                for encoding, encoded_signature in encoded_patterns:
                    offset = data.find(encoded_signature)

                    if offset < 0:
                        continue

                    matches.append(
                        ScriptMatch(
                            file=path,
                            relative_path=str(path.relative_to(root)),
                            signature=signature,
                            encoding=encoding,
                            offset=offset,
                        )
                    )

        return matches