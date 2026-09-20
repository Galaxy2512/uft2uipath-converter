"""Resolves ALM resource references to files in the project repository.

UFT stores references as "[QC-RESOURCE];;<folder path>;;\\<file name>". The
RESOURCE_FOLDERS tree gives the folder, RESOURCES the file, and the stored
file lives under resources\\<RSC_ID>\\<RSC_FILE_NAME>.
"""

from __future__ import annotations

from typing import Any

QC_RESOURCE = "[QC-RESOURCE]"


def parse_reference(reference: str) -> tuple[str, str] | None:
    """Returns (folder path, file name) for a QC resource reference."""
    parts = reference.split(";;")
    if len(parts) != 3 or parts[0].strip().upper() != QC_RESOURCE:
        return None
    return parts[1].strip().strip("\\"), parts[2].strip().strip("\\")


class ResourceIndex:
    def __init__(self, resource_rows: list[dict[str, Any]], folder_rows: list[dict[str, Any]]):
        folders = {row["RFO_ID"]: row for row in folder_rows}
        self._paths: dict[int, str] = {}
        for folder_id in folders:
            names, current, seen = [], folder_id, set()
            while current in folders and current not in seen:
                seen.add(current)
                names.append(folders[current].get("RFO_NAME") or "")
                current = folders[current].get("RFO_PARENT_ID")
            self._paths[folder_id] = "\\".join(reversed(names)).casefold()
        self._resources = resource_rows

    def find(self, folder_path: str, file_name: str) -> str | None:
        wanted_folder = folder_path.strip("\\").casefold()
        wanted_file = file_name.casefold()
        for row in self._resources:
            names = {str(row.get(key) or "").casefold() for key in ("RSC_FILE_NAME", "RSC_NAME")}
            if wanted_file not in names or row.get("RSC_ID") is None:
                continue
            if self._paths.get(row.get("RSC_PARENT_ID")) != wanted_folder:
                continue
            stored = row.get("RSC_FILE_NAME") or row.get("RSC_NAME")
            return f"resources\\{row['RSC_ID']}\\{stored}"
        return None
