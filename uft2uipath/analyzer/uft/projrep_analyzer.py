"""
ProjRep Evidence Analyzer

Responsibility
--------------
Inspects files stored under the extracted QCP ProjRep directory.

The exact meaning of "ProjRep" has not yet been confirmed.
We therefore treat it only as an internal QCP storage directory.

This analyzer collects evidence that may help us connect:

ALM COMPONENT record
    ->
ProjRep file
    ->
UFT/VBScript automation source

It searches for:

- UFT script signatures
- component names
- readable text around script locations
- numeric ProjRep object identifiers

Important
---------
This module does not create final mappings yet.

A mapping is accepted only after we have reliable evidence, such as:

- an explicit component name inside a ProjRep file
- a COMPONENT table path/reference pointing to that file
- a matching resource or internal object ID
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass
class ProjRepEvidence:
    """
    Evidence collected from one ProjRep file.
    """

    file: Path
    relative_path: str
    object_id: int | None

    # UFT keywords found in this file.
    signatures: list[str] = field(default_factory=list)

    # Known Business Component names found directly inside this file.
    component_names: list[str] = field(default_factory=list)

    # Readable text extracted around the first relevant UFT signature.
    text_preview: str | None = None

    # Encoding that produced the preview.
    preview_encoding: str | None = None


class ProjRepAnalyzer:
    """
    Inspects ProjRep files and collects mapping evidence.
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

    def analyze(
        self,
        projrep_folder: str | Path,
        component_names: list[str] | None = None,
        preview_characters: int = 1200,
    ) -> list[ProjRepEvidence]:
        """
        Analyze every file under a ProjRep directory.

        Parameters
        ----------
        projrep_folder:
            Path to extracted QCP ProjRep directory.

        component_names:
            Optional list of known ALM Business Component names.

            Example:
            - BrowserStart_QWERTZ
            - BrowserNavigate_QWERTZ
            - CheckWebsite_QWERTZ

        preview_characters:
            Maximum number of decoded characters retained in a preview.

        Returns
        -------
        list[ProjRepEvidence]:
            Only files containing a UFT signature or component name.
        """

        root = Path(projrep_folder)

        if not root.exists():
            raise FileNotFoundError(root)

        if not root.is_dir():
            raise NotADirectoryError(root)

        known_components = component_names or []
        results: list[ProjRepEvidence] = []

        # --------------------------------------------------------------
        # STEP 1
        # Scan every physical file stored under ProjRep.
        # --------------------------------------------------------------
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue

            try:
                data = path.read_bytes()
            except OSError:
                # One unreadable object must not stop the full analysis.
                continue

            evidence = self._analyze_file(
                root=root,
                path=path,
                data=data,
                component_names=known_components,
                preview_characters=preview_characters,
            )

            # Keep only files containing relevant evidence.
            if evidence.signatures or evidence.component_names:
                results.append(evidence)

        return results

    def _analyze_file(
        self,
        root: Path,
        path: Path,
        data: bytes,
        component_names: list[str],
        preview_characters: int,
    ) -> ProjRepEvidence:
        """
        Analyze one ProjRep file using common text encodings.
        """

        evidence = ProjRepEvidence(
            file=path,
            relative_path=str(path.relative_to(root)),
            object_id=self._extract_object_id(path),
        )

        decoded_versions = self._decode_candidates(data)

        # --------------------------------------------------------------
        # STEP 2
        # Search decoded content for UFT signatures.
        # --------------------------------------------------------------
        for encoding, text in decoded_versions:
            for signature in self.DEFAULT_SIGNATURES:
                if signature in text and signature not in evidence.signatures:
                    evidence.signatures.append(signature)

            # ----------------------------------------------------------
            # STEP 3
            # Search for complete component names.
            # ----------------------------------------------------------
            for component_name in component_names:
                if (
                    component_name in text
                    and component_name not in evidence.component_names
                ):
                    evidence.component_names.append(component_name)

            # ----------------------------------------------------------
            # STEP 4
            # Retain a readable preview around the first UFT signature.
            # ----------------------------------------------------------
            if evidence.text_preview is None:
                preview = self._create_preview(
                    text=text,
                    preview_characters=preview_characters,
                )

                if preview:
                    evidence.text_preview = preview
                    evidence.preview_encoding = encoding

        return evidence

    def _decode_candidates(self, data: bytes) -> list[tuple[str, str]]:
        """
        Decode raw ProjRep bytes using likely text encodings.

        Invalid byte sequences are ignored because these files can mix
        binary metadata and text content.
        """

        candidates: list[tuple[str, str]] = []

        for encoding in ("utf-8", "utf-16-le", "latin1"):
            text = data.decode(encoding, errors="ignore")
            candidates.append((encoding, text))

        return candidates

    def _create_preview(
        self,
        text: str,
        preview_characters: int,
    ) -> str | None:
        """
        Return normalized text around the first UFT signature.
        """

        positions = [
            text.find(signature)
            for signature in self.DEFAULT_SIGNATURES
            if text.find(signature) >= 0
        ]

        if not positions:
            return None

        first_position = min(positions)

        # Include some text before the match because it may contain:
        # - a component name
        # - metadata
        # - a function or action header
        start = max(0, first_position - 250)
        end = min(len(text), first_position + preview_characters)

        preview = text[start:end]

        # Replace control characters with spaces, but keep line breaks.
        preview = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", " ", preview)

        # Reduce long runs of spaces created by binary metadata.
        preview = re.sub(r"[ ]{2,}", " ", preview)

        return preview.strip() or None

    def _extract_object_id(self, path: Path) -> int | None:
        """
        Extract the numeric identifier represented by the ProjRep path.

        Example path:

            ProjRep/000/000/000/001/803

        becomes:

            1803

        NOTE
        ----
        This is currently treated as a candidate object ID.
        We have not yet proven what this number represents.
        """

        numeric_parts = [
            part
            for part in path.parts
            if part.isdigit()
        ]

        if not numeric_parts:
            return None

        # The folder hierarchy appears to store one zero-padded number.
        combined = "".join(numeric_parts).lstrip("0")

        if not combined:
            return 0

        try:
            return int(combined)
        except ValueError:
            return None