"""System operations outside the application under test: starting programs."""
import xml.etree.ElementTree as ET

from uft2uipath.script_generation.emitter import UI, expr, q
from uft2uipath.script_generation.handlers import emits


# SystemUtil.Run operations Start Process reproduces: "open" is the default verb.
_OPEN = {"", "open"}


@emits("RunApplicationOperation")
def emit_start_process(ctx, node, parent, trace, display):
    """SystemUtil.Run: Start Process with the file, its parameters and working directory.

    Other operations ("print", "edit" ...) need the shell and block; a window mode
    (maximized, hidden ...) is not reproduced and is noted in the report.
    """
    operation = node.get("operation")
    if operation is not None:
        if operation.get("node_type") != "LiteralValue" or str(operation.get("value")).lower() not in _OPEN:
            raise ValueError(f"SystemUtil.Run operation {operation.get('raw')!r} is not supported; only open.")
    attributes = {"DisplayName": display, "FileName": expr(ctx.value(node.get("file"), "String", parent)),
                  "ContinueOnError": "False"}
    for field, attribute in (("parameters", "Arguments"), ("directory", "WorkingDirectory")):
        if node.get(field) is not None:
            attributes[attribute] = expr(ctx.value(node[field], "String", parent))
    ET.SubElement(parent, q("StartProcess", UI), attributes)
    trace.update(status="mapped_unverified", activity="StartProcess")
    if node.get("mode") is not None:
        trace["note"] = f"Window mode {node['mode'].get('raw')} is not reproduced."
