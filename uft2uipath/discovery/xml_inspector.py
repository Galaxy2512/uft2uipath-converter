from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass
class XmlInspectionResult:
    path: Path
    root_tag: str
    attributes: dict[str, str] = field(default_factory=dict)
    element_count: int = 0


class XmlInspector:
    def inspect(self, xml_file: str | Path) -> XmlInspectionResult:
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