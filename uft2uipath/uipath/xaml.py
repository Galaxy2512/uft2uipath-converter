from __future__ import annotations
import html, re
from uft2uipath.model.ast import Component, TestCase, OperationType

def safe_class(name: str) -> str:
    return re.sub(r"\W+", "_", name).strip("_")

def xaml_header(xclass: str) -> str:
    return f'''<Activity mc:Ignorable="sap sap2010" x:Class="{safe_class(xclass)}" xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:p="http://schemas.microsoft.com/netfx/2009/xaml/activities" xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation" xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation" xmlns:scg="clr-namespace:System.Collections.Generic;assembly=System.Private.CoreLib" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <TextExpression.NamespacesForImplementation>
    <scg:List x:TypeArguments="x:String" Capacity="8"><x:String>System</x:String><x:String>System.Collections.Generic</x:String><x:String>System.Data</x:String><x:String>System.Linq</x:String></scg:List>
  </TextExpression.NamespacesForImplementation>
  <TextExpression.ReferencesForImplementation>
    <scg:List x:TypeArguments="AssemblyReference" Capacity="8"><AssemblyReference>System.Private.CoreLib</AssemblyReference><AssemblyReference>System.Data.Common</AssemblyReference><AssemblyReference>System.Linq</AssemblyReference></scg:List>
  </TextExpression.ReferencesForImplementation>'''

def write_line(text: str, display: str = "Migration step") -> str:
    return f'    <p:WriteLine DisplayName="{html.escape(display)}" Text="{html.escape(text)}" />'

def operation_lines(component: Component) -> list[str]:
    lines = []
    for op in component.operations:
        if op.type == OperationType.BROWSER_START:
            lines.append(write_line(f"TODO native activity: Use Application/Browser | Browser={op.properties.get('browser','Edge')} | URL={op.properties.get('url','about:blank')}", "Browser Start"))
        elif op.type == OperationType.BROWSER_NAVIGATE:
            lines.append(write_line(f"TODO native activity: Navigate To | URL={op.properties.get('url','')}", "Navigate"))
        elif op.type == OperationType.BROWSER_CLOSE:
            lines.append(write_line("TODO native activity: Close Tab / Close Application", "Browser Close"))
        elif op.type == OperationType.READ_EXCEL:
            lines.append(write_line(f"TODO native activity: Read Range Workbook | File={op.properties.get('file','Data')}", "Read Excel"))
        elif op.type == OperationType.LOGIN:
            lines.append(write_line("TODO native activities: Get Credential assets + Type Into username/password + Click Login", "Login"))
        elif op.type == OperationType.SELECT:
            lines.append(write_line("TODO native activity: Select Item. Requires Object Repository mapping.", "Select"))
        elif op.type == OperationType.CLICK:
            lines.append(write_line("TODO native activity: Click. Requires selector/Object Repository mapping.", "Click"))
        elif op.type == OperationType.TYPE_INTO:
            lines.append(write_line("TODO native activity: Type Into. Requires selector/Object Repository mapping.", "Type Into"))
        elif op.type in (OperationType.CHECK_WEBSITE, OperationType.VERIFY):
            lines.append(write_line("TODO native activity: Check App State / Verify Expression. Requires expected state mapping.", "Verify"))
        elif op.type == OperationType.CONDITION:
            lines.append(write_line("TODO native activity: If. Original condition must be parsed from BPT/VBScript source.", "Condition"))
        elif op.type == OperationType.LOOP:
            lines.append(write_line("TODO native activity: For Each / While. Original loop must be parsed from BPT/VBScript source.", "Loop"))
        elif op.type == OperationType.CUSTOM_CODE:
            lines.append(write_line("TODO manual review: custom VBScript function/sub found.", "Custom Code"))
        else:
            lines.append(write_line(f"Unsupported UFT operation: {op.name}", "Unmapped"))
    return lines or [write_line(f"No operation mapped for {component.name}")]

def component_xaml(component: Component) -> str:
    lines = "\n".join(operation_lines(component))
    return f'''{xaml_header('TestCases_Components_' + component.name)}
  <Sequence DisplayName="{html.escape(component.name)}">
{lines}
  </Sequence>
</Activity>
'''

def test_xaml(test: TestCase) -> str:
    invokes = [write_line(f"Starting migrated BPT test: {test.name}", "Test start")]
    for c in test.component_names:
        invokes.append(f'    <p:InvokeWorkflowFile DisplayName="{html.escape(c)}" WorkflowFileName="TestCases\\Components\\{html.escape(c)}.xaml" />')
    invokes.append(write_line(f"Finished migrated BPT test: {test.name}", "Test end"))
    return f'''{xaml_header('TestCases_' + test.name)}
  <Sequence DisplayName="{html.escape(test.name)}">
{chr(10).join(invokes)}
  </Sequence>
</Activity>
'''
