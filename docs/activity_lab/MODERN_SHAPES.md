# Modern activities: the properties, read from the UiPath assemblies

Modern (Next) activities are the migration target. The Studio clipboard samples
in this folder show the shape of a card and of `NClick` / `NTypeInto`, but none
of them was indicated on an element, so they do not show how a target is
written. The rest is read from UiPath's own assemblies in the local NuGet cache
(`UiPath.UIAutomationNext.Activities.dll`, `UiPath.UIAutomationNext.dll`,
version 26.10.1) with:

```powershell
python tools\read_activity_metadata.py NClick NTypeInto NApplicationCard TargetAnchorable TargetApp
python tools\read_activity_metadata.py --enums NClickType NChildInteractionMode NWaitForReady
```

That gives property names and types, which is fact, not guesswork. What Studio
actually writes for an indicated element is still open (see the end).

## What the converter has to fill in

| What the converter knows | Modern property | Type |
|---|---|---|
| full selector of an element | `Target/@FullSelector` | `String` |
| selector below the application scope | `Target/@PartialSelector` | `String` |
| selector of the browser or window | `TargetApp/@Selector` | `InArgument<String>` |
| browser type (`Edge`, `Chrome`, ...) | `TargetApp/@BrowserType` | `NBrowserType` |
| timeout | `Timeout` on the activity | `InArgument<Double>`, **seconds** |
| input method | `InteractionMode` on the activity | `NChildInteractionMode` |
| text to type | `NTypeInto/@Text` | `InArgument<String>` |
| clear the field first (UFT `Set`) | `EmptyFieldMode` = `SingleLine` | `NEmptyFieldMode` |
| keep the field (UFT `Type`) | `EmptyFieldMode` = `None` | `NEmptyFieldMode` |

Classic wrote `TimeoutMS` in milliseconds and `SimulateClick` / `SendWindowMessages`
as Booleans; modern has one `Timeout` in seconds and one `InteractionMode`, so
the binding's `timeout_ms` is divided by 1000 and its `input_method` becomes:

| UFT / binding | `NChildInteractionMode` |
|---|---|
| `Simulate` | `Simulate` |
| `HardwareEvents` | `HardwareEvents` |
| `SendWindowMessages` | `WindowMessages` |
| (not set) | `SameAsCard` |

## Enum values (from the assemblies)

| Enum | Members |
|---|---|
| `NClickType` | Single, Double, Down, Up |
| `NMouseButton` | Left, Right, Middle |
| `NKeyModifiers` | None, Alt, Ctrl, Shift, Win |
| `NClickMode` (click before typing) | None, Single, Double |
| `NEmptyFieldMode` | None, SingleLine, MultiLine |
| `NChildInteractionMode` (per activity) | SameAsCard, HardwareEvents, Simulate, DebuggerApi, WindowMessages |
| `NInteractionMode` (on the card) | HardwareEvents, Simulate, DebuggerApi, WindowMessages, Background |
| `NWaitForReady` | None, Interactive, Complete |
| `NBrowserType` | None, IE, Firefox, Chrome, Edge, Custom, WebWidgetNative, Safari |
| `NAppAttachMode` | ByProcessName, ByInstance, SingleWindow |
| `NActivityVersion` / `NTargetVersion` | None, V1 … V5 (V6 for targets), Latest |
| `NApplicationCardVersion` | None, V1, V2, Latest |

The samples show which values Studio writes today: card `Version="V2"`,
`AttachMode="ByInstance"`, activities `Version="V3"`, `ClickType="Single"`,
`MouseButton="Left"`, `KeyModifiers="None"`, `ActivateBefore="True"`,
`ClickBeforeMode="Single"`, `EmptyFieldMode="SingleLine"`.

## Activity names

| UFT | Modern activity | In the assemblies |
|---|---|---|
| `Browser`/`Page` scope, `Window` | `uix:NApplicationCard` | yes |
| `.Click` | `uix:NClick` | yes |
| `.Set`, `.Type` | `uix:NTypeInto` | yes |
| `.Select` | `uix:NSelectItem` | yes |
| `CheckBox.Set "ON"/"OFF"` | `uix:NCheckState` | yes |
| `.GetROProperty` | `uix:NGetAttribute`, `uix:NGetText` | yes |
| `Browser.Navigate` | `uix:NGoToUrl` | yes |
| `.Exist`, `.Sync` | *check app state* | name not confirmed yet |

Namespace: `xmlns:uix="http://schemas.uipath.com/workflow/activities/uix"`.

## Still to confirm in Studio

Only one thing blocks emitting modern activities, and one clipboard copy answers
it: **a Use Browser card holding a Click and a Type Into, both indicated on real
elements, with a text typed in**. From it we need to see:

1. how the target is written: `<uix:NClick.Target><uix:TargetAnchorable … />`,
   which selector property carries the value inside a card (`PartialSelector`
   with `FullSelector` beside it?), and which of `Guid`, `Version`,
   `WaitForReady`, `Visibility`, `SelectionStrategy` Studio always writes;
2. whether `Timeout` appears as an attribute or a child element;
3. how `Text` is written for Type Into (attribute vs `<uix:NTypeInto.Text>`).

Until that is answered, generation stays on the classic activities that a Studio
round-trip has already confirmed; nothing modern is emitted on a guess.
