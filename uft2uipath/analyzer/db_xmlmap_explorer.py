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

    def list_tables(self, xml_file: str | Path) -> list[str]:
        path = Path(xml_file)

        if not path.exists():
            raise FileNotFoundError(path)

        tree = ET.parse(path)
        root = tree.getroot()

        tables = []

        for element in root.iter():
            if element.tag.lower() == "table":
                name = element.attrib.get("name")
                if name:
                    tables.append(name)

        return sorted(tables)

    def describe_table(self, xml_file: str | Path, table_name: str) -> list[str]:
        path = Path(xml_file)

        if not path.exists():
            raise FileNotFoundError(path)

        tree = ET.parse(path)
        root = tree.getroot()

        columns = []

        for table in root.iter():
            if table.tag.lower() == "t" and table.attrib.get("name", "").upper() == table_name.upper():
                for child in table:
                    if child.tag.lower() == "c":
                        name = child.attrib.get("name")
                        if name:
                            columns.append(name)

        return columns

    def describe_table_details(
            self,
            xml_file: str | Path,
            table_name: str,
    ) -> list[dict[str, str]]:
        """
        Return complete column metadata for one ALM table.

        This includes the column name, datatype, size and nullability.
        """

        path = Path(xml_file)

        if not path.exists():
            raise FileNotFoundError(path)

        tree = ET.parse(path)
        root = tree.getroot()

        columns: list[dict[str, str]] = []

        for table in root.iter():
            if (
                    table.tag.lower() == "t"
                    and table.attrib.get("name", "").upper() == table_name.upper()
            ):
                for child in table:
                    if child.tag.lower() != "c":
                        continue

                    columns.append(dict(child.attrib))

        return columns
