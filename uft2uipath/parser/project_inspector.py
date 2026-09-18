# Lightweight diagnostic utility: given a project folder path, reports its
# name plus a count of contained directories and files. Used for a quick
# sanity check of an extracted project before running the full parser chain.

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