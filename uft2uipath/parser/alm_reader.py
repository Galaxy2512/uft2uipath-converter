from pathlib import Path

from uft2uipath.ast import Project
from .project_loader import ProjectLoader


class AlmReader:

    def read(self, project_folder: str | Path) -> Project:

        loader = ProjectLoader(project_folder)

        if not loader.exists():
            raise FileNotFoundError(project_folder)

        project = Project(
            name=loader.root.name,
            source_path=str(loader.root)
        )

        return project