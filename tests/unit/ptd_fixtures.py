"""Builds synthetic ALM exports in the PTD row format for tests."""
import struct
from pathlib import Path

NULL = object()


def encode_value(datatype, value):
    if value is None:
        value = NULL
    if datatype == "timestamp":
        return b"\xff" * 8 if value is NULL else struct.pack(">q", value)
    if value is NULL:
        return b"\x01"
    if datatype in ("int", "short"):
        return b"\x00" + struct.pack(">i", value)
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return b"\x00" + struct.pack(">i", len(raw)) + raw


def encode_rows(columns, rows):
    return b"".join(
        encode_value(datatype, row.get(name, NULL))
        for row in rows for name, datatype in columns
    )


def schema_xml(tables):
    parts = ['<?xml version="1.0" encoding="UTF-8"?><Scheme>']
    for table, columns in tables.items():
        parts.append(f'<t name="{table}">')
        parts.extend(f'<c name="{name}" type="{datatype}" />' for name, datatype in columns)
        parts.append("</t>")
    parts.append("</Scheme>")
    return "".join(parts)


TEST_COLUMNS = [("TS_TEST_ID", "int"), ("TS_NAME", "varchar"), ("TS_TYPE", "varchar"),
                ("TS_CREATION_DATE", "timestamp"), ("TS_DESCRIPTION", "clob"), ("TS_PATH", "varchar")]
COMPONENT_COLUMNS = [("CO_ID", "int"), ("CO_NAME", "varchar"), ("CO_SCRIPT_TYPE", "varchar"),
                     ("CO_SUBTYPE_ID", "varchar"), ("CO_PHYSICAL_PATH", "varchar"),
                     ("CO_BPTA_FLOW_TEST_ID", "int")]
STEP_COLUMNS = [("CS_STEP_ID", "int"), ("CS_COMPONENT_ID", "int"), ("CS_STEP_ORDER", "int"),
                ("CS_STEP_NAME", "varchar")]
RELATION_COLUMNS = [("BC_ID", "int"), ("BC_BPT_ID", "int"), ("BC_CO_ID", "int"), ("BC_ORDER", "int"),
                    ("BC_PARENT_ID", "int"), ("BC_PARENT_TYPE", "varchar"), ("BC_SUBTYPE_ID", "varchar"),
                    ("BC_NAME", "varchar"), ("BC_BPTA_CONDITION", "clob")]
LOGICAL_COLUMNS = [("SRLF_ID", "int"), ("SRLF_PARENT_PATH", "varchar"), ("SRLF_NAME", "varchar"),
                   ("SRLF_PHYSICAL_ID", "int"), ("SRLF_IS_DIRECTORY", "varchar")]
PHYSICAL_COLUMNS = [("SRPF_ID", "int"), ("SRPF_PATH", "varchar")]


def write_export(root: Path, tables: dict, project_name="SYNTHETIC_ALM"):
    """tables maps name -> (columns, rows); every name gets schema and data."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "tables").mkdir()
    (root / "db_xmlmap.xml").write_text(
        schema_xml({name: columns for name, (columns, _) in tables.items()}), encoding="utf-8",
    )
    (root / "dbid.xml").write_text(
        f"<ProjectDescription><PROJECT_NAME>{project_name}</PROJECT_NAME>"
        "<DB_USER_PASS>secret</DB_USER_PASS></ProjectDescription>",
        encoding="utf-8",
    )
    for name, (columns, rows) in tables.items():
        (root / "tables" / f"{name}_!000001.ptd").write_bytes(encode_rows(columns, rows))
    return root


def repository_tables(root: Path, files: dict[str, bytes]):
    """Stores files as ProjRep blobs; returns SMART_REPOSITORY_* table entries."""
    logical, physical = [], []
    for number, (path, data) in enumerate(sorted(files.items()), 1):
        blob = f"ProjRep\\000\\{number:03d}"
        (root / "ProjRep" / "000").mkdir(parents=True, exist_ok=True)
        (root / "ProjRep" / "000" / f"{number:03d}").write_bytes(data)
        parent, _, name = ("." + "\\" + path).rpartition("\\")
        logical.append({"SRLF_ID": number, "SRLF_PARENT_PATH": parent + "\\", "SRLF_NAME": name,
                        "SRLF_PHYSICAL_ID": number, "SRLF_IS_DIRECTORY": "N"})
        physical.append({"SRPF_ID": number, "SRPF_PATH": ".\\" + blob})
    return {
        "SMART_REPOSITORY_LOGICAL_FILE": (LOGICAL_COLUMNS, logical),
        "SMART_REPOSITORY_PHYSICAL_FILE": (PHYSICAL_COLUMNS, physical),
    }


def minimal_bpt_export(root: Path):
    return write_export(root, {
        "TEST": (TEST_COLUMNS, [
            {"TS_TEST_ID": 7, "TS_NAME": "Create order", "TS_TYPE": "BUSINESS-PROCESS",
             "TS_CREATION_DATE": 1421877600000, "TS_DESCRIPTION": "<html>Zürich</html>"},
            {"TS_TEST_ID": 8, "TS_NAME": "Manual check", "TS_TYPE": "MANUAL"},
        ]),
        "COMPONENT": (COMPONENT_COLUMNS, [
            {"CO_ID": 1, "CO_NAME": "Login", "CO_SCRIPT_TYPE": "QT-KW"},
            {"CO_ID": 2, "CO_NAME": "Logout", "CO_SCRIPT_TYPE": "QT-KW"},
        ]),
        "COMPONENT_STEP": (STEP_COLUMNS, []),
        "BPTEST_TO_COMPONENTS": (RELATION_COLUMNS, [
            {"BC_ID": 11, "BC_BPT_ID": 7, "BC_CO_ID": 2, "BC_ORDER": 400},
            {"BC_ID": 10, "BC_BPT_ID": 7, "BC_CO_ID": 1, "BC_ORDER": 200},
        ]),
        "SMART_REPOSITORY_LOGICAL_FILE": (LOGICAL_COLUMNS, []),
        "SMART_REPOSITORY_PHYSICAL_FILE": (PHYSICAL_COLUMNS, []),
    })
