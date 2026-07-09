from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from uft2uipath.discovery.discovery_report import DiscoveryReportBuilder


@dataclass
class ProjectAnalysis:
    project_root: Path
    total_files: int
    extensions: dict[str, int] = field(default_factory=dict)
    categories: dict[str, int] = field(default_factory=dict)
    largest_files: list[tuple[str, int]] = field(default_factory=list)
    xml_roots: dict[str, int] = field(default_factory=dict)


class ProjectAnalyzer:
    def analyze(self, project_folder: str | Path) -> ProjectAnalysis:
        root = Path(project_folder)

        if not root.exists():
            raise FileNotFoundError(root)

        files = [path for path in root.rglob("*") if path.is_file()]
        report = DiscoveryReportBuilder().build(root)

        extensions = Counter(path.suffix.lower() or "<no_ext>" for path in files)

        largest_files = sorted(
            [(str(path.relative_to(root)), path.stat().st_size) for path in files],
            key=lambda item: item[1],
            reverse=True,
        )[:20]

        xml_roots = Counter(xml.root_tag for xml in report.xml_files)

        return ProjectAnalysis(
            project_root=root,
            total_files=len(files),
            extensions=dict(extensions),
            categories=report.categories,
            largest_files=largest_files,
            xml_roots=dict(xml_roots),
        )