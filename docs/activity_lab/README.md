# Activity Lab: modern activity XAML from UiPath Studio

Reference XAML copied from UiPath Studio, used to emit modern activities in the
exact shape Studio saves. Nothing here is guessed: every file is Studio output.
The converter's catalog of modern activities is built from these files.

These files teach only the **shape** of each activity. The application in them
is incidental: in the migrated tests the browser type, URL, window title and
selectors always come from each UFT test's own Object Repository, descriptive
properties and selector review, never from these samples.

## Collected

| File | Activity | What it shows |
|---|---|---|
| `NApplicationCard.clipboard.xaml` | Use Application/Browser (`uix:NApplicationCard`) | Namespace `uix` = `http://schemas.uipath.com/workflow/activities/uix`; `Version="V2"`, `AttachMode="ByInstance"`, `ScopeGuid`; body is `ActivityAction<Object>` with argument `WSSessionData` around a `Sequence "Do"`; `TargetApp` child. **No application indicated yet**: `TargetApp` only has `Area`. |
| `NGetUrl.clipboard.xaml` | Get URL (`uix:NGetUrl`) | `Version="V3"`; result property `CurrentUrl` (unset here). |
| `NApplicationCard_browser_NClick_NTypeInto.clipboard.xaml` | Use Browser with an indicated browser window, containing Click and Type Into | `TargetApp` for a browser: `BrowserType="Edge"`, `Selector="<html app='msedge.exe' title='…' />"`, `Title`, `Url`, `Area`, plus design-time `IconBase64` (dropped here) and `InformativeScreenshot`. Card: `InteractionMode="DebuggerApi"`. `uix:NClick` V3 (`ClickType="Single"`, `MouseButton="Left"`, `KeyModifiers="None"`, `ActivateBefore="True"`), `uix:NTypeInto` V3 (`ClickBeforeMode="Single"`, `EmptyFieldMode="SingleLine"`). **Click and Type Into were not indicated on elements** (no target), and Type Into has no text. |

| `NApplicationCard_desktop.clipboard.xaml` | Use Application with an indicated desktop window (here the Windows desktop, "Program Manager") | `TargetApp` for a desktop app: `FilePath` (the executable), `Selector="<wnd app='explorer.exe' cls='Progman' title='Program Manager' />"`, `Title`, `Area`; no `BrowserType`, `Url` or `InteractionMode`. Body still empty. |

What these give the converter: the browser card's `Selector` is the same
`<html app=… title=… />` form the converter already derives from a UFT Page's
title, with `app` from the browser type (e.g. msedge.exe). `Url`, `Title` and
`Area` are design-time information from indicating the window.

A desktop card's `Selector` is the `<wnd …/>` form the converter derives from a
UFT Window/Dialog (`cls` from nativeclass, `title` from the window title). UFT
repositories do not record the process name (`app`) or the executable path
(`FilePath`): the selector candidates already report `process_name_unspecified`,
so both must come from the selector review for desktop applications.

## Still needed

1. ~~Use Application/Browser with a real target, for a browser and for a
   desktop application~~ (collected, see above).
2. Inside it, one of each, each **indicated on a real element** (so the
   activity gets its `Target` with the element selector) and with its value
   filled in (e.g. Type Into with a text): Click, Type Into (text and secure text), Select Item, Check/Uncheck, Get Text, Get
   Attribute, Check App State, Go To URL, Go Back, Close Application.
3. Outside it: Assign (String, Int32, Boolean), If, Delay, Throw, Log Message,
   Start Process, Invoke Workflow File (one In and one Out argument), Verify
   Expression.
4. The project's `project.json` (exact package versions) and, preferably, the
   saved `.xaml` files instead of clipboard copies: saved files also show the
   namespace imports and assembly references Studio writes.

Clipboard copies (`ClipboardData`) keep the activity itself but omit the
workflow header; they are enough for the activity's own properties.
