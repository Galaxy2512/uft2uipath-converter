from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiscoveredFile:
    path: Path
    relative_path: str
    suffix: str
    size_bytes: int
    category: str = "unknown"


@dataclass
class DiscoveryResult:
    root: Path
    files: list[DiscoveredFile] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.files)

    def by_category(self, category: str) -> list[DiscoveredFile]:
        return [file for file in self.files if file.category == category]


class ProjectDiscovery:
    def discover(self, project_folder: str | Path) -> DiscoveryResult:
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