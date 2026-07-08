from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class OperationType(str, Enum):
    BROWSER_START = "browser_start"
    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_CLOSE = "browser_close"
    CHECK_WEBSITE = "check_website"
    LOGIN = "login"
    READ_EXCEL = "read_excel"
    SELECT = "select"
    CLICK = "click"
    TYPE_INTO = "type_into"
    WAIT = "wait"
    VERIFY = "verify"
    CONDITION = "condition"
    LOOP = "loop"
    CUSTOM_CODE = "custom_code"
    UNKNOWN = "unknown"

@dataclass
class Operation:
    type: OperationType
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    confidence: float = 0.0

@dataclass
class Component:
    name: str
    operations: list[Operation] = field(default_factory=list)
    description: str | None = None
    raw_text: str | None = None
    source_files: list[str] = field(default_factory=list)

@dataclass
class TestCase:
    name: str
    component_names: list[str] = field(default_factory=list)
    source: str | None = None

@dataclass
class ConversionIssue:
    severity: str
    item: str
    message: str

@dataclass
class MigrationModel:
    source_qcp: str
    components: list[Component] = field(default_factory=list)
    tests: list[TestCase] = field(default_factory=list)
    extracted_dir: str | None = None
    issues: list[ConversionIssue] = field(default_factory=list)
