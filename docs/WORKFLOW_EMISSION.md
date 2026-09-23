# Script AST to workflow candidates

## Scope

This milestone emits workflow XAML using Windows C# expressions and Classic UI
activities. No UiPath Studio/runtime is available in the Python test environment:
XML parsing and mapping tests do not prove XAML compilation or executable
equivalence.

The complete, current list of mappings, their semantics and how to add one is in
[MAPPING_REGISTRY.md](MAPPING_REGISTRY.md). In short, the emitter supports Exist,
Click, Set, SetSecure, Select, Sync, Wait, typed assignments, output parameters,
Reporter.ReportEvent, ExitTest, And/Or/Not/comparison conditions, GetROProperty,
arithmetic and the common VBScript string/number functions.

Unresolved operations, malformed expressions, partial object chains and incomplete
bindings get Throw activities. A component with any blocker has an additional
Throw before its first UI action, even when the blocker is in a conditional branch.
A test that invokes a blocked component is blocked before any component invocation.
These "Migration blocked" Throws signal incomplete migration; ExitTest has its own
mapping (see MAPPING_REGISTRY.md).

Note: this document describes the older manifest-based `emit-workflows` bundle.
That bundle binds In arguments only, so components that report failures, call
ExitTest or write output parameters are blocked there; use `convert`, which
generates the test-level wiring for them. UFT secure-string decoding is not
implemented anywhere: SetSecure takes its value from a secure argument.

## Commands

    python -m uft2uipath analyze-scripts examples/workflow_generation/manifest.json --out output/workflow-analysis
    python -m uft2uipath emit-workflows output/workflow-analysis --bindings examples/workflow_generation/target-bindings.json --out output/workflow-bundle

Expected example result:
- 2 components, 2 tests.
- 2 blocked components, 2 blocked tests.
- Component_10 contains Element Exists, If/Else, Type Into and Click candidates.
- Component_20 contains an unsupported custom operation.
- All fixture workflows have initial Throws because the selectors are synthetic.

The example has fixture_only=true. It may be opened for inspection but is not a
live-application configuration. Do not just flip that flag to execute it.

## Target binding contract

profile must be windows-csharp-classic.
components is indexed by the canonical numeric ALM component ID.
parameters and environment map each source reference name to:
  {"name": "in_User", "type": "String", "direction": "In"}

Target argument names must begin in_ followed by an ASCII letter and then
letters, numbers or underscores. Names must be unique within a component.
There is no arbitrary expression execution from binding configuration.

objects contains exact UFT identities:
  {"uft": {"browser":"B","page":"P","object_type":"WebEdit","logical_name":"User"},
   "selector":"<html ... /><webctrl ... />",
   "accepted_for_generation":true, "verification_status":"accepted_unverified",
   "input_method":"Simulate", "timeout_ms":30000, "browser_type":"Edge"}

accepted_for_generation says the converter may emit this selector, nothing more.
verification_status says how far it was checked (see contracts/selector_state.py):
accepted_unverified, studio_validated or runtime_verified. The converter never
raises that status by itself; only a person who checked the selector in Studio
or in a run may record the stronger values, in the selector review file.
Input methods: Simulate, HardwareEvents, SendWindowMessages.
Selectors must be explicit XML fragments; this version does not generate or
infer them. timeout_ms is required. Exist uses its source timeout instead.
WaitForReady=NONE avoids adding a separate document-ready wait; runtime behavior
still needs validation. The required browser/application must already be open.

Click and Set require an explicit browser_type: IE, Firefox, Chrome, Edge or
Custom. Edge above is an example setting, not a converter default. Missing or
unknown browser types block generation of those actions; no browser is guessed
from a UFT logical object name. Existing target-binding files must add this field.

For these browser actions the supported selector shape is a flat HTML root
followed by one or more webctrl nodes, including frame paths. The generator moves
the supplied HTML root into Attach Browser and keeps the remaining nodes as each
activity's partial selector. It does not invent application or element attributes.
Consecutive actions may share a scope only within the same sequence and with the
same UFT browser/page identity, HTML selector, browser type and attachment timeout.
A Click ends the group so the next action reattaches after possible navigation.
Scope attachment has its own timeout_ms wait in addition to an activity's target
wait; exact end-to-end timing equivalence is not established.

Exist remains outside Attach Browser, with its original full selector and source
timeout. Attaching before Exist would change the missing-browser case into an
attachment exception. Then/Else bodies get their own scopes; no scope is hoisted
across the condition, branches or unresolved-operation guards.

calls is indexed first by TEST ID, then by BPTEST_TO_COMPONENTS.BC_ID:
  {"1": {"7": {"in_User": {"argument":"in_User_ForThisTest","type":"String"}}}}

This explicitly forwards a test-entry argument to a component argument. It does
not invent a fixed value and does not automatically decode ALM parameter datasets.
The caller must supply the actual test input. All defined component arguments
need a call binding, including currently unused definitions. Different component
instances may receive different caller arguments. Original relationship metadata
remains in the bundled analysis.

## Output and Studio verification

- Workflows/Component_<ID>.xaml: one per unique definition.
- Tests/Test_<ID>.xaml: separate entry workflow with ordered component calls.
- generation-report.json: mapped_unverified/blocked status, source-line trace,
  issues and explicit executable_verified=false / equivalent_verified=false.
- target-bindings.json and Data/Analysis: input configuration and source evidence.
- README.md: runtime limitations.

No project.json or dependency versions are guessed. Copy Workflows and Tests
into a separate Windows C# UiPath project with compatible
UiPath.UIAutomation.Activities and UiPath.System.Activities dependencies.
Keep those folder names relative to the project root. Use a separate project
to avoid collisions with existing filenames.

Open the component and test XAML in Studio and run validation before any runtime
test. The fixture's Throw is intentional. Test entries are ordinary workflows,
not automatically registered UiPath Test Explorer cases.

Bring back Studio errors together with the blank project's project.json and
a Studio-saved minimal example containing the relevant activities if adaptation
is necessary. The next gate is Studio load and compilation, not more Python
test counts. Runtime and outcome equivalence remain separate gates.

Existing output directories are rejected. Staging happens before copying;
an I/O failure during the final copy can leave a partial new output directory.

## Primary references

- [Classic Element Exists](https://docs.uipath.com/activities/other/latest/ui-automation/ui-element-exists)
- [Type Into](https://docs.uipath.com/activities/other/latest/ui-automation/type-into)
- [Type Secure Text](https://docs.uipath.com/activities/other/latest/ui-automation/type-secure-text)
- [Throw](https://docs.uipath.com/activities/other/latest/workflow/throw)
- [Container Usage, UI-DBP-006](https://docs.uipath.com/activities/other/latest/ui-automation/ui-dbp-006)
- [Attach Browser](https://docs.uipath.com/activities/other/latest/ui-automation/browser-scope)

## Verification

    python -m pytest -q
    git diff --check

Tests inspect recursive branch shape, expression escaping, typed argument
declarations, source-line traceability, guarded unsupported semantics, missing
bindings, distinct call inputs, fixture protection, CLI generation and output
protection. They do not instantiate UiPath activities or compile C# expressions.
