"""ALM smart repository: logical file tree -> physical ProjRep blobs.

SMART_REPOSITORY_LOGICAL_FILE holds the virtual file system ALM exposes to
UFT (e.g. tests\\142\\Action1\\Script.mts); SRLF_PHYSICAL_ID points at
SMART_REPOSITORY_PHYSICAL_FILE, whose SRPF_PATH is a content-addressed blob
under ProjRep\\ in the export.
"""

from __future__ import annotations

from pathlib import Path, PureWindowsPath

from uft2uipath.alm.tables import AlmTables


def normalize(path: str) -> str:
    parts = [p for p in path.replace("/", "\\").split("\\") if p not in ("", ".")]
    return "\\".join(parts)


class SmartRepository:
    def __init__(self, tables: AlmTables):
        self.root = tables.root.resolve()
        physical = {
            row["SRPF_ID"]: row["SRPF_PATH"]
            for row in tables.rows("SMART_REPOSITORY_PHYSICAL_FILE")
        }
        self._files: dict[str, tuple[str, str | None]] = {}
        for row in tables.rows("SMART_REPOSITORY_LOGICAL_FILE"):
            if row.get("SRLF_IS_DIRECTORY") == "Y":
                continue
            logical = normalize((row.get("SRLF_PARENT_PATH") or "") + "\\" + (row.get("SRLF_NAME") or ""))
            self._files[logical.lower()] = (logical, physical.get(row.get("SRLF_PHYSICAL_ID")))

    def exists(self, logical: str) -> bool:
        return normalize(logical).lower() in self._files

    def files_under(self, folder: str) -> list[str]:
        prefix = normalize(folder).lower() + "\\"
        return sorted(name for key, (name, _) in self._files.items() if key.startswith(prefix))

    def physical_path(self, logical: str) -> Path:
        entry = self._files.get(normalize(logical).lower())
        if entry is None:
            raise FileNotFoundError(f"Not in ALM repository: {logical}")
        if not entry[1]:
            raise FileNotFoundError(f"No physical file recorded for: {logical}")
        path = (self.root / Path(*PureWindowsPath(normalize(entry[1])).parts)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Physical path escapes the export: {entry[1]}")
        return path

    def read_bytes(self, logical: str) -> bytes:
        return self.physical_path(logical).read_bytes()
