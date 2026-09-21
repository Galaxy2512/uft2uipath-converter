"""Proposes UiPath selectors from UFT identification properties.

Only properties UFT itself uses to identify the object (the mandatory list,
or the inline description in descriptive programming) plus strong assistive
identifiers (html id, name) are mapped. A candidate is never marked verified;
confidence reflects how identifying the mapped attributes are, not whether
the selector matches the live application.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

WEB_ROOTS = {"browser"}
WEB_PAGES = {"page"}
WEB_FRAMES = {"frame"}
WEB_CONTROLS = {"webedit", "webbutton", "webelement", "weblist", "webcheckbox", "webradiogroup",
                "webtable", "webfile", "webarea", "link", "image", "webnumber", "webrange"}
WIN_WINDOWS = {"window", "dialog"}
WIN_CONTROLS = {"winedit", "winbutton", "wincheckbox", "winradiobutton", "wincombobox", "winlist",
                "winlistview", "wintreeview", "wintab", "wintoolbar", "static", "winobject", "wineditor"}

# UFT property -> UiPath webctrl attribute.
WEB_ATTRIBUTES = {"html tag": "tag", "html id": "id", "name": "name", "type": "type", "class": "class",
                  "innertext": "innertext", "text": "innertext", "alt": "aaname", "href": "href"}
# UFT property -> UiPath wnd attribute.
WIN_ATTRIBUTES = {"nativeclass": "cls", "regexpwndclass": "cls", "window id": "ctrlid",
                  "regexpwndtitle": "title", "title": "title", "text": "title",
                  "attached text": "aaname"}
STRONG = {"id": 0.35, "ctrlid": 0.3, "name": 0.3, "aaname": 0.2, "innertext": 0.2, "href": 0.2, "title": 0.15}
WEAK = {"tag": 0.1, "type": 0.05, "class": 0.05, "cls": 0.1}
MAX_CONFIDENCE = 0.85


@dataclass
class SelectorCandidate:
    """A proposed selector with its confidence, the evidence used and its known weaknesses."""
    selector: str | None
    confidence: float
    requires_review: bool = True
    verified: bool = False
    kind: str | None = None
    evidence: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def propose(chain: list[dict[str, Any]]) -> SelectorCandidate:
    """chain: root-to-target steps, each {"class", "name", "properties", "identification"}."""
    classes = [step["class"].casefold() for step in chain]
    target = classes[-1]
    if classes[0] in WEB_ROOTS and (target in WEB_CONTROLS or target in WEB_PAGES):
        return _web(chain)
    if target in WIN_CONTROLS | WIN_WINDOWS and any(c in WIN_WINDOWS for c in classes):
        return _win(chain)
    return SelectorCandidate(None, 0.0, issues=[f"unsupported_class: {chain[-1]['class']}"])


def _web(chain) -> SelectorCandidate:
    """Web selector: <html title> from the page, frames, then the target webctrl."""
    candidate = SelectorCandidate(None, 0.0, kind="web")
    html = ET.Element("html")
    page = next((s for s in chain if s["class"].casefold() in WEB_PAGES), None)
    title = _value(page, "title") if page else None
    if title:
        html.set("title", title)
        candidate.evidence.append(f"Page title {title!r}")
    else:
        candidate.issues.append("page_title_unknown")
    nodes = [html]
    for step in chain[1:]:
        cls = step["class"].casefold()
        if cls in WEB_FRAMES:
            frame = _element("webctrl", step, WEB_ATTRIBUTES, candidate)
            frame.set("tag", frame.get("tag") or "IFRAME")
            nodes.append(frame)
        elif cls in WEB_CONTROLS and step is chain[-1]:
            nodes.append(_element("webctrl", step, WEB_ATTRIBUTES, candidate))
    if chain[-1]["class"].casefold() in WEB_CONTROLS and len(nodes) == 1:
        candidate.issues.append("target_not_mapped")
    candidate.selector = "".join(ET.tostring(node, encoding="unicode") for node in nodes)
    candidate.confidence = _score(nodes[-1] if len(nodes) > 1 else html, bool(title))
    candidate.issues.append("browser_app_unspecified")
    return candidate


def _win(chain) -> SelectorCandidate:
    """Desktop selector: the top window, then the target control."""
    candidate = SelectorCandidate(None, 0.0, kind="desktop")
    windows = [s for s in chain if s["class"].casefold() in WIN_WINDOWS]
    top = _element("wnd", windows[-1], WIN_ATTRIBUTES, candidate)
    nodes = [top]
    if chain[-1] is not windows[-1]:
        nodes.append(_element("wnd", chain[-1], WIN_ATTRIBUTES, candidate))
    candidate.selector = "".join(ET.tostring(node, encoding="unicode") for node in nodes)
    candidate.confidence = _score(nodes[-1], bool(top.get("title")))
    candidate.issues.append("process_name_unspecified")
    return candidate


def _element(tag: str, step, mapping, candidate: SelectorCandidate) -> ET.Element:
    """Selector node from a step's identification properties plus strong assistive ones."""
    element = ET.Element(tag)
    used = []
    names = list(step.get("identification") or [])
    # Strong assistive identifiers help UiPath even when UFT did not need them.
    names += [p for p in ("html id", "name", "window id") if p not in names]
    for prop in names:
        attribute = mapping.get(prop.casefold())
        value = _value(step, prop)
        if attribute and value not in (None, "") and element.get(attribute) is None:
            text = str(value)
            if attribute == "type" and (element.get("tag") or str(_value(step, "html tag") or "")).upper() != "INPUT":
                continue
            element.set(attribute, text)
            used.append(f"{step['class']}.{prop}={text!r} -> {attribute}")
    if not used:
        candidate.issues.append(f"no_mappable_properties: {step['class']}({step.get('name')!r})")
    candidate.evidence.extend(used)
    return element


def _value(step, name: str):
    """Property value by case-insensitive name, or None."""
    wanted = name.casefold()
    for key, value in (step.get("properties") or {}).items():
        if key.casefold() == wanted:
            return value
    return None


def _score(element: ET.Element, has_top_title: bool) -> float:
    """Confidence from the attributes used, lowered without a window/page title, capped below 1."""
    score = sum(STRONG.get(a, 0) + WEAK.get(a, 0) for a in element.attrib)
    if not has_top_title:
        score -= 0.15
    return round(max(0.0, min(MAX_CONFIDENCE, score)), 2)
