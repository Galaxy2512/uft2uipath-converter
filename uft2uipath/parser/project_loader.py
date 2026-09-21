# Minimal filesystem helper wrapping an extracted project folder: exposes
# its root path, an existence check, and a recursive glob-based file finder.
# Used by AlmReader (and other loaders) as a thin base for locating files.

from pathlib import Path


class ProjectLoader:
    """File access to a project folder for the legacy readers."""
    def __init__(self, project_folder: str | Path):
        """Remember the project folder."""
        self.project_folder = Path(project_folder)

    @property
    def root(self) -> Path:
        """The project folder."""
        return self.project_folder

    def exists(self) -> bool:
        """True if the project folder exists."""
        return self.project_folder.exists()

    def find(self, name: str):
        """Files named name anywhere below the project folder."""
        return list(self.project_folder.rglob(name))