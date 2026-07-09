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
    """
    Represents a UFT/ALM parameter.

    This can become a UiPath argument later.
    """

    name: str
    value: Any = None
    datatype: str | None = None
    direction: str | None = None

    # ALM traceability
    id: int | None = None
    source_entity: str | None = None
    source_id: int | None = None

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
    """
    Represents one executable or descriptive UFT step.

    This will later become one or more UiPath activities.
    """

    name: str
    type: StepType = StepType.UNKNOWN

    # ALM identity and ordering
    id: int | None = None
    order: int | None = None

    # Step content
    action: str | None = None
    target: str | None = None
    value: Any = None
    description: str | None = None
    expected_result: str | None = None

    parameters: list[Parameter] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    children: list["Step"] = field(default_factory=list)
    issues: list[ConversionIssue] = field(default_factory=list)

    status: ConversionStatus = ConversionStatus.SUCCESS
    raw: dict[str, Any] = field(default_factory=dict)

@dataclass
class BusinessComponent:
    """
    Represents one ALM/UFT Business Component.

    This will later become a reusable UiPath XAML workflow.
    """

    name: str

    # ALM identity
    id: int | None = None
    alm_status: str | None = None
    script_type: str | None = None
    component_type: str | None = None

    description: str | None = None

    parameters: list[Parameter] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    issues: list[ConversionIssue] = field(default_factory=list)

    status: ConversionStatus = ConversionStatus.SUCCESS
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class UftTestCase:
    """
    Represents one ALM/UFT test case.

    This will later become a UiPath Test Case.
    """

    name: str

    # ALM identity
    id: int | None = None
    alm_status: str | None = None
    test_type: str | None = None
    execution_status: str | None = None

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
    """
    Shared ALM/UFT resources.

    Examples:
    - Excel data tables
    - Function libraries
    - Application Areas
    - Object repositories
    """

    name: str
    type: str

    id: int | None = None
    file_name: str | None = None
    location_type: str | None = None
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