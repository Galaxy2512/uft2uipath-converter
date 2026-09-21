"""Resolves script object references against an action's local repository."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from uft2uipath.mapping.selector_candidates import propose
from uft2uipath.uft.object_references import ObjectReference, extract_references
from uft2uipath.uft.object_repository import ObjectRepository

# UFT built-ins that appear in object position but are not test objects.
NON_OBJECT_CLASSES = {"checkpoint", "outputvalue"}


def resolve_objects(text: str, repositories: list[tuple[str, ObjectRepository]]) -> list[dict[str, Any]]:
    """repositories: (name, repository) in UFT lookup order - local first, then shared."""
    grouped: dict[tuple, dict[str, Any]] = {}
    for reference in extract_references(text):
        entry = grouped.get(reference.key())
        if entry is None:
            entry = grouped[reference.key()] = _resolve(reference, repositories)
        entry["lines"].append(reference.line)
    return list(grouped.values())


def _lookup(repositories, path):
    """First repository, in UFT lookup order, that has the object path."""
    for name, repository in repositories:
        found = repository.find(path)
        if found is not None:
            return name, found
    return None, None


def _resolve(reference: ObjectReference, repositories) -> dict[str, Any]:
    """Resolve one reference to repository objects and propose a selector for its target."""
    entry: dict[str, Any] = {
        "lines": [],
        "path": [{"class": s.test_object_class, "name": s.name, "description": s.description}
                 for s in reference.path],
        "source": reference.source,
    }
    if reference.dynamic:
        return {**entry, "status": "dynamic", "candidate": None}
    if len(reference.path) == 1 and reference.path[0].test_object_class.casefold() in NON_OBJECT_CLASSES:
        return {**entry, "status": "checkpoint", "candidate": None}

    chain = []
    for depth, step in enumerate(reference.path, 1):
        if step.description:
            chain.append({"class": step.test_object_class, "name": None,
                          "properties": dict(step.description), "identification": list(step.description)})
            continue
        named = [(s.test_object_class, s.name) for s in reference.path[:depth]]
        source, obj = (None, None)
        if not any(s.description for s in reference.path[:depth]):
            source, obj = _lookup(repositories, named)
        if obj is None or obj.issue:
            status = "no_repository" if not repositories else "not_in_repository"
            if obj is not None:
                status = obj.issue
            return {**entry, "status": status, "missing_at": step.name, "candidate": None}
        entry["repository"] = source
        chain.append({"class": obj.test_object_class, "name": obj.logical_name,
                      "properties": {p.name: p.value for p in obj.properties},
                      "identification": obj.mandatory})

    target = chain[-1]
    if not reference.descriptive:
        classes = [s.test_object_class.casefold() for s in reference.path]
        identity: dict[str, Any] = {
            "path": [{"class": s.test_object_class, "name": s.name} for s in reference.path],
        }
        # Web objects also carry the flat identity the emitter's browser scopes use.
        if classes[:2] == ["browser", "page"] and len(reference.path) in (2, 3):
            last = reference.path[2] if len(reference.path) == 3 else None
            identity.update(
                browser=reference.path[0].name, page=reference.path[1].name,
                object_type=last.test_object_class if last else "Page",
                logical_name=last.name if last else reference.path[1].name,
            )
        entry["uft"] = identity
    return {
        **entry,
        "status": "descriptive" if reference.descriptive else "resolved",
        "identification": {name: target["properties"].get(name) for name in target["identification"]},
        "candidate": asdict(propose(chain)),
    }
