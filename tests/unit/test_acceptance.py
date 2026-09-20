import pytest

from uft2uipath.mapping.acceptance import (AcceptanceSettings, ReviewError, argument_name,
                                           build_binding, decide, load_review, review_template)

IDENTITY = {"browser": "B", "page": "P", "object_type": "WebEdit", "logical_name": "userName"}
SELECTOR = '<html title="Welcome" /><webctrl name="userName" tag="INPUT" />'


def entry(confidence=0.6, identity=IDENTITY, kind="web", selector=SELECTOR):
    return {"uft": identity, "path": [{"class": "WebEdit", "name": "userName"}], "lines": [3],
            "status": "resolved",
            "candidate": {"selector": selector, "confidence": confidence, "kind": kind,
                          "verified": False, "requires_review": True, "evidence": [], "issues": []}}


def settings(**overrides):
    return AcceptanceSettings(**{"browser_type": "Edge", **overrides})


def test_threshold_accepts_confident_candidates_only():
    accepted = decide(entry(0.6), settings(threshold=0.5))
    rejected = decide(entry(0.4), settings(threshold=0.5))

    assert accepted["accepted"] and accepted["accepted_by"] == "threshold"
    assert accepted["binding"]["selector"] == SELECTOR
    assert accepted["binding"]["verified"] is True
    assert "not verified against the application" in accepted["binding"]["verification_note"]
    assert not rejected["accepted"] and rejected["reasons"] == ["below_threshold: 0.4 < 0.5"]


def test_without_a_threshold_nothing_is_accepted_automatically():
    decision = decide(entry(0.9), settings())
    assert not decision["accepted"]
    assert decision["reasons"] == ["no_review_entry_and_no_threshold"]


def test_review_accepts_rejects_and_overrides_low_confidence_candidates():
    review = load_review({"objects": [
        {"uft": IDENTITY, "selector": "<html /><webctrl id='user' />", "accepted": True,
         "input_method": "HardwareEvents", "timeout_ms": 5000, "browser_type": "Chrome"},
    ]})
    accepted = decide(entry(0.1), settings(review=review))

    assert accepted["accepted"] and accepted["accepted_by"] == "review"
    assert accepted["binding"]["selector"] == "<html /><webctrl id='user' />"
    assert accepted["binding"]["input_method"] == "HardwareEvents"
    assert accepted["binding"]["timeout_ms"] == 5000
    assert accepted["binding"]["browser_type"] == "Chrome"


def test_review_can_reject_a_candidate_the_threshold_would_accept():
    review = load_review({"objects": [{"uft": IDENTITY, "accepted": False}]})
    decision = decide(entry(0.9), settings(threshold=0.1, review=review))

    assert not decision["accepted"] and decision["reasons"] == ["rejected_in_review"]


def test_missing_browser_type_and_desktop_targets_are_not_generated():
    no_browser = decide(entry(), AcceptanceSettings(threshold=0.1))
    desktop = decide(entry(kind="desktop"), settings(threshold=0.1))
    unresolved = decide({"uft": None, "path": [], "lines": [1], "status": "dynamic", "candidate": None},
                        settings(threshold=0.1))

    assert no_browser["reasons"] == ["browser_type_required"]
    assert desktop["reasons"] == ["unsupported_target_kind: desktop"]
    assert unresolved["reasons"] == ["no_emitter_identity"]
    assert not any(d["accepted"] for d in (no_browser, desktop, unresolved))


def test_invalid_review_documents_are_rejected():
    with pytest.raises(ReviewError, match="objects array"):
        load_review({"selectors": []})
    with pytest.raises(ReviewError, match="uft identity"):
        load_review({"objects": [{"selector": "x"}]})
    with pytest.raises(ReviewError, match="Duplicate"):
        load_review({"objects": [{"uft": IDENTITY}, {"uft": dict(IDENTITY)}]})


def test_binding_names_arguments_for_parameters_and_environment():
    analysis = {"references": {"parameters": ["Agent Name"], "environment": ["1stURL"]}}
    decisions = [decide(entry(0.6), settings(threshold=0.5)), decide(entry(0.1), settings(threshold=0.5))]

    binding = build_binding(analysis, decisions)

    assert binding["parameters"] == {"Agent Name": {"name": "in_param_Agent_Name", "type": "String",
                                                    "direction": "In"}}
    assert binding["environment"] == {"1stURL": {"name": "in_env_v1stURL", "type": "String",
                                                 "direction": "In"}}
    assert [obj["uft"] for obj in binding["objects"]] == [IDENTITY]
    assert argument_name("param", "!!!") == "in_param_value"


def test_review_template_lists_every_proposed_selector_once():
    other = dict(IDENTITY, logical_name="password")
    decisions = {
        "a/Action1": [decide(entry(0.6), settings(threshold=0.5)), decide(entry(0.6), settings(threshold=0.5))],
        "b/Action1": [decide(entry(0.2, identity=other), settings(threshold=0.5))],
    }

    template = review_template(decisions)

    assert [(obj["uft"]["logical_name"], obj["accepted"]) for obj in template["objects"]] == [
        ("userName", True), ("password", False),
    ]
    assert template["objects"][1]["selector"] == SELECTOR
