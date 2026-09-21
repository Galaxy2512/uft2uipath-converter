# Parses a single XML file (e.g. from a UFT project) and reports basic
# structural facts about it: root tag, root attributes, and total element
# count, for use in discovery reports.

from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass
class XmlInspectionResult:
    """Root tag, root attributes and element count of one XML file."""
    path: Path
    root_tag: str
    attributes: dict[str, str] = field(default_factory=dict)
    element_count: int = 0


class XmlInspector:
    """Reads the outline of XML files found in a project."""
    def inspect(self, xml_file: str | Path) -> XmlInspectionResult:
        """Outline of one XML file."""
        path = Path(xml_file)

        if not path.exists():
            raise FileNotFoundError(path)

        tree = ET.parse(path)
        root = tree.getroot()

        return XmlInspectionResult(
            path=path,
            root_tag=root.tag,
            attributes=dict(root.attrib),
            element_count=sum(1 for _ in root.iter()),
        )