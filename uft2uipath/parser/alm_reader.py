# Thin ALM project entry point: locates a project folder via ProjectLoader
# and wraps it in a bare Project AST object (name/source_path only). Unlike
# ProjectBuilder, it does not populate tests/components/steps from ALM rows.

from pathlib import Path

from uft2uipath.ast import Project
from .project_loader import ProjectLoader


class AlmReader:

    """Reads a project folder into the neutral model through ProjectLoader. Legacy path, not used
    by convert.
    """
    def read(self, project_folder: str | Path) -> Project:

        """Load the project folder into a Project."""
        loader = ProjectLoader(project_folder)

        if not loader.exists():
            raise FileNotFoundError(project_folder)

        project = Project(
            name=loader.root.name,
            source_path=str(loader.root)
        )

        return project