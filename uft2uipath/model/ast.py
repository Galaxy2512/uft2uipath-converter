# Neutral intermediate-representation dataclasses for the QCP/ALM reading
# pipeline: OperationType/Operation, Component, TestCase, ConversionIssue,
# and the top-level MigrationModel that the generator consumes.

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class OperationType(str, Enum):
    """Kinds of operations the legacy classifier recognizes."""
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
    """A classified operation of a legacy component, with its confidence."""
    type: OperationType
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    confidence: float = 0.0

@dataclass
class Component:
    """A component found by the legacy QCP reader and its classified operations."""
    name: str
    operations: list[Operation] = field(default_factory=list)
    description: str | None = None
    raw_text: str | None = None
    source_files: list[str] = field(default_factory=list)

@dataclass
class TestCase:
    """A test found by the legacy QCP reader: the components it runs, by name."""
    name: str
    component_names: list[str] = field(default_factory=list)
    source: str | None = None

@dataclass
class ConversionIssue:
    """A problem reported by the legacy QCP reader."""
    severity: str
    item: str
    message: str

@dataclass
class MigrationModel:
    """Everything the legacy QCP reader found in an export."""
    source_qcp: str
    components: list[Component] = field(default_factory=list)
    tests: list[TestCase] = field(default_factory=list)
    extracted_dir: str | None = None
    issues: list[ConversionIssue] = field(default_factory=list)
