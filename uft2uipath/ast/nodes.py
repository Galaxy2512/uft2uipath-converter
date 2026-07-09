from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepType(str, Enum):
    ACTION = "action"
    CONDITION = "condition"
    LOOP = "loop"
    VERIFICATION = "verification"
    COMMENT = "comment"
    UNKNOWN = "unknown"


@dataclass
class Parameter:
    name: str
    value: Any = None
    type: str | None = None
    direction: str | None = None


@dataclass
class Step:
    name: str
    type: StepType = StepType.UNKNOWN
    action: str | None = None
    target: str | None = None
    value: Any = None
    parameters: list[Parameter] = field(default_factory=list)
    children: list["Step"] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class BusinessComponent:
    name: str
    description: str | None = None
    parameters: list[Parameter] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestCase:
    name: str
    description: str | None = None
    components: list[BusinessComponent] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedResource:
    name: str
    type: str
    path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Project:
    name: str
    source_path: str | None = None
    tests: list[TestCase] = field(default_factory=list)
    shared_resources: list[SharedResource] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)