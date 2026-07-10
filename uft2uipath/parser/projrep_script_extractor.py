"""
ProjRep Script Extractor

Responsibility
--------------
Extracts readable UFT/VBScript source code from one QCP ProjRep file.

Background
----------
The extracted QCP archive contains files under:

    ProjRep/000/000/...

Some of these files contain recognizable UFT code such as:

    Browser("...")
    Page("...")
    WebEdit("...").Set
    WebButton("...").Click
    Reporter.ReportEvent

The files can mix:

- binary metadata
- UTF-8 text
- UTF-16 little-endian text
- serialized UFT resources

This module does not yet resolve which Business Component owns the file.
Its only responsibility is to extract the most likely script text.

Output
------
ProjRepScript containing:

- source file
- candidate object ID
- detected encoding
- extracted script text
- signatures found in the script
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass
class ProjRepScript:
    """
    Represents script content extracted from one ProjRep file.
    """

    source_file: Path
    object_id: int | None
    encoding: str
    text: str
    signatures: list[str] = field(default_factory=list)


class ProjRepScriptExtractor:
    """
    Extracts the most likely UFT/VBScript source from a ProjRep file.
    """

    UFT_SIGNATURES = (
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

    def extract(
        self,
        file: str | Path,
    ) -> ProjRepScript | None:
        """
        Extract UFT/VBScript text from one ProjRep file.

        Parameters
        ----------
        file:
            Path to a physical ProjRep file.

        Returns
        -------
        ProjRepScript | None:
            Extracted script, or None when no UFT signature is found.
        """

        path = Path(file)

        if not path.exists():
            raise FileNotFoundError(path)

        if not path.is_file():
            raise IsADirectoryError(path)

        data = path.read_bytes()

        # --------------------------------------------------------------
        # STEP 1
        # Decode the same binary content using the encodings observed
        # during reverse engineering.
        # --------------------------------------------------------------
        candidates = [
            ("utf-8", data.decode("utf-8", errors="ignore")),
            ("utf-16-le", data.decode("utf-16-le", errors="ignore")),
            ("latin1", data.decode("latin1", errors="ignore")),
        ]

        best_encoding: str | None = None
        best_text: str | None = None
        best_signatures: list[str] = []
        best_score = 0

        # --------------------------------------------------------------
        # STEP 2
        # Score every decoded version.
        #
        # The candidate containing the largest number of recognizable
        # UFT signatures is considered the most likely script encoding.
        # --------------------------------------------------------------
        for encoding, decoded_text in candidates:
            signatures = self._find_signatures(decoded_text)
            score = len(signatures)

            if score > best_score:
                best_score = score
                best_encoding = encoding
                best_text = decoded_text
                best_signatures = signatures

        if best_text is None or best_encoding is None:
            return None

        # --------------------------------------------------------------
        # STEP 3
        # Remove binary noise and retain the readable script region.
        # --------------------------------------------------------------
        cleaned_text = self._extract_script_region(best_text)

        if not cleaned_text:
            return None

        return ProjRepScript(
            source_file=path,
            object_id=self._extract_object_id(path),
            encoding=best_encoding,
            text=cleaned_text,
            signatures=best_signatures,
        )

    def _find_signatures(self, text: str) -> list[str]:
        """
        Return all known UFT signatures found in decoded text.
        """

        return [
            signature
            for signature in self.UFT_SIGNATURES
            if signature in text
        ]

    def _extract_script_region(self, text: str) -> str | None:
        """
        Extract the readable region around UFT script signatures.

        NOTE
        ----
        At this stage we cannot yet reliably decode every serialized
        ProjRep structure. We therefore retain the readable region from
        the first to the last recognizable UFT signature, with some
        surrounding context.
        """

        positions: list[int] = []

        for signature in self.UFT_SIGNATURES:
            start = 0

            while True:
                position = text.find(signature, start)

                if position < 0:
                    break

                positions.append(position)
                start = position + len(signature)

        if not positions:
            return None

        first_position = min(positions)
        last_position = max(positions)

        # Keep context before and after the recognized script.
        start = max(0, first_position - 300)
        end = min(len(text), last_position + 2000)

        region = text[start:end]

        # --------------------------------------------------------------
        # STEP 4
        # Replace binary control characters with line breaks or spaces.
        # Preserve tabs and normal line endings where possible.
        # --------------------------------------------------------------
        region = region.replace("\x00", "\n")

        region = re.sub(
            r"[^\x09\x0A\x0D\x20-\x7E]",
            " ",
            region,
        )

        # Remove excessive spaces created from binary metadata.
        region = re.sub(r"[ ]{2,}", " ", region)

        # Remove excessive blank lines.
        region = re.sub(r"\n{3,}", "\n\n", region)

        return region.strip() or None

    def _extract_object_id(self, path: Path) -> int | None:
        """
        Extract the candidate numeric ProjRep object identifier.

        Example:

            ProjRep/000/000/000/001/803

        becomes:

            1803

        The semantic meaning of this ID still needs to be proven.
        """

        numeric_parts = [
            part
            for part in path.parts
            if part.isdigit()
        ]

        if not numeric_parts:
            return None

        combined = "".join(numeric_parts).lstrip("0")

        if not combined:
            return 0

        try:
            return int(combined)
        except ValueError:
            return None