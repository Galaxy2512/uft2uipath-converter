"""UI automation: actions and checks on objects bound to an explicit selector."""
import xml.etree.ElementTree as ET

from uft2uipath.mapping.operation_registry import maps
from uft2uipath.script_generation.emitter import UI, X, _secret_source, expr, q


def _input_flag(binding, method):
    return str(binding["input_method"] == method).lower()


@maps("ExistCondition", uft=".Exist(n)", activities=("UiElementExists",), requires_selector=True,
      kind="condition", notes="Timeout must be a positive literal number of seconds.")
def emit_exists(ctx, condition, parent, display):
    variable = ctx.temporary("exists", "Boolean")
    binding = ctx.object_binding(condition, "exists")
    timeout_node = condition.get("timeout") or {}
    seconds = timeout_node.get("value")
    if timeout_node.get("node_type") != "LiteralValue" or type(seconds) is not int or not 0 < seconds <= 2147483:
        raise ValueError("Exist requires a positive literal timeout in seconds in this version.")
    activity = ET.SubElement(parent, q("UiElementExists", UI), {
        "DisplayName": display + " / Exists", "Exists": expr(variable), "ContinueOnError": "False",
    })
    ctx.ui_target(activity, "UiElementExists", binding, seconds * 1000)
    return variable


# UFT run-time property -> UiPath attribute. Web properties read the same DOM
# value under the same name; only these are mapped until more are verified.
PROPERTY_ATTRIBUTES = {
    **{name: name for name in ("innertext", "outertext", "innerhtml", "outerhtml", "value",
                               "href", "title", "name", "class", "url", "src", "alt", "text")},
    "html id": "id", "html tag": "tag",
}


@maps("ObjectPropertyReference", uft='.GetROProperty("property")', activities=("GetAttribute",),
      requires_selector=True, kind="expression", returns="String",
      notes="Read with the full selector, outside any browser scope. The attribute is converted "
            "to String, as GetROProperty's value is compared in UFT.")
def emit_get_attribute(ctx, node, parent):
    if parent is None:
        raise ValueError("GetROProperty needs a Get Attribute activity before this statement; not supported here.")
    prop = (node.get("property") or "").strip().lower()
    attribute = PROPERTY_ATTRIBUTES.get(prop)
    if attribute is None:
        raise ValueError(f"No verified UiPath attribute for UFT property {node.get('property')!r}.")
    binding = ctx.object_binding(node, "exists")
    variable = ctx.temporary("property", "Object")
    activity = ET.SubElement(parent, q("GetAttribute", UI), {
        "DisplayName": f"{node.get('property')} of {binding['uft'].get('logical_name') or 'object'}",
        "Attribute": attribute, "ContinueOnError": "False",
    })
    result = ET.SubElement(activity, q("GetAttribute.Result", UI))
    ET.SubElement(result, q("OutArgument"), {q("TypeArguments", X): "x:Object"}).text = expr(variable)
    ctx.ui_target(activity, "GetAttribute", binding)
    return f"System.Convert.ToString({variable})"


@maps("ClickOperation", uft=".Click", activities=("Click",), requires_selector=True,
      notes="A recorded click offset is not reproduced.")
def emit_click(ctx, node, parent, trace, display):
    binding = ctx.object_binding(node, "click")
    activity = ET.SubElement(parent, q("Click", UI), {
        "DisplayName": display, "ContinueOnError": "False",
        "ClickType": "CLICK_SINGLE", "MouseButton": "BTN_LEFT",
        "SimulateClick": _input_flag(binding, "Simulate"),
        "SendWindowMessages": _input_flag(binding, "SendWindowMessages"),
    })
    ctx.ui_target(activity, "Click", binding, scoped=True)
    trace.update(status="mapped_unverified", activity="Click")
    if node.get("x") is not None:
        trace["note"] = (f"Recorded offset ({node['x']}, {node['y']}) is not reproduced; "
                         "the element is clicked at its centre.")


@maps("SetTextOperation", uft=".Set", activities=("TypeInto",), requires_selector=True)
def emit_type_into(ctx, node, parent, trace, display):
    binding = ctx.object_binding(node, "set")
    text = ctx.value(node.get("value"), "String", parent)
    activity = ET.SubElement(parent, q("TypeInto", UI), {
        "DisplayName": display, "Text": expr(text), "EmptyField": "True", "ContinueOnError": "False",
        "SimulateType": _input_flag(binding, "Simulate"),
        "SendWindowMessages": _input_flag(binding, "SendWindowMessages"),
    })
    ctx.ui_target(activity, "TypeInto", binding, scoped=True)
    trace.update(status="mapped_unverified", activity="TypeInto (replace)")


@maps("SetSecureTextOperation", uft=".SetSecure", activities=("TypeInto",), requires_selector=True,
      notes="The UFT encoded value is not carried over; a secure argument supplies it.")
def emit_secure_type_into(ctx, node, parent, trace, display):
    binding = ctx.object_binding(node, "set")
    secret = ctx.references.get(("secure", _secret_source(node)))
    if secret is None or secret[1] != "String":
        raise ValueError(
            f"SetSecure needs a String argument bound for {_secret_source(node)!r}; "
            "the UFT encoded value cannot be decoded."
        )
    activity = ET.SubElement(parent, q("TypeInto", UI), {
        "DisplayName": display, "Text": expr(secret[0]), "EmptyField": "True",
        "ContinueOnError": "False",
        "SimulateType": _input_flag(binding, "Simulate"),
        "SendWindowMessages": _input_flag(binding, "SendWindowMessages"),
    })
    ctx.ui_target(activity, "TypeInto", binding, scoped=True)
    trace.update(status="mapped_unverified", activity="TypeInto (secure)",
                 note="The UFT encoded value is not carried over; the argument supplies it.")


@maps("SelectOperation", uft=".Select", activities=("SelectItem",), requires_selector=True)
def emit_select_item(ctx, node, parent, trace, display):
    binding = ctx.object_binding(node, "select")
    item = ctx.value(node.get("value"), "String", parent)
    activity = ET.SubElement(parent, q("SelectItem", UI), {
        "DisplayName": display, "Item": expr(item), "ContinueOnError": "False",
    })
    ctx.ui_target(activity, "SelectItem", binding, scoped=True)
    trace.update(status="mapped_unverified", activity="SelectItem")


@maps("SyncOperation", uft=".Sync", activities=("WaitUiElementAppear",), requires_selector=True,
      notes="Sync waits for load completion; waiting for the page element is close, not identical.")
def emit_sync(ctx, node, parent, trace, display):
    binding = ctx.object_binding(node, "exists")
    activity = ET.SubElement(parent, q("WaitUiElementAppear", UI), {
        "DisplayName": display + " / wait for page", "ContinueOnError": "False",
    })
    ctx.ui_target(activity, "WaitUiElementAppear", binding)
    trace.update(status="mapped_unverified", activity="WaitUiElementAppear",
                 note="Sync approximated by waiting for the page selector.")
