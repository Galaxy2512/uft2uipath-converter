"""Classic UI activity candidates; unresolved semantics fail before UI actions."""
import json
import re
import xml.etree.ElementTree as ET

WF = "http://schemas.microsoft.com/netfx/2009/xaml/activities"
X = "http://schemas.microsoft.com/winfx/2006/xaml"
UI = "http://schemas.uipath.com/workflow/activities"
for prefix, uri in (("", WF), ("x", X), ("ui", UI)):
    ET.register_namespace(prefix, uri)

TYPES = {"String": "x:String", "Boolean": "x:Boolean", "Int32": "x:Int32"}
# A deliberately restrictive naming contract avoids keyword collisions.
IDENTIFIER = re.compile(r"in_[A-Za-z][A-Za-z0-9_]*\Z")


def q(name, uri=WF):
    return f"{{{uri}}}{name}"


def expr(code):
    return "[" + code + "]"


def literal(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int and -(2**31) <= value < 2**31:
        return str(value)
    raise ValueError("Unsupported literal type or Int32 range.")


def throw(message):
    return ET.Element(q("Throw"), {
        "DisplayName": "Migration blocked",
        "Exception": expr("new System.InvalidOperationException(" + literal(message) + ")"),
    })


def document(name, arguments):
    root = ET.Element(q("Activity"), {q("Class", X): name})
    # Omit the x:Members directive when the workflow has no arguments.
    if arguments:
        members = ET.SubElement(root, q("Members", X))
        for arg, kind in sorted(arguments.items()):
            ET.SubElement(members, q("Property", X), {
                "Name": arg, "Type": f"InArgument({TYPES[kind]})",
            })
    seq = ET.SubElement(root, q("Sequence"), {"DisplayName": name})
    return root, seq


def write_xaml(path, root):
    from uft2uipath.script_generation.studio_xaml import prepare
    root = prepare(root)
    ET.indent(root, space="  ")
    path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def target_key(target):
    return tuple(target.get(key) for key in ("browser", "page", "object_type", "logical_name"))


class ComponentEmitter:
    def __init__(self, component_id, analysis, bindings, workflow_name=None):
        self.component_id = component_id
        self.workflow_name = workflow_name or f"Component_{component_id}"
        self.analysis = analysis
        self.bindings = bindings
        self.arguments = {}
        self.references = {}
        self.objects = {}
        self.issues = []
        self.trace = []
        self.counter = 0
        self.variables = []
        self.scoped_actions = {}
        self._load_bindings()

    def problem(self, node, code, message):
        self.issues.append({
            "code": code, "message": message, "line_number": node.get("line_number"),
            "raw": node.get("raw"), "component_id": self.component_id,
        })

    def _load_bindings(self):
        if not isinstance(self.bindings, dict):
            raise ValueError("Component target bindings must be an object.")
        for category in ("parameters", "environment"):
            entries = self.bindings.get(category, {})
            if not isinstance(entries, dict):
                raise ValueError(f"{category} must be an object.")
            for source_name, arg in entries.items():
                if not isinstance(arg, dict):
                    raise ValueError("Argument definition must be an object.")
                name, kind = arg.get("name"), arg.get("type")
                if (
                    not isinstance(name, str) or not IDENTIFIER.fullmatch(name)
                    or kind not in TYPES or arg.get("direction") != "In"
                ):
                    raise ValueError("Only explicit In arguments named in_<identifier>, with String/Boolean/Int32 types, are supported.")
                if name in self.arguments:
                    raise ValueError(f"Duplicate target argument {name}.")
                self.arguments[name] = kind
                self.references[(category, source_name)] = (name, kind)
        objects = self.bindings.get("objects", [])
        if not isinstance(objects, list):
            raise ValueError("objects must be an array.")
        for obj in objects:
            if not isinstance(obj, dict) or not isinstance(obj.get("uft"), dict):
                raise ValueError("Object binding needs a uft identity.")
            key = target_key(obj["uft"])
            if any(not isinstance(v, str) or not v for v in key) or key in self.objects:
                raise ValueError("Missing or duplicate UFT object identity.")
            self.objects[key] = obj

    def value(self, node, expected):
        if not isinstance(node, dict):
            raise ValueError("Value expression is missing.")
        kind = node.get("node_type")
        if kind == "LiteralValue":
            value = node.get("value")
            actual = "Boolean" if type(value) is bool else "Int32" if type(value) is int else "String" if isinstance(value, str) else None
            if actual != expected:
                raise ValueError(f"Expected {expected}; no implicit conversion from {actual}.")
            return literal(value)
        category = {"ParameterReference": "parameters", "EnvironmentReference": "environment"}.get(kind)
        if category:
            binding = self.references.get((category, node.get("name")))
            if binding is None or binding[1] != expected:
                raise ValueError(f"Missing {expected} binding for {category}:{node.get('name')}.")
            return binding[0]
        raise ValueError("Unsupported expression remains unresolved.")

    def object_binding(self, node, action):
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
            from uft2uipath.script_generation.browser_scopes import browser_target
            binding = browser_target(binding)
        return binding

    def ui_target(self, activity, activity_type, binding, timeout=None, scoped=False):
        prop = ET.SubElement(activity, q(activity_type + ".Target", UI))
        ET.SubElement(prop, q("Target", UI), {
            "Selector": expr(literal(binding["partial_selector"] if scoped else binding["selector"])),
            "TimeoutMS": str(binding["timeout_ms"] if timeout is None else timeout),
            "WaitForReady": "NONE",
        })
        if scoped:
            self.scoped_actions[activity] = binding

    def map_operation(self, node, parent):
        kind = node.get("node_type")
        line = node.get("line_number")
        display = f"UFT line {line}: {kind}"
        trace = {"component_id": self.component_id, "line_number": line,
                 "raw": node.get("raw"), "node_type": kind, "status": "blocked"}
        self.trace.append(trace)
        if kind == "IfOperation":
            self.counter += 1
            variable = f"exists_{self.counter}"
            self.variables.append(variable)
            condition = node.get("condition") or {}
            try:
                if condition.get("node_type") != "ExistCondition":
                    raise ValueError("Only an explicitly parsed Exist condition is supported.")
                binding = self.object_binding(condition, "exists")
                timeout_node = condition.get("timeout") or {}
                seconds = timeout_node.get("value")
                if timeout_node.get("node_type") != "LiteralValue" or type(seconds) is not int or not 0 < seconds <= 2147483:
                    raise ValueError("Exist requires a positive literal timeout in seconds in this version.")
                activity = ET.SubElement(parent, q("UiElementExists", UI), {
                    "DisplayName": display + " / Exists", "Exists": expr(variable), "ContinueOnError": "False",
                })
                self.ui_target(activity, "UiElementExists", binding, seconds * 1000)
                trace.update(status="mapped_unverified", activity="UiElementExists + If")
            except (ValueError, ET.ParseError) as exc:
                self.problem(node, "unresolved_condition", str(exc))
                parent.append(throw(f"Component {self.component_id}, line {line}: unresolved condition."))
            branch = ET.SubElement(parent, q("If"), {"DisplayName": display, "Condition": expr(variable)})
            for field, prop_name in (("then_operations", "If.Then"), ("else_operations", "If.Else")):
                prop = ET.SubElement(branch, q(prop_name))
                body = ET.SubElement(prop, q("Sequence"), {"DisplayName": field})
                for child in node.get(field, []):
                    self.map_operation(child, body)
            return

        try:
            if kind == "ClickOperation":
                binding = self.object_binding(node, "click")
                activity = ET.SubElement(parent, q("Click", UI), {
                    "DisplayName": display, "ContinueOnError": "False",
                    "ClickType": "CLICK_SINGLE", "MouseButton": "BTN_LEFT",
                    "SimulateClick": str(binding["input_method"] == "Simulate").lower(),
                    "SendWindowMessages": str(binding["input_method"] == "SendWindowMessages").lower(),
                })
                self.ui_target(activity, "Click", binding, scoped=True)
                trace.update(status="mapped_unverified", activity="Click")
            elif kind == "SetTextOperation":
                binding = self.object_binding(node, "set")
                text = self.value(node.get("value"), "String")
                activity = ET.SubElement(parent, q("TypeInto", UI), {
                    "DisplayName": display, "Text": expr(text), "EmptyField": "True", "ContinueOnError": "False",
                    "SimulateType": str(binding["input_method"] == "Simulate").lower(),
                    "SendWindowMessages": str(binding["input_method"] == "SendWindowMessages").lower(),
                })
                self.ui_target(activity, "TypeInto", binding, scoped=True)
                trace.update(status="mapped_unverified", activity="TypeInto (replace)")
            else:
                raise ValueError(f"{kind} has no validated semantic mapping; source preserved.")
        except (ValueError, ET.ParseError) as exc:
            self.problem(node, "unsupported_mapping", str(exc))
            parent.append(throw(f"Component {self.component_id}, line {line}: migration incomplete."))

    def generate(self):
        root, seq = document(self.workflow_name, self.arguments)
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
        group_browser_actions(seq, self.scoped_actions)
        if self.variables:
            variables = ET.Element(q("Sequence.Variables"))
            for name in self.variables:
                ET.SubElement(variables, q("Variable"), {q("TypeArguments", X): "x:Boolean", "Name": name})
            seq.insert(0, variables)
        if self.issues:
            index = 1 if self.variables else 0
            seq.insert(index, throw(f"Component {self.component_id}: incomplete migration. Read generation-report.json."))
        return root, {
            "component_id": self.component_id,
            "status": "blocked" if self.issues else "mapped_unverified",
            "arguments": self.arguments, "issues": self.issues, "trace": self.trace,
            "executable_verified": False, "equivalent_verified": False,
        }
