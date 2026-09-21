# Walks an extracted UFT project directory and classifies every file into a
# coarse category (xml, vbscript, data_table, object_repository, component,
# test, unknown) based on extension and path keywords, for discovery reports.

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiscoveredFile:
    """One file of an extracted project, with its category."""
    path: Path
    relative_path: str
    suffix: str
    size_bytes: int
    category: str = "unknown"


@dataclass
class DiscoveryResult:
    """All files found in a project folder."""
    root: Path
    files: list[DiscoveredFile] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        """Number of files found."""
        return len(self.files)

    def by_category(self, category: str) -> list[DiscoveredFile]:
        """Files of one category."""
        return [file for file in self.files if file.category == category]


class ProjectDiscovery:
    """Walks an extracted project folder and categorizes its files."""
    def discover(self, project_folder: str | Path) -> DiscoveryResult:
        """Find and categorize every file below the project folder."""
        root = Path(project_folder)

        if not root.exists():
            raise FileNotFoundError(root)

        result = DiscoveryResult(root=root)

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue

            result.files.append(
                DiscoveredFile(
                    path=path,
                    relative_path=str(path.relative_to(root)),
                    suffix=path.suffix.lower(),
                    size_bytes=path.stat().st_size,
                    category=self._categorize(path),
                )
            )

        return result

    def _categorize(self, path: Path) -> str:
        """Category of a file from its name, extension and location."""
        name = path.name.lower()
        suffix = path.suffix.lower()
        full = str(path).lower()

        if suffix == ".xml":
            return "xml"

        if suffix in [".vbs", ".qfl"]:
            return "vbscript"

        if suffix in [".xls", ".xlsx", ".csv"]:
            return "data_table"

        if "object" in full or "repository" in full:
            return "object_repository"

        if "component" in full:
            return "component"

        if "test" in full:
            return "test"

        return "unknown"