"""COM objects in variables: Set x = CreateObject(...), Set x = Nothing and their methods.

Only objects whose methods have an exact .NET equivalent are supported; the
object itself then needs no activity at all. Scripting.FileSystemObject is
mapped to System.IO; any other ProgID (WScript.Shell, Excel.Application ...)
or a test object held in a variable blocks with the reason.
"""
import re

from uft2uipath.mapping.operation_registry import maps
from uft2uipath.script_generation.emitter import NonNull

FILE_SYSTEM = "scripting.filesystemobject"
_CREATE = re.compile(r'^CreateObject\s*\(\s*"(?P<progid>[^"]+)"\s*\)$', re.IGNORECASE)


def _s(code):
    return code if isinstance(code, NonNull) else f'({code} ?? "")'


# Method (lower case) -> (argument count, result type, C# template).
FILE_SYSTEM_METHODS = {
    "fileexists": (1, "Boolean", lambda a: f"System.IO.File.Exists({a[0]})"),
    "folderexists": (1, "Boolean", lambda a: f"System.IO.Directory.Exists({a[0]})"),
    "getfilename": (1, "String", lambda a: f"System.IO.Path.GetFileName({_s(a[0])})"),
    "getbasename": (1, "String", lambda a: f"System.IO.Path.GetFileNameWithoutExtension({_s(a[0])})"),
    "getextensionname": (1, "String", lambda a: f"System.IO.Path.GetExtension({_s(a[0])}).TrimStart('.')"),
    "getparentfoldername": (1, "String",
                            lambda a: f'(System.IO.Path.GetDirectoryName({_s(a[0])}) ?? "")'),
    "buildpath": (2, "String", lambda a: f"System.IO.Path.Combine({_s(a[0])}, {_s(a[1])})"),
}


@maps("ObjectAssignmentOperation", uft='Set x = CreateObject("...") / Set x = Nothing', activities=(),
      status="no_effect",
      notes="Scripting.FileSystemObject only: its methods become System.IO calls, so the object "
            "itself needs no activity. Other ProgIDs and test objects in variables block.")
def emit_object_assignment(ctx, node, parent, trace, display):
    """Remember which COM object a variable holds; nothing is emitted for it."""
    name = (node.get("name") or "").casefold()
    expression = (node.get("expression") or "").strip()
    if expression.lower() == "nothing":
        if name not in ctx.com_objects:
            raise ValueError(f"Set {node.get('name')} = Nothing releases an object that is not supported.")
        del ctx.com_objects[name]
        trace.update(status="mapped_unverified", activity="(no effect)", note="Releasing the object needs no activity.")
        return
    match = _CREATE.match(expression)
    if match is None:
        raise ValueError("Object references other than CreateObject are not supported yet.")
    progid = match.group("progid")
    if progid.casefold() != FILE_SYSTEM:
        raise ValueError(f"CreateObject({progid!r}) has no UiPath mapping.")
    ctx.com_objects[name] = FILE_SYSTEM
    trace.update(status="mapped_unverified", activity="(no effect)",
                 note="FileSystemObject methods are translated to System.IO where they are used.")


def _method(ctx, node):
    """(argument count, result type, template) of an object's method, or ValueError with the reason."""
    holder = (node.get("object") or "").casefold()
    if ctx.com_objects.get(holder) != FILE_SYSTEM:
        raise ValueError(f"{node.get('object')} holds no supported object; {node.get('method')} cannot be mapped.")
    method = FILE_SYSTEM_METHODS.get((node.get("method") or "").lower())
    if method is None:
        raise ValueError(f"FileSystemObject.{node.get('method')} has no UiPath mapping.")
    if len(node.get("arguments") or []) != method[0]:
        raise ValueError(f"FileSystemObject.{node.get('method')} takes {method[0]} arguments.")
    return method


@maps("MethodCall", uft="fso.FileExists(path) ...", activities=(), kind="expression",
      typer=lambda ctx, node: _method(ctx, node)[1],
      notes="FileSystemObject: " + ", ".join(sorted(FILE_SYSTEM_METHODS)) + ".")
def emit_method_call(ctx, node, parent):
    """C# System.IO code for a FileSystemObject method."""
    _, kind, template = _method(ctx, node)
    code = template([ctx.value(argument, "String", parent) for argument in node.get("arguments") or []])
    return NonNull(code) if kind == "String" else code
