"""Attach to explicitly mapped browsers without moving condition evaluation."""
import xml.etree.ElementTree as ET

from uft2uipath.contracts.targets import BROWSER_TYPES, target_key
from uft2uipath.script_generation.emitter import UI, X, q


def browser_target(binding):
    """Split a full selector at its HTML root; never infer a browser type."""
    if binding.get("browser_type") not in BROWSER_TYPES:
        raise ValueError("Explicit browser_type required: IE, Firefox, Chrome, Edge or Custom.")
    fragment = ET.fromstring("<root>" + binding["selector"] + "</root>")
    nodes = list(fragment)
    if (
        len(nodes) < 2 or nodes[0].tag != "html" or not nodes[0].attrib
        or any(node.tag != "webctrl" for node in nodes[1:])
        or (fragment.text or "").strip()
        or any(len(node) or (node.text or "").strip() or (node.tail or "").strip() for node in nodes)
    ):
        raise ValueError("Browser actions require a full flat <html ... /><webctrl ... /> selector.")
    for node in nodes:
        node.tail = None
    # Attribute order is immaterial; canonicalize only the scope identity.
    html = ET.Element("html", dict(sorted(nodes[0].attrib.items())))
    return {
        **binding,
        "browser_selector": ET.tostring(html, encoding="unicode"),
        "partial_selector": "".join(ET.tostring(node, encoding="unicode") for node in nodes[1:]),
    }


def group_browser_actions(root, bindings):
    """Scope consecutive actions in each sequence, never across If/Else or guards.

    Exist keeps its full selector outside Attach Browser: an absent browser must
    not become an attachment exception before the Boolean condition is evaluated.
    A click ends a group because it can navigate, open a tab or close the browser.
    """
    for sequence in list(root.iter(q("Sequence"))):
        children = []
        current_key, body = None, None
        for activity in sequence:
            binding = bindings.get(activity)
            if binding is None:
                children.append(activity)
                current_key, body = None, None
                continue
            key = (
                target_key(binding["uft"])[:2], binding["browser_selector"],
                binding["browser_type"], binding["timeout_ms"],
            )
            if key != current_key:
                scope = ET.Element(q("BrowserScope", UI), {
                    "DisplayName": "Attach browser: " + binding["uft"]["browser"],
                    "Selector": binding["browser_selector"],
                    "BrowserType": binding["browser_type"],
                    "TimeoutMS": str(binding["timeout_ms"]),
                    "ContinueOnError": "False",
                })
                prop = ET.SubElement(scope, q("BrowserScope.Body", UI))
                action = ET.SubElement(prop, q("ActivityAction"), {q("TypeArguments", X): "x:Object"})
                argument = ET.SubElement(action, q("ActivityAction.Argument"))
                ET.SubElement(argument, q("DelegateInArgument"), {
                    q("TypeArguments", X): "x:Object", "Name": "ContextTarget",
                })
                body = ET.SubElement(action, q("Sequence"), {"DisplayName": "Browser actions"})
                children.append(scope)
                current_key = key
            body.append(activity)
            if activity.tag == q("Click", UI):
                current_key, body = None, None
        sequence[:] = children
