# Manifest to UiPath Studio test project

Run the complete pipeline with one command:

    python -m uft2uipath migrate-project examples/workflow_generation/manifest.json --bindings examples/workflow_generation/target-bindings.json --out output/UFT_Migration_Preview --zip

The command runs source analysis, emits component and test workflows, registers
test files in project metadata, writes Main.xaml and packages a ZIP. Both the
destination directory and ZIP must be new.

Open output/UFT_Migration_Preview/project.json in UiPath Studio. Allow dependency
restoration, open Tests/Test_1.xaml, then Workflows/Component_10.xaml to inspect
If/Else, Element Exists, Type Into and Click. The synthetic fixture is guarded
with Throw and is intended for opening/validation, not live execution.

This is a generated example, not a migration of an unseen production QCP.
For real input supply decoded ALM tables, verified component-to-script mappings,
selectors and argument/call bindings. See SCRIPT_ANALYSIS.md and WORKFLOW_EMISSION.md.

## Project profile

Windows, CSharp, designOptions.outputType=Tests. Test metadata uses
fileInfoCollection entries with testCaseType=TestCase and editingStatus=InProgress.
Expressions are written as explicit CSharpValue/CSharpReference nodes with
implementation namespaces and assembly references.
Workflows without arguments omit x:Members. Empty InvokeWorkflowFile.Arguments
collections are omitted too; argument-bearing workflows retain their typed members.

Classic Click and Type Into activities now use Attach Browser scopes with partial
selectors. The original Exist condition is evaluated before these scopes. Supply
browser_type in each action's object binding; see WORKFLOW_EMISSION.md for grouping
rules and the timing boundary. The fixture explicitly uses Edge, with synthetic
selectors and its execution guard still enabled.

The default dependency baseline is taken from published UiPath examples:
System 23.10.3, Testing 23.10.0, UIAutomation 23.10.7. These are reference versions,
not a claim that they are current or installed on your machine.
For local dependency versions use:

    python -m uft2uipath migrate-project <manifest.json> --bindings <target-bindings.json> --out <new-directory> --project-template <blank-Windows-CSharp-test-project/project.json> --zip

The template must declare all three activity dependencies. Its entry-point and
test-registration metadata is replaced with the generated project's metadata.
Only project.json is read from the template; its source files are not copied.

## Validation boundary

The local checks cover XML serialization, explicit C# expression nodes,
workflow references, registered test paths, package contents, source preservation,
unsupported-operation guards and output protection.
Regression checks cover argumentless XAML, scope boundaries, browser identities,
branch order, and selector attributes/frame paths after splitting.
They do not run UiPath Studio, compile workflows or compare UFT and UiPath outcomes.
studio_load_verified, executable_verified and equivalent_verified remain false.

After generation the next gate is actual Studio load/validation. Report its exact
errors with project.json and a Studio-saved activity example if adaptation is
needed. Do not remove guards to manufacture a passing test.

## Studio validation corrections

The initial preview emitted <x:Members /> for Component_20, which has no
arguments. The System.Xaml scanner classifies a directive as PROPERTYELEMENT even
when it is self-closing. The parser then encounters the next property instead of
an end tag, producing the reported NonemptyPropertyElement error. Omit the unused
directive; do not remove the component or its unresolved-operation guard.

UI-DBP-006 reports consecutive Classic activities repeating top-level selectors.
The generator now places the supplied browser selector on Attach Browser and
uses partial selectors on its contained actions. The rule remains enabled.
Open the regenerated project from a new folder, restore packages and run Studio
Validate Project / Analyze Project again. Python checks do not replace this gate.

## Primary project/XAML references

- https://github.com/UiPath/codedautomations-samples/tree/main/SAP_WinGUI_Coded_Automation_Project
- https://github.com/UiPath/codedautomations-samples/tree/main/CrossXamlInteroperability
- https://github.com/dotnet/wpf/blob/main/src/Microsoft.DotNet.Wpf/src/System.Xaml/System/Xaml/Parser/XamlScanner.cs
- https://github.com/dotnet/wpf/blob/main/src/Microsoft.DotNet.Wpf/src/System.Xaml/System/Xaml/Parser/XamlPullParser.cs
