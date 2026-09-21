"""Decides which selector candidates may be used, and builds emitter bindings.

A candidate is used only when a review file accepts it explicitly, or when a
confidence threshold was given and the candidate reaches it. Accepted-by
threshold is recorded as such: it means "good enough to generate", never
"verified against the application".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from uft2uipath.script_generation.browser_scopes import BROWSER_TYPES
from uft2uipath.script_generation.emitter import target_key

IDENTITY_KEYS = ("browser", "page", "object_type", "logical_name")
INPUT_METHODS = {"Simulate", "HardwareEvents", "SendWindowMessages"}
DEFAULT_INPUT_METHOD = "Simulate"
_IDENTIFIER = re.compile(r"[^A-Za-z0-9_]")


class ReviewError(ValueError):
    pass


@dataclass
class AcceptanceSettings:
    threshold: float | None = None
    browser_type: str | None = None
    timeout_ms: int = 30000
    review: dict[tuple, dict[str, Any]] = field(default_factory=dict)


def identity_key(identity: dict[str, Any]) -> tuple:
    return target_key(identity)


def load_review(document: Any) -> dict[tuple, dict[str, Any]]:
    """Reads a review file: {"objects": [{"uft": {...}, "selector": ..., "accepted": true}]}."""
    if not isinstance(document, dict) or not isinstance(document.get("objects"), list):
        raise ReviewError("Review file must be an object with an objects array.")
    review = {}
    for entry in document["objects"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("uft"), dict):
            raise ReviewError("Every review entry needs a uft identity.")
        key = identity_key(entry["uft"])
        if not key:
            raise ReviewError(f"Incomplete UFT identity: {entry['uft']}")
        if key in review:
            raise ReviewError(f"Duplicate review entry for {key}.")
        review[key] = entry
    return review


def decide(entry: dict[str, Any], settings: AcceptanceSettings) -> dict[str, Any]:
    """Returns the acceptance decision for one resolved object reference."""
    identity = entry.get("uft")
    candidate = entry.get("candidate") or {}
    decision: dict[str, Any] = {
        "uft": identity, "path": entry["path"], "lines": entry["lines"],
        "status": entry["status"], "confidence": candidate.get("confidence"),
        "accepted": False, "accepted_by": None, "selector": None,
        "proposed": candidate.get("selector"), "reasons": [],
    }
    if identity is None:
        decision["reasons"].append("no_emitter_identity")
        return decision
    if not candidate.get("selector"):
        decision["reasons"].append("no_candidate")
        return decision

    reviewed = settings.review.get(identity_key(identity))
    if reviewed is not None:
        if reviewed.get("accepted") is not True:
            decision["reasons"].append("rejected_in_review")
            return decision
        selector = reviewed.get("selector") or candidate["selector"]
        source = "review"
    elif settings.threshold is None:
        decision["reasons"].append("no_review_entry_and_no_threshold")
        return decision
    elif candidate["confidence"] < settings.threshold:
        decision["reasons"].append(f"below_threshold: {candidate['confidence']} < {settings.threshold}")
        return decision
    else:
        reviewed, selector, source = {}, candidate["selector"], "threshold"

    kind = candidate.get("kind")
    if kind not in ("web", "desktop"):
        decision["reasons"].append(f"unsupported_target_kind: {kind}")
        return decision
    browser_type = reviewed.get("browser_type") or settings.browser_type
    if kind == "web" and browser_type not in BROWSER_TYPES:
        decision["reasons"].append("browser_type_required")
        return decision
    input_method = reviewed.get("input_method") or DEFAULT_INPUT_METHOD
    if input_method not in INPUT_METHODS:
        decision["reasons"].append(f"unsupported_input_method: {input_method}")
        return decision
    timeout = reviewed.get("timeout_ms", settings.timeout_ms)
    if type(timeout) is not int or not 0 < timeout < 2**31:
        decision["reasons"].append("invalid_timeout_ms")
        return decision

    binding = {
        "uft": {**{key: identity.get(key) for key in IDENTITY_KEYS},
                "path": identity.get("path")},
        "selector": selector, "kind": kind,
        # The emitter refuses unverified bindings; record how this one was accepted.
        "verified": True,
        "verification_note": f"Accepted by {source}; not verified against the application.",
        "input_method": input_method, "timeout_ms": timeout,
    }
    if kind == "web":
        binding["browser_type"] = browser_type
    decision.update(accepted=True, accepted_by=source, selector=selector, binding=binding)
    return decision


def argument_name(kind: str, name: str) -> str:
    cleaned = _IDENTIFIER.sub("_", name).strip("_") or "value"
    if not cleaned[0].isalpha():
        cleaned = "v" + cleaned
    return f"in_{kind}_{cleaned}"


def build_binding(analysis: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Builds the target binding the component emitter expects."""
    references = analysis.get("references", {})
    binding: dict[str, Any] = {"parameters": {}, "environment": {}, "data": {},
                               "secure": {}, "objects": []}
    for category, kind in (("parameters", "param"), ("environment", "env"),
                           ("data", "data"), ("secure", "secure")):
        for name in references.get(category, []):
            binding[category][name] = {
                "name": argument_name(kind, name), "type": "String", "direction": "In",
            }
    seen = set()
    for decision in decisions:
        if not decision["accepted"]:
            continue
        key = identity_key(decision["binding"]["uft"])
        if key in seen:
            continue
        seen.add(key)
        binding["objects"].append(decision["binding"])
    return binding


def review_template(actions: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Builds an editable review document from the decisions of every action."""
    objects, seen = [], set()
    for action, decisions in sorted(actions.items()):
        for decision in decisions:
            if decision["uft"] is None or not decision.get("confidence"):
                continue
            key = identity_key(decision["uft"])
            if key in seen:
                continue
            seen.add(key)
            objects.append({
                "uft": decision["uft"], "selector": decision["selector"] or decision.get("proposed"),
                "confidence": decision["confidence"], "accepted": decision["accepted"],
                "first_seen_in": action, "lines": decision["lines"],
                "input_method": DEFAULT_INPUT_METHOD, "timeout_ms": None, "browser_type": None,
            })
    return {
        "format_version": 1,
        "note": "Set accepted to true for selectors you have checked; pass this file with --selector-review.",
        "objects": objects,
    }
