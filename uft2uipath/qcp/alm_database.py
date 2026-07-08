from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re

TEXT_EXTENSIONS = {".xml", ".txt", ".vbs", ".mtr", ".ini", ".csv", ".html", ".htm", ".json", ".sql", ".td"}

@dataclass
class AlmTextFile:
    path: Path
    text: str

@dataclass
class AlmDatabase:
    root: Path
    files: list[AlmTextFile] = field(default_factory=list)

    @classmethod
    def load(cls, root: str | Path) -> "AlmDatabase":
        root = Path(root)
        db = cls(root=root)
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            try:
                if p.stat().st_size > 5_000_000:
                    continue
                suffix = p.suffix.lower()
                # ALM tables may have unusual/no extensions; try small files as text safely.
                data = p.read_bytes()
                if suffix not in TEXT_EXTENSIONS and b"\x00" in data[:4096]:
                    continue
                text = data.decode("utf-8", errors="ignore")
                if text.strip():
                    db.files.append(AlmTextFile(path=p, text=text))
            except Exception:
                continue
        return db

    @property
    def blob(self) -> str:
        return "\n".join(f.text for f in self.files)

    def snippets_for(self, token: str, radius: int = 2500) -> tuple[str, list[str]]:
        snippets: list[str] = []
        sources: list[str] = []
        if not token:
            return "", []
        token_re = re.compile(re.escape(token), re.I)
        for f in self.files:
            for m in token_re.finditer(f.text):
                start = max(0, m.start() - radius)
                end = min(len(f.text), m.end() + radius)
                snippets.append(f.text[start:end])
                sources.append(str(f.path.relative_to(self.root)))
                if len(snippets) >= 20:
                    return "\n".join(snippets), sources
        return "\n".join(snippets), sources
