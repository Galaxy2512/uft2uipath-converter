from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConversionStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class IssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class StepType(str, Enum):
    ACTION = "action"
    CONDITION = "condition"
    LOOP = "loop"
    VERIFICATION = "verification"
    COMMENT = "comment"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass
class ConversionIssue:
    message: str
    severity: IssueSeverity = IssueSeverity.WARNING
    source: str | None = None
    recommendation: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Parameter:
    name: str
    value: Any = None
    datatype: str | None = None
    direction: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Variable:
    name: str
    datatype: str | None = None
    default_value: Any = None
    scope: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ObjectRepositoryItem:
    name: str
    object_type: str | None = None
    selector: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataTable:
    name: str
    path: str | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Step:
    name: str
    type: StepType = StepType.UNKNOWN
    action: str | None = None
    target: str | None = None
    value: Any = None

    parameters: list[Parameter] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    children: list["Step"] = field(default_factory=list)
    issues: list[ConversionIssue] = field(default_factory=list)

    status: ConversionStatus = ConversionStatus.SUCCESS
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class BusinessComponent:
    name: str
    description: str | None = None

    parameters: list[Parameter] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    issues: list[ConversionIssue] = field(default_factory=list)

    status: ConversionStatus = ConversionStatus.SUCCESS
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class UftTestCase:
    name: str
    description: str | None = None

    components: list[BusinessComponent] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    data_tables: list[DataTable] = field(default_factory=list)
    issues: list[ConversionIssue] = field(default_factory=list)

    status: ConversionStatus = ConversionStatus.SUCCESS
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedResource:
    name: str
    type: str
    path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Project:
    name: str
    source_path: str | None = None

    tests: list[UftTestCase] = field(default_factory=list)
    shared_resources: list[SharedResource] = field(default_factory=list)
    object_repository: list[ObjectRepositoryItem] = field(default_factory=list)
    data_tables: list[DataTable] = field(default_factory=list)
    issues: list[ConversionIssue] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)