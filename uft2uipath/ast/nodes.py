<<<<<<< HEAD
=======
from __future__ import annotations

>>>>>>> feature/archive-reader
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
<<<<<<< HEAD
    name: str
    value: Any = None
    type: str | None = None
=======
    """
    Represents an input/output parameter.
    """
    name: str
    value: Any = None
    datatype: str | None = None
>>>>>>> feature/archive-reader
    direction: str | None = None


@dataclass
class Step:
<<<<<<< HEAD
    name: str
    type: StepType = StepType.UNKNOWN
    action: str | None = None
    target: str | None = None
    value: Any = None
    parameters: list[Parameter] = field(default_factory=list)
    children: list["Step"] = field(default_factory=list)
=======
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

>>>>>>> feature/archive-reader
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class BusinessComponent:
<<<<<<< HEAD
    name: str
    description: str | None = None
    parameters: list[Parameter] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
=======
    """
    Represents one UFT Business Component.
    """
    name: str

    description: str | None = None

    parameters: list[Parameter] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)

>>>>>>> feature/archive-reader
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestCase:
<<<<<<< HEAD
    name: str
    description: str | None = None
    components: list[BusinessComponent] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
=======
    """
    Represents one UFT Test.
    """
    name: str

    description: str | None = None

    components: list[BusinessComponent] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)

>>>>>>> feature/archive-reader
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedResource:
<<<<<<< HEAD
    name: str
    type: str
    path: str | None = None
=======
    """
    Shared resources (Object Repository, Function Library, Excel...).
    """
    name: str
    type: str

    path: str | None = None

>>>>>>> feature/archive-reader
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Project:
<<<<<<< HEAD
    name: str
    source_path: str | None = None
    tests: list[TestCase] = field(default_factory=list)
    shared_resources: list[SharedResource] = field(default_factory=list)
=======
    """
    Root object representing the complete UFT project.
    """
    name: str

    source_path: str | None = None

    tests: list[TestCase] = field(default_factory=list)

    shared_resources: list[SharedResource] = field(default_factory=list)

>>>>>>> feature/archive-reader
    metadata: dict[str, Any] = field(default_factory=dict)