from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass
class DbXmlMapAnalysis:
    path: Path
    root_tag: str
    total_elements: int
    tags: dict[str, int] = field(default_factory=dict)
    attributes: dict[str, int] = field(default_factory=dict)


class DbXmlMapExplorer:
    def analyze(self, xml_file: str | Path) -> DbXmlMapAnalysis:
        path = Path(xml_file)

        if not path.exists():
            raise FileNotFoundError(path)

        tree = ET.parse(path)
        root = tree.getroot()

        tag_counter = Counter()
        attr_counter = Counter()

        for element in root.iter():
            tag_counter[element.tag] += 1
            for attr in element.attrib:
                attr_counter[attr] += 1

        return DbXmlMapAnalysis(
            path=path,
            root_tag=root.tag,
            total_elements=sum(tag_counter.values()),
            tags=dict(tag_counter),
            attributes=dict(attr_counter),
        )