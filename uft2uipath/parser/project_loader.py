# Minimal filesystem helper wrapping an extracted project folder: exposes
# its root path, an existence check, and a recursive glob-based file finder.
# Used by AlmReader (and other loaders) as a thin base for locating files.

from pathlib import Path


class ProjectLoader:
    def __init__(self, project_folder: str | Path):
        self.project_folder = Path(project_folder)

    @property
    def root(self) -> Path:
        return self.project_folder

    def exists(self) -> bool:
        return self.project_folder.exists()

    def find(self, name: str):
        return list(self.project_folder.rglob(name))