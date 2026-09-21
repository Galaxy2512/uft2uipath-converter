"""Serialize explicit C# expression nodes, matching UiPath Studio C# XAML."""
from copy import deepcopy
import json
import xml.etree.ElementTree as ET

from uft2uipath.script_generation.emitter import WF, X, UI, q

S = "clr-namespace:System;assembly=System.Private.CoreLib"
SCO = "clr-namespace:System.Collections.ObjectModel;assembly=System.Private.CoreLib"
SAP = "http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
for prefix, uri in (("s", S), ("sco", SCO), ("sap2010", SAP), ("mc", MC)):
    ET.register_namespace(prefix, uri)


def prepare(root):
    root = deepcopy(root)
    root.set(q("ExpressionActivityEditor.ExpressionActivityEditor", SAP), "C#")
    root.set(q("Ignorable", MC), "sap2010")
    # s is used in XAML type strings, invisible to ElementTree's QName collector.
    root.set("xmlns:s", S)
    for element in list(root.iter()):
        local = element.tag.split("}")[-1]
        ns = element.tag.split("}")[0][1:] if "}" in element.tag else WF
        if local == "Target" and "Selector" in element.attrib:
            selector = element.attrib["Selector"]
            if selector.startswith("[") and selector.endswith("]"):
                element.set("Selector", json.loads(selector[1:-1]))
        mappings = {
            "Throw": ("Exception", "s:Exception", False),
            "If": ("Condition", "x:Boolean", False),
            "UiElementExists": ("Exists", "x:Boolean", True),
            "TypeInto": ("Text", "x:String", False),
            "Delay": ("Duration", "s:TimeSpan", False),
            "SelectItem": ("Item", "x:String", False),
            "LogMessage": ("Message", "x:String", False),
        }
        if local in mappings:
            attribute, kind, output = mappings[local]
            value = element.attrib.get(attribute)
            if value is not None and value.startswith("[") and value.endswith("]"):
                del element.attrib[attribute]
                prop = ET.Element(q(local + "." + attribute, ns))
                argument = ET.SubElement(prop, q("OutArgument" if output else "InArgument"),
                                         {q("TypeArguments", X): kind})
                ET.SubElement(argument, q("CSharpReference" if output else "CSharpValue"),
                              {q("TypeArguments", X): kind}).text = value[1:-1]
                element.insert(0, prop)
        if local in {"InArgument", "OutArgument", "InOutArgument"} and element.text and element.text.startswith("[") and element.text.endswith("]"):
            code, element.text = element.text[1:-1], None
            ET.SubElement(
                element,
                q("CSharpValue" if local == "InArgument" else "CSharpReference"),
                {q("TypeArguments", X): element.attrib[q("TypeArguments", X)]},
            ).text = code
    namespaces = ET.Element(q("TextExpression.NamespacesForImplementation"))
    collection = ET.SubElement(namespaces, q("Collection", SCO), {q("TypeArguments", X): "x:String"})
    for value in ("System", "System.Activities", "System.Activities.Statements",
                  "System.Activities.Expressions", "UiPath.Core", "UiPath.Core.Activities"):
        ET.SubElement(collection, q("String", X)).text = value
    references = ET.Element(q("TextExpression.ReferencesForImplementation"))
    collection = ET.SubElement(references, q("Collection", SCO), {q("TypeArguments", X): "AssemblyReference"})
    for value in ("Microsoft.CSharp", "System.Activities", "System.Private.CoreLib",
                  "System.Runtime", "UiPath.System.Activities", "UiPath.UiAutomation.Activities"):
        ET.SubElement(collection, q("AssemblyReference")).text = value
    position = 1 if len(root) and root[0].tag == q("Members", X) else 0
    root.insert(position, namespaces)
    root.insert(position + 1, references)
    return root
