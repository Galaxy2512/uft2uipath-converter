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

## Still needed

1. **Use Application/Browser with a real target**, twice: once on any browser
   window and once on any desktop application (e.g. Notepad), so `TargetApp`
   shows how Studio records a browser (type, URL, selector) and a desktop
   application (file path, window selector). UFT tests use both (Browser/Page
   and Window/Dialog objects). Which application does not matter.
2. Inside it, one of each, each **indicated on a real element**: Click, Type
   Into (text and secure text), Select Item, Check/Uncheck, Get Text, Get
   Attribute, Check App State, Go To URL, Go Back, Close Application.
3. Outside it: Assign (String, Int32, Boolean), If, Delay, Throw, Log Message,
   Start Process, Invoke Workflow File (one In and one Out argument), Verify
   Expression.
4. The project's `project.json` (exact package versions) and, preferably, the
   saved `.xaml` files instead of clipboard copies: saved files also show the
   namespace imports and assembly references Studio writes.

Clipboard copies (`ClipboardData`) keep the activity itself but omit the
workflow header; they are enough for the activity's own properties.
