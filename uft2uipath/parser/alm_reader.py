
from pathlib import Path

from .project_loader import ProjectLoader


class AlmReader:
    def read(self, project_folder: str | Path):
        loader = ProjectLoader(project_folder)

        if not loader.exists():
            raise FileNotFoundError(project_folder)

        return {
            "tests": loader.find("Test.xml"),
            "components": loader.find("Component.xml"),
            "resources": loader.find("Resource.xml"),
        }
