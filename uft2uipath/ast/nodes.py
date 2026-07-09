from __future__ import annotations

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
    """
    Represents an input/output parameter.
    """
    name: str
    value: Any = None
    datatype: str | None = None
    direction: str | None = None


@dataclass
class Step:
    """
    Represents one executable step inside a Business Component.
    """
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
    """
    Represents one UFT Business Component.
    """
    name: str

    description: str | None = None

    parameters: list[Parameter] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)

    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestCase:
    """
    Represents one UFT Test.
    """
    name: str

    description: str | None = None

    components: list[BusinessComponent] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)

    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedResource:
    """
    Shared resources (Object Repository, Function Library, Excel...).
    """
    name: str
    type: str

    path: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Project:
    """
    Root object representing the complete UFT project.
    """
    name: str

    source_path: str | None = None

    tests: list[TestCase] = field(default_factory=list)

    shared_resources: list[SharedResource] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)