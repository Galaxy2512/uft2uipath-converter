"""
UFT Component Explorer

Responsibility
--------------
Inspects files and folders that may belong to UFT Business Components.

This module is used during reverse engineering of the UFT/QCP format.
It does not parse VBScript and does not generate UiPath workflows.

Its purpose is to answer questions such as:

- Which folders contain Script.mts files?
- Where are Action folders stored?
- Which files look like Object Repositories?
- Which resources belong to a component?
- What file extensions appear in UFT component definitions?

The information collected here will later guide the production
UFT Component Definition Parser.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UftComponentFile:
    """
    Represents one file found inside a potential UFT component structure.
    """

    path: Path
    relative_path: str
    file_name: str
    suffix: str
    size_bytes: int
    category: str


@dataclass
class UftComponentInspection:
    """
    Summary of files discovered inside an inspected folder.
    """

    root: Path
    files: list[UftComponentFile] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        """
        Return the total number of discovered files.
        """
        return len(self.files)

    def by_category(self, category: str) -> list[UftComponentFile]:
        """
        Return all files belonging to a specific category.
        """
        return [
            file
            for file in self.files
            if file.category == category
        ]


class UftComponentExplorer:
    """
    Inspects a folder and classifies possible UFT component files.
    """

    def inspect(
        self,
        component_folder: str | Path,
    ) -> UftComponentInspection:
        """
        Inspect a folder recursively.

        Parameters
        ----------
        component_folder:
            Folder containing extracted UFT component artifacts.

        Returns
        -------
        UftComponentInspection:
            Classified list of files found under the folder.
        """

        root = Path(component_folder)

        if not root.exists():
            raise FileNotFoundError(root)

        if not root.is_dir():
            raise NotADirectoryError(root)

        inspection = UftComponentInspection(root=root)

        # --------------------------------------------------------------
        # STEP 1
        # Walk through every file below the supplied root folder.
        # --------------------------------------------------------------
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue

            inspection.files.append(
                UftComponentFile(
                    path=path,
                    relative_path=str(path.relative_to(root)),
                    file_name=path.name,
                    suffix=path.suffix.lower(),
                    size_bytes=path.stat().st_size,
                    category=self._categorize(path),
                )
            )

        return inspection

    def _categorize(self, path: Path) -> str:
        """
        Classify a file based on its name, extension and path.

        NOTE
        ----
        These rules are intentionally broad.

        This explorer is a reverse-engineering tool, not the final parser.
        Once the real UFT storage structure is confirmed, production
        parsers will use stricter rules.
        """

        name = path.name.lower()
        full_path = str(path).lower()
        suffix = path.suffix.lower()

        # UFT Action scripts commonly use Script.mts.
        if name == "script.mts":
            return "script"

        # Resource.mtr commonly contains action metadata/resources.
        if name == "resource.mtr":
            return "action_resource"

        # Configuration files may contain component/action settings.
        if suffix == ".cfg":
            return "configuration"

        # UFT Object Repository files can use several formats.
        if (
            "objectrepository" in full_path
            or "object repository" in full_path
            or suffix in {".tsr", ".bdb"}
        ):
            return "object_repository"

        # Function libraries and scripts.
        if suffix in {".vbs", ".qfl"}:
            return "function_library"

        # Test data and Excel resources.
        if suffix in {".xls", ".xlsx", ".csv"}:
            return "data_table"

        # XML files may contain metadata or repository definitions.
        if suffix == ".xml":
            return "xml"

        # Action folders usually have names like Action0, Action1, ...
        if any(
            part.lower().startswith("action")
            for part in path.parts
        ):
            return "action_file"

        return "unknown"
