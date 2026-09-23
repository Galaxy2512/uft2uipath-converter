"""Attach to desktop windows the same way browser actions attach to a browser."""
import xml.etree.ElementTree as ET

from uft2uipath.contracts.targets import target_key
from uft2uipath.script_generation.emitter import UI, X, q


def window_target(binding):
    """Split a desktop selector into its window scope and the control below it."""
    fragment = ET.fromstring("<root>" + binding["selector"] + "</root>")
    nodes = list(fragment)
    if (
        len(nodes) < 2 or nodes[0].tag != "wnd" or not nodes[0].attrib
        or any(node.tag not in ("wnd", "ctrl") for node in nodes[1:])
        or (fragment.text or "").strip()
        or any(len(node) or (node.text or "").strip() or (node.tail or "").strip() for node in nodes)
    ):
        raise ValueError("Desktop actions require a full flat <wnd ... /> selector with a control.")
    for node in nodes:
        node.tail = None
    window = ET.Element("wnd", dict(sorted(nodes[0].attrib.items())))
    return {
        **binding,
        "window_selector": ET.tostring(window, encoding="unicode"),
        "partial_selector": "".join(ET.tostring(node, encoding="unicode") for node in nodes[1:]),
    }


def _window_name(binding) -> str:
    """Display name of the window an action is scoped to."""
    path = binding["uft"].get("path") or []
    return str(path[-2]["name"]) if len(path) > 1 else str(binding["uft"].get("page") or "")


def group_window_actions(root, bindings):
    """Scope consecutive actions on the same window, never across If/Else or guards."""
    for sequence in list(root.iter(q("Sequence"))):
        children = []
        current_key, body = None, None
        for activity in sequence:
            binding = bindings.get(activity)
            if binding is None:
                children.append(activity)
                current_key, body = None, None
                continue
            container = target_key(binding["uft"])[:-1]
            key = (container, binding["window_selector"], binding["timeout_ms"])
            if key != current_key:
                scope = ET.Element(q("WindowScope", UI), {
                    "DisplayName": "Attach window: " + _window_name(binding),
                    "Selector": binding["window_selector"],
                    "TimeoutMS": str(binding["timeout_ms"]),
                    "ContinueOnError": "False",
                })
                prop = ET.SubElement(scope, q("WindowScope.Body", UI))
                action = ET.SubElement(prop, q("ActivityAction"), {q("TypeArguments", X): "x:Object"})
                argument = ET.SubElement(action, q("ActivityAction.Argument"))
                ET.SubElement(argument, q("DelegateInArgument"), {
                    q("TypeArguments", X): "x:Object", "Name": "ContextTarget",
                })
                body = ET.SubElement(action, q("Sequence"), {"DisplayName": "Window actions"})
                children.append(scope)
                current_key = key
            body.append(activity)
        sequence[:] = children
