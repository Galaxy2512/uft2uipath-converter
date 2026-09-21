"""One UFT action -> one UiPath workflow (ComponentEmitter) and the XAML helpers it uses.

How a line is migrated:
1. map_operation looks the parser node up in mapping.operation_registry and
   calls its handler from script_generation.emitters.
2. Handlers ask this class for typed C# values (value, as_string, condition)
   and for verified selector bindings (object_binding, ui_target).
3. Anything that cannot be mapped raises ValueError; the line's activities are
   dropped, a Throw takes its place, and the workflow starts with a Throw too,
   so an incomplete migration can never run as if it were complete.

Currently Classic UI activities are emitted; modern activities are planned
once their XAML has been confirmed in Studio.
"""
import json
import math
import re
import xml.etree.ElementTree as ET

from uft2uipath.mapping.operation_registry import lookup

WF = "http://schemas.microsoft.com/netfx/2009/xaml/activities"
X = "http://schemas.microsoft.com/winfx/2006/xaml"
UI = "http://schemas.uipath.com/workflow/activities"
for prefix, uri in (("", WF), ("x", X), ("ui", UI)):
    ET.register_namespace(prefix, uri)

TYPES = {"String": "x:String", "Boolean": "x:Boolean", "Int32": "x:Int32", "Double": "x:Double",
         "Object": "x:Object"}
# Object only holds activity results internally; arguments stay typed.
ARGUMENT_TYPES = ("String", "Boolean", "Int32")
# A deliberately restrictive naming contract avoids keyword collisions.
IDENTIFIER = re.compile(r"in_[A-Za-z][A-Za-z0-9_]*\Z")
OUT_IDENTIFIER = re.compile(r"out_[A-Za-z][A-Za-z0-9_]*\Z")
IDENTIFIER_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
DIRECTIONS = {"In": "InArgument", "Out": "OutArgument", "InOut": "InOutArgument"}
# Set by Reporter micFail in any action; the calling test fails at its end.
FAILED_FLAG = "io_uft_failed"
# Marks the exception ExitTest raises, so the test can stop without failing.
EXIT_TEST_MARKER = "UFT ExitTest"
# Appended to that message when a failure was reported before the ExitTest.
EXIT_FAILED_SUFFIX = " [failure reported]"
CSHARP_KEYWORDS = frozenset("""
    abstract as base bool break byte case catch char checked class const continue decimal
    default delegate do double else enum event explicit extern false finally fixed float for
    foreach goto if implicit in int interface internal is lock long namespace new null object
    operator out override params private protected public readonly ref return sbyte sealed
    short sizeof stackalloc static string struct switch this throw true try typeof uint ulong
    unchecked unsafe ushort using virtual void volatile while
""".split())


def q(name, uri=WF):
    """Qualified XML name: the local name in the given namespace (workflow namespace by default)."""
    return f"{{{uri}}}{name}"


def expr(code):
    """Mark C# code as an expression; studio_xaml.prepare turns it into CSharpValue/CSharpReference."""
    return "[" + code + "]"


class NonNull(str):
    """C# code for a String that is never null, e.g. a concatenation or ToString()."""


def literal(value):
    """C# literal for a Python str, bool, Int32-range int or finite float."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int and -(2**31) <= value < 2**31:
        return str(value)
    if type(value) is float and math.isfinite(value):
        text = repr(value)
        # A C# double literal needs a decimal point or an exponent.
        return text if any(c in text for c in ".eE") else text + ".0"
    raise ValueError("Unsupported literal type or Int32 range.")


def throw(message, display="Migration blocked", exception="System.InvalidOperationException"):
    """Throw activity raising the given exception type with a fixed message."""
    return ET.Element(q("Throw"), {
        "DisplayName": display,
        "Exception": expr(f"new {exception}(" + literal(message) + ")"),
    })


def assign(parent, display, target, kind, code):
    """Assign the C# expression code to a variable or argument of the given type."""
    element = ET.SubElement(parent, q("Assign"), {"DisplayName": display})
    ET.SubElement(ET.SubElement(element, q("Assign.To")), q("OutArgument"), {
        q("TypeArguments", X): TYPES[kind]}).text = expr(target)
    ET.SubElement(ET.SubElement(element, q("Assign.Value")), q("InArgument"), {
        q("TypeArguments", X): TYPES[kind]}).text = expr(code)
    return element


def document(name, arguments, directions=None):
    """Workflow root; arguments are In unless directions names Out or InOut."""
    root = ET.Element(q("Activity"), {q("Class", X): name})
    # Omit the x:Members directive when the workflow has no arguments.
    if arguments:
        members = ET.SubElement(root, q("Members", X))
        for arg, kind in sorted(arguments.items()):
            direction = DIRECTIONS[(directions or {}).get(arg, "In")]
            ET.SubElement(members, q("Property", X), {
                "Name": arg, "Type": f"{direction}({TYPES[kind]})",
            })
    seq = ET.SubElement(root, q("Sequence"), {"DisplayName": name})
    return root, seq


def write_xaml(path, root):
    """Serialize a workflow as Studio-compatible C# XAML (see studio_xaml.prepare)."""
    from uft2uipath.script_generation.studio_xaml import prepare
    root = prepare(root)
    ET.indent(root, space="  ")
    path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def _secret_source(node):
    """Name of the secure argument a SetSecure step needs: its object's logical name."""
    target = node.get("target") or {}
    return target.get("logical_name") or target.get("object_type") or "value"


def target_key(target):
    """Identity of a UFT object: its hierarchy, however the binding spelled it."""
    path = target.get("path")
    if not path:
        path = [{"class": kind, "name": target.get(name)} for kind, name in
                (("Browser", "browser"), ("Page", "page"))] + [
            {"class": target.get("object_type"), "name": target.get("logical_name")}]
    steps = []
    for step in path:
        kind, name = step.get("class"), step.get("name")
        # A statement on the page repeats it as the target; keep one step for it.
        if kind and name and (kind.casefold(), name.casefold()) not in steps[-1:]:
            steps.append((kind.casefold(), name.casefold()))
    return tuple(steps)


class ComponentEmitter:
    """Turns the parsed operations of one UFT action into one UiPath workflow.

    It owns the per-workflow state the handlers share: arguments and their
    directions, typed variables, object bindings, and the issues and trace that
    end up in generation-report.json. Which activities a line becomes is decided
    by the handlers in script_generation.emitters, found through the registry.
    """
    def __init__(self, component_id, analysis, bindings, workflow_name=None):
        """Load the bindings (arguments and selectors) the workflow may use; nothing is emitted yet."""
        self.component_id = component_id
        self.workflow_name = workflow_name or f"Component_{component_id}"
        self.analysis = analysis
        self.bindings = bindings
        self.arguments = {}
        # Only Out and InOut arguments are listed; the rest are In.
        self.directions = {}
        self.exits_test = False
        self.references = {}
        self.objects = {}
        self.issues = []
        self.trace = []
        self.counter = 0
        self.variables = []
        self.typed_variables = {}
        self.assigned = set()
        self.scoped_actions = {}
        self._load_bindings()

    def problem(self, node, code, message):
        """Record a blocker for the report; the workflow then starts with a Throw."""
        self.issues.append({
            "code": code, "message": message, "line_number": node.get("line_number"),
            "raw": node.get("raw"), "component_id": self.component_id,
        })

    def _load_bindings(self):
        """Validate and index the bindings: In arguments per parameter, environment,
        data and secure value, Out arguments for output parameters, and the
        selector of each UFT object identity.
        """
        if not isinstance(self.bindings, dict):
            raise ValueError("Component target bindings must be an object.")
        for category in ("parameters", "environment", "data", "secure"):
            entries = self.bindings.get(category, {})
            if not isinstance(entries, dict):
                raise ValueError(f"{category} must be an object.")
            for source_name, arg in entries.items():
                if not isinstance(arg, dict):
                    raise ValueError("Argument definition must be an object.")
                name, kind = arg.get("name"), arg.get("type")
                if (
                    not isinstance(name, str) or not IDENTIFIER.fullmatch(name)
                    or kind not in ARGUMENT_TYPES or arg.get("direction") != "In"
                ):
                    raise ValueError("Only explicit In arguments named in_<identifier>, with String/Boolean/Int32 types, are supported.")
                if name in self.arguments:
                    raise ValueError(f"Duplicate target argument {name}.")
                self.arguments[name] = kind
                self.references[(category, source_name)] = (name, kind)
        outputs = self.bindings.get("outputs", {})
        if not isinstance(outputs, dict):
            raise ValueError("outputs must be an object.")
        for source_name, arg in outputs.items():
            if not isinstance(arg, dict):
                raise ValueError("Argument definition must be an object.")
            name, kind = arg.get("name"), arg.get("type")
            if (
                not isinstance(name, str) or not OUT_IDENTIFIER.fullmatch(name)
                or kind not in ARGUMENT_TYPES or arg.get("direction") != "Out"
            ):
                raise ValueError("Output parameters must be Out arguments named out_<identifier>, with String/Boolean/Int32 types.")
            if name in self.arguments:
                raise ValueError(f"Duplicate target argument {name}.")
            self.arguments[name] = kind
            self.directions[name] = "Out"
            self.references[("outputs", source_name)] = (name, kind)
            # UFT reads an output parameter as its current value.
            self.references.setdefault(("parameters", source_name), (name, kind))
        objects = self.bindings.get("objects", [])
        if not isinstance(objects, list):
            raise ValueError("objects must be an array.")
        for obj in objects:
            if not isinstance(obj, dict) or not isinstance(obj.get("uft"), dict):
                raise ValueError("Object binding needs a uft identity.")
            key = target_key(obj["uft"])
            if not key or key in self.objects:
                raise ValueError("Missing or duplicate UFT object identity.")
            self.objects[key] = obj

    def failure_flag(self):
        """The InOut Boolean a reported failure sets; the calling test checks it."""
        self.arguments[FAILED_FLAG] = "Boolean"
        self.directions[FAILED_FLAG] = "InOut"
        return FAILED_FLAG

    def expression_type(self, node):
        """Static type of a value expression; raises with the reason when it is unknown."""
        if not isinstance(node, dict):
            raise ValueError("Value expression is missing.")
        kind = node.get("node_type")
        if kind == "LiteralValue":
            value = node.get("value")
            actual = ("Boolean" if type(value) is bool else "Int32" if type(value) is int
                      else "Double" if type(value) is float else "String" if isinstance(value, str) else None)
            if actual is None:
                raise ValueError("Unsupported literal value.")
            return actual
        category = {"ParameterReference": "parameters", "EnvironmentReference": "environment",
                    "DataTableReference": "data"}.get(kind)
        if category:
            source = node.get("column") if category == "data" else node.get("name")
            binding = self.references.get((category, source))
            if binding is None:
                raise ValueError(f"Missing binding for {category}:{source}.")
            return binding[1]
        if kind == "ConcatenationExpression":
            return "String"
        if kind == "VariableReference":
            kinds = {kind for name, kind in self.assigned if name == node.get("name")}
            if len(kinds) != 1:
                raise ValueError(f"{node.get('name')} is not assigned earlier in this action.")
            return kinds.pop()
        entry = lookup(kind)
        if entry is not None and entry.kind == "expression" and entry.handler is not None:
            return entry.typer(self, node) if entry.typer else entry.returns
        raise ValueError("Unsupported expression remains unresolved.")

    def value_type(self, node):
        """Static type of a value expression, or None when it cannot be known."""
        try:
            return self.expression_type(node)
        except ValueError:
            return None

    def function_origin(self, name):
        """Where a non-built-in function is defined: its library, this action, or None."""
        library = (self.analysis.get("library_functions") or {}).get(name.casefold())
        if library:
            return f"library {library}"
        local = {(op.get("name") or "").casefold() for op in self.analysis.get("operations") or []
                 if isinstance(op, dict) and op.get("node_type") == "FunctionDefinitionOperation"}
        return "this action" if name.casefold() in local else None

    def temporary(self, prefix, kind):
        """A new workflow variable for an intermediate result."""
        self.counter += 1
        name = f"{prefix}_{self.counter}"
        self.typed_variables[name] = kind
        return name

    def condition(self, node, parent, display):
        """C# Boolean code for an If condition; activities it needs go to parent first."""
        if not isinstance(node, dict):
            raise ValueError("Condition is missing.")
        entry = lookup(node.get("node_type"))
        if entry is not None and entry.kind == "condition" and entry.handler is not None:
            return entry.handler(self, node, parent, display)
        if entry is None or entry.kind == "expression":
            # A plain value used as a condition must be Boolean, as VBScript would test it.
            return self.value(node, "Boolean", parent)
        raise ValueError(f"{node.get('node_type')} is not a supported condition.")

    def value(self, node, expected, parent=None):
        """C# code for a value of the expected type.

        Values that need an activity first, e.g. reading a property, emit it
        into parent. Only conversions VBScript and C# agree on are implicit.
        """
        actual = self.expression_type(node)
        code = self._code(node, actual, parent)
        if actual == expected:
            return code
        if expected == "Double" and actual == "Int32":
            return f"(double)({code})"
        raise ValueError(f"Expected {expected}; no implicit conversion from {actual}.")

    def as_string(self, node, parent=None):
        """C# String code for a value, converted as VBScript converts it in & and CStr."""
        kind = self.expression_type(node)
        code = self._code(node, kind, parent)
        if kind == "String":
            return code
        # Boolean prints True/False in both; numbers use the current culture in both.
        return NonNull(f"({code}).ToString()")

    def _code(self, node, kind, parent):
        """C# code of a value already known to have the given type."""
        node_type = node.get("node_type")
        if node_type == "LiteralValue":
            return literal(node.get("value"))
        category = {"ParameterReference": "parameters", "EnvironmentReference": "environment",
                    "DataTableReference": "data"}.get(node_type)
        if category:
            source = node.get("column") if category == "data" else node.get("name")
            return self.references[(category, source)][0]
        if node_type == "ConcatenationExpression":
            # C# concatenation turns null into "", as VBScript does with Empty.
            return NonNull(" + ".join(self.as_string(part, parent) for part in node.get("parts", [])))
        if node_type == "VariableReference":
            return node.get("name")
        return lookup(node_type).handler(self, node, parent)

    def object_binding(self, node, action):
        """Verified selector binding of the object a node acts on.

        Actions (anything but an existence check or a read) also need an input
        method and are split into a browser/window scope plus a partial selector.
        """
        target = node.get("target")
        if not isinstance(target, dict):
            raise ValueError("Missing object target.")
        binding = self.objects.get(target_key(target))
        if binding is None:
            raise ValueError("No exact object-identity binding.")
        selector = binding.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError("Explicit selector required.")
        # Syntax check only; matching the live UI must be verified in Studio.
        ET.fromstring("<root>" + selector + "</root>")
        if binding.get("verified") is not True:
            raise ValueError("Object binding must be explicitly marked verified.")
        timeout = binding.get("timeout_ms")
        if type(timeout) is not int or not 0 < timeout < 2**31:
            raise ValueError("Positive Int32 timeout_ms required.")
        if action != "exists" and binding.get("input_method") not in {"Simulate", "HardwareEvents", "SendWindowMessages"}:
            raise ValueError("Explicit input_method required.")
        if action != "exists":
            if binding.get("kind") == "desktop":
                from uft2uipath.script_generation.window_scopes import window_target
                binding = window_target(binding)
            else:
                from uft2uipath.script_generation.browser_scopes import browser_target
                binding = browser_target(binding)
        return binding

    def ui_target(self, activity, activity_type, binding, timeout=None, scoped=False):
        """Add the Target (selector and timeout) of a UI activity; scoped targets use the partial selector."""
        prop = ET.SubElement(activity, q(activity_type + ".Target", UI))
        ET.SubElement(prop, q("Target", UI), {
            "Selector": expr(literal(binding["partial_selector"] if scoped else binding["selector"])),
            "TimeoutMS": str(binding["timeout_ms"] if timeout is None else timeout),
            "WaitForReady": "NONE",
        })
        if scoped:
            self.scoped_actions[activity] = binding

    def map_operation(self, node, parent):
        """Emit one parsed operation into parent and record its trace entry.

        The registry names the handler; if there is none, or it raises, everything
        the line emitted is removed and a Throw marks the line as not migrated.
        """
        kind = node.get("node_type")
        line = node.get("line_number")
        display = f"UFT line {line}: {kind}"
        trace = {"component_id": self.component_id, "line_number": line,
                 "raw": node.get("raw"), "node_type": kind, "status": "blocked"}
        self.trace.append(trace)
        # Handlers live in script_generation.emitters; the registry says which applies.
        entry = lookup(kind)
        start = len(parent)
        try:
            if entry is None or entry.handler is None or entry.kind != "operation":
                raise ValueError(f"{kind} has no validated semantic mapping; source preserved.")
            entry.handler(self, node, parent, trace, display)
        except (ValueError, ET.ParseError) as exc:
            # Drop activities the line emitted before it failed, e.g. a property read.
            del parent[start:]
            self.problem(node, "unsupported_mapping", str(exc))
            parent.append(throw(f"Component {self.component_id}, line {line}: migration incomplete."))

    def generate(self):
        # The root is built last: mapping can add arguments, e.g. the failure flag.
        """Emit the whole workflow and its report.

        Order: parser-level blockers, every operation, browser/window scopes, then
        variables and arguments, because mapping can still add them (e.g. the
        failure flag). Any issue puts a Throw before the first activity.
        """
        seq = ET.Element(q("Sequence"), {"DisplayName": self.workflow_name})
        operations = self.analysis.get("operations")
        if not isinstance(operations, list) or not operations:
            self.problem({}, "no_operations", "No parsed script operations available.")
            operations = []
        # Parser-level ambiguities are never cleared by adding a selector.
        for issue in self.analysis.get("issues", []):
            if issue.get("code") in {"unsupported_object_chain", "unsupported_statement", "unsupported_expression", "script_analysis_error", "missing_binding"}:
                self.problem(issue, issue["code"], issue.get("message", "Unresolved analysis issue."))
        for node in operations:
            self.map_operation(node, seq)
        from uft2uipath.script_generation.browser_scopes import group_browser_actions
        from uft2uipath.script_generation.window_scopes import group_window_actions
        scoped = self.scoped_actions
        group_browser_actions(seq, {a: b for a, b in scoped.items() if b.get("kind") != "desktop"})
        group_window_actions(seq, {a: b for a, b in scoped.items() if b.get("kind") == "desktop"})
        if self.typed_variables:
            variables = ET.Element(q("Sequence.Variables"))
            for name, kind in self.typed_variables.items():
                ET.SubElement(variables, q("Variable"), {q("TypeArguments", X): TYPES[kind], "Name": name})
            seq.insert(0, variables)
        if self.issues:
            index = 1 if self.typed_variables else 0
            seq.insert(index, throw(f"Component {self.component_id}: incomplete migration. Read generation-report.json."))
        root, placeholder = document(self.workflow_name, self.arguments, self.directions)
        root[list(root).index(placeholder)] = seq
        report = {
            "component_id": self.component_id,
            "status": "blocked" if self.issues else "mapped_unverified",
            "arguments": self.arguments, "issues": self.issues, "trace": self.trace,
            "executable_verified": False, "equivalent_verified": False,
        }
        if self.directions:
            report["argument_directions"] = dict(self.directions)
        if self.exits_test:
            report["exits_test"] = True
        return root, report
