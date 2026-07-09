from dataclasses import dataclass, field
from pathlib import Path

from uft2uipath.discovery.project_discovery import ProjectDiscovery
from uft2uipath.discovery.xml_inspector import XmlInspectionResult, XmlInspector


@dataclass
class DiscoveryReport:
    project_root: Path
    total_files: int
    categories: dict[str, int] = field(default_factory=dict)
    xml_files: list[XmlInspectionResult] = field(default_factory=list)


class DiscoveryReportBuilder:
    def __init__(
        self,
        discovery: ProjectDiscovery | None = None,
        xml_inspector: XmlInspector | None = None,
    ):
        self.discovery = discovery or ProjectDiscovery()
        self.xml_inspector = xml_inspector or XmlInspector()

    def build(self, project_folder: str | Path) -> DiscoveryReport:
        result = self.discovery.discover(project_folder)

        categories: dict[str, int] = {}

        for file in result.files:
            categories[file.category] = categories.get(file.category, 0) + 1

        xml_files = []

        for file in result.by_category("xml"):
            try:
                xml_files.append(self.xml_inspector.inspect(file.path))
            except Exception:
                continue

        return DiscoveryReport(
            project_root=result.root,
            total_files=result.total_files,
            categories=categories,
            xml_files=xml_files,
        )