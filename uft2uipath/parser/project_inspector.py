from pathlib import Path


class ProjectInspector:

    def inspect(self, project_folder: str | Path) -> dict:

        root = Path(project_folder)

        files = list(root.rglob("*"))

        return {
            "project_name": root.name,
            "directories": len([x for x in files if x.is_dir()]),
            "files": len([x for x in files if x.is_file()]),
        }