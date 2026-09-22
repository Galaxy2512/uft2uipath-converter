# UFT → UiPath mapping registry

How the converter decides which UiPath activities a UFT script line becomes,
what each mapping means, what is still missing, and how to add a mapping.

## Principles

- **Nothing is guessed.** A construct is either translated with its UFT/VBScript
  semantics or blocked with a reason. A blocked line becomes a `Throw`, and the
  workflow starts with a `Throw`, so an incomplete migration can never run as if
  it were complete.
- **General, not sample-specific.** Every mapping must hold for the ~4000
  production tests, not only for the demo exports.
- **Mapped is not verified.** `mapped_unverified` means an activity was emitted.
  Studio load (`studio_load_verified`), execution (`executable_verified`) and UFT
  equivalence (`equivalent_verified`) are separate gates.

## Architecture

```text
Script.mts
   │  parser/uft_vbscript_parser.py      what the line means (neutral AST, parser/uft_script_nodes.py)
   ▼
Neutral AST (operations, conditions, values)
   │  script_analysis/analyzer.py         references, parser-level blockers, coverage
   ▼
mapping/operation_registry.py            UFT → UiPath registry: one entry per node type
   │
   ▼
script_generation/emitters/*.py          handlers: which activities a node becomes
   │  script_generation/emitter.py        ComponentEmitter: per-workflow state, typed values, selectors
   ▼
script_generation/browser_scopes.py      Attach Browser / Attach Window grouping
script_generation/studio_xaml.py         C# XAML exactly as Studio saves it
   ▼
script_generation/project_emitter.py     test cases per ALM test, project.json
   ▼
mapping/inventory.py                     coverage report (artifacts/migration-coverage.json)
```

| Module | Responsibility |
|---|---|
| `mapping/operation_registry.py` | Source of truth: every parser node type, its UiPath activities, status and handler |
| `script_generation/emitters/ui.py` | UI actions and checks: Exist, GetROProperty, Click, Set, SetSecure, Select, Sync |
| `script_generation/emitters/flow.py` | If and conditions (comparison, And/Or/Not), assignments, output parameters, Wait, no-op statements |
| `script_generation/emitters/testing.py` | Test outcome: Reporter.ReportEvent, ExitTest |
| `script_generation/emitters/functions.py` | VBScript built-in functions and arithmetic as typed C# |
| `script_generation/emitters/calls.py` | Calls to user/library Functions and Subs: Invoke Workflow File |
| `script_generation/emitters/system.py` | Starting programs: SystemUtil.Run → Start Process |
| `script_generation/user_functions.py` | Compiles each called Function/Sub into its own workflow |
| `script_analysis/function_definitions.py` | Which functions an action can call, in UFT lookup order |
| `script_generation/emitter.py` | `ComponentEmitter`: dispatch, typed values, bindings, rollback, report |
| `script_generation/project_emitter.py` | Test case per ALM test: argument wiring, failure flag, ExitTest catch |
| `mapping/inventory.py` | Inventory of operations, blockers by reason, coverage per test |

## Registry entries

Each entry (`OperationMapping`) describes one parser node type:

| Field | Meaning |
|---|---|
| `node_type` | Parser class name, e.g. `ClickOperation` |
| `uft` | The UFT construct, for people and reports, e.g. `.Click` |
| `activities` | UiPath activities it becomes |
| `status` | `supported`, `no_effect`, `planned`, `requires_strategy`, `unsupported` |
| `kind` | `operation` (a statement), `condition` (the test of an If), `expression` (a value) |
| `returns` / `typer` | For expressions: the result type, or a function computing it from the operands |
| `requires_selector` | Needs a verified object binding |
| `handler` | The emitter function; `None` while not implemented |

Handlers register themselves with the `@maps(...)` decorator. A second handler
for the same node type is an error at import time. A test fails if the parser
gains a node type without a registry entry.

Handler signatures:

```python
# operation: emit into parent, update the report trace; raise ValueError to block
def handler(ctx, node, parent, trace, display): ...

# condition: return C# Boolean code; activities it needs go into parent first
def handler(ctx, node, parent, display) -> str: ...

# expression: return C# code of the registry type; parent may be None
def handler(ctx, node, parent) -> str: ...
```

## Current mappings

### Operations

| UFT | UiPath | Notes |
|---|---|---|
| `Obj.Click` | Click | Single left click at the centre; a recorded offset is not reproduced |
| `Obj.Set value` | Type Into | Replaces the field content |
| `Obj.SetSecure x` | Type Into | Value from a secure argument; UFT's encoded value is not decoded |
| `Obj.Select value` | Select Item | |
| `Browser/Page.Sync` | Wait Ui Element Appear | Waits for the page element, close to but not the same as load completion |
| `Wait n` | Delay | Positive literal seconds only |
| `Select Case x` / `Case a, b` / `Case Else` | Assign + If/Else chain | Subject evaluated once; each Case compares for equality, in order; `Case Is` and `Case a To b` block |
| `SystemUtil.Run file, params, dir, op, mode` | Start Process | Only the default `open` operation; the window mode is not reproduced (noted) |
| `x = value` | Assign | Variable typed String, Int32, Boolean or Double; one type per variable |
| `Parameter("X") = value` | Assign | To Out argument `out_param_X`; the test exposes it per step |
| `Reporter.ReportEvent` | Log Message | See *Test outcome* |
| `ExitTest` | Throw | See *Test outcome* |
| `Dim`, `Option Explicit`, `Randomize`, `Function` definitions | – | No effect; a definition runs only when called |
| `Foo a, b`, `Call Foo(a)`, `x = Foo(a)` | Invoke Workflow File | Calls the function's own workflow; see *Functions and Subs* |
| `Navigate`, `Close`, `Activate`, `Back` | – | **planned** (Go To URL, Close, Application Card, Go Back) |
| Checkpoints, `Set x = CreateObject(...)` | – | **requires strategy** |

### Conditions (`If ... Then`)

| UFT | C# / UiPath |
|---|---|
| `Obj.Exist(n)` | Element Exists into a Boolean variable (full selector, outside browser scopes) |
| `a = b`, `a <> b`, `<`, `>`, `<=`, `>=` | Typed comparison; strings ordinal, `null` treated as `""` |
| `a And b`, `a Or b`, `Not a` | `&&`, `||`, `!` |
| A Boolean value | Used directly |

Parentheses are unwrapped and operators are split by VBScript precedence
(`Or` < `And` < `Not` < comparison), never inside strings or calls. All activities
a condition needs run before the `If`, as VBScript evaluates every operand.

### Values and functions

| UFT | C# |
|---|---|
| `Obj.GetROProperty("p")` | Get Attribute into an Object variable, read with `Convert.ToString` |
| `a & b` | String concatenation; numbers and Booleans converted as VBScript does |
| `+ - * / \ Mod ^`, unary `-` | Typed arithmetic; `/` and `^` give Double, `\` and `Mod` need Int32 |
| `Len LCase UCase Trim LTrim RTrim Left Right Mid InStr InStrRev Replace Space Chr` | Null-safe string code |
| `CStr CInt CLng CDbl Int Fix Abs Rnd` | Conversions with VBScript rounding (`CInt` rounds half to even, `True` is -1) |

GetROProperty maps only these properties, since they read the same DOM value
under the same name: `innertext outertext innerhtml outerhtml value href title
name class url src alt text`, `html id` → `id`, `html tag` → `tag`. Others block.

## Semantics

### Types

Every value has a static type: String, Int32, Boolean, Double (and Object for
activity results). Only conversions VBScript and C# agree on are implicit
(Int32 → Double; numbers and Booleans → String in `&` and `CStr`). Anything that
relies on VBScript's Variant conversions blocks, e.g. `"a" + 1`,
`Parameter("X") = False` (String vs Boolean), `1.5 Mod 2`.

VBScript names are case-insensitive, C# names are not: a variable written as
both `sValue` and `svalue` blocks, as do names that are C# keywords.

### Null

An argument that is not passed is `null` in C#, but `Empty` (`""`) in VBScript.
String code is therefore wrapped as `(x ?? "")`, except for literals and values
that cannot be null (concatenations, `ToString()`, string function results).

### Test outcome

UFT continues after `Reporter.ReportEvent micFail`; the test fails at the end.
The converter reproduces that:

- `micPass`/`micDone` → Log Message Info, `micWarning` → Warn, `micFail` → Error.
- `micFail` also sets the InOut argument `io_uft_failed` of the action workflow.
- The test case passes one shared variable `uft_failed` to every step and ends
  with `If uft_failed → Throw`.
- `ExitTest` throws an `ApplicationException` marked `UFT ExitTest`. The test runs
  its steps in a TryCatch that stops them without failing; other exceptions are
  rethrown. A faulted workflow does not hand back its InOut arguments, so the
  exception message carries ` [failure reported]` when a failure was reported
  before, and the test adds it to `uft_failed`.

### Functions and Subs (library strategy A)

Every Function/Sub an action calls, defined in the action itself or in an
associated function library (`.qfl`/`.vbs`/`.txt`), becomes its own workflow
`Functions\Function_<Name>.xaml`, called with Invoke Workflow File
(`script_generation/user_functions.py`, call sites in `emitters/calls.py`).

- **Lookup** follows UFT: the action's own functions first, then the libraries
  in their configured order (`script_analysis/function_definitions.py`). A user
  definition wins over a VBScript built-in of the same name (e.g. `Sub Log`).
- **Calls**: as statements (`Foo`, `Foo a, b`, `Call Foo(a)`), in values
  (`x = Foo(a)`), and without parentheses (`n = GetCount`).
- **Parameters** are In arguments typed from the call. A parameter the body
  assigns is InOut: with ByRef (the VBScript default) and a variable passed, the
  caller's variable changes; with ByVal or an expression passed, a copy does.
- **Return value**: `FunctionName = value` assigns the Out argument `out_result`.
- **Context**: `Environment`/`Parameter`/`DataTable` values used in the body are
  passed on from the caller's arguments of the same name; `micFail` in a function
  sets the caller's failure flag; `ExitTest` in a function still ends the test.
- **Library globals** set once to a literal at load time (`IgnoredStringValue =
  "<SKIP>"`) are constants; a local `Dim` shadows them; changing them without
  one blocks, since other functions would not see the change.
- **One workflow per signature**: a function is compiled once per combination
  of argument types and the selectors its body uses, and shared by all callers.
- **Blocking**: a function whose body cannot be fully migrated is still written,
  guarded by a Throw; every call to it blocks as `library`, naming the function's
  first blocker. Recursion, optional/array parameters, writing output
  parameters or secure values inside a function also block.

Strategy B (direct activity mappings for the most-used helpers, e.g.
`Excel_ReadValue` → Read Cell) waits for the real function libraries.

### Blocking and rollback

A handler raises `ValueError` with the reason. Everything the line had already
emitted (for example a Get Attribute before a failed comparison) is removed,
and a `Throw` replaces it. The reason appears in `generation-report.json`.

## Coverage inventory

Every `convert` writes `artifacts/migration-coverage.json`. For several exports:

```powershell
python -m uft2uipath inventory output\run1 output\run2 --out coverage.json
```

It reports lines mapped/blocked, operations by outcome, blocked lines by reason,
unmapped functions and object methods, coverage per test and the registry by
status. Coverage is computed from the per-line trace, not from the registry: a
supported operation still blocks when its object has no selector.

| Reason | Meaning | Owner |
|---|---|---|
| `mapping` | Operation has no UiPath mapping yet | converter |
| `expression` | Value or type not supported | converter |
| `condition` | If condition not supported | converter |
| `parser` | Statement or object chain not fully parsed | converter |
| `library` | Calls a function library routine, not migrated yet | converter + libraries from the export |
| `binding` | No verified selector or argument | selector review |

## Adding a mapping

1. Find the priority with `uft2uipath inventory` over real exports.
2. If the parser does not produce a node for the construct yet, add the node to
   `parser/uft_script_nodes.py` and parse it in `parser/uft_vbscript_parser.py`.
3. Write the handler in the matching `script_generation/emitters/*.py` module
   with `@maps(...)`; remove the `planned` entry from `operation_registry.py` if
   there was one.
4. Reproduce UFT semantics; raise `ValueError` for anything that would need a
   guess. Prefer blocking to an approximation that changes behaviour.
5. Add tests: the parse, the emitted XAML, and the cases that must block.
6. Run `pytest`, `convert` both sample exports and compare `inventory` before and after.
7. Have the new activity opened in Studio; record the result below.

## Studio evidence

Confirmed by opening generated projects in UiPath Studio (Windows, C#):

- Loaded: Get Attribute with `Result` as `OutArgument<Object>`; Click inside
  Attach Browser; Assign to an InOut Boolean argument; If with a C# condition.
- Rejected, now fixed: Log Message with `Message` as `InArgument<String>` was
  shown as an unresolved ErrorActivity; Studio types `Message` as Object.

Not yet confirmed: the test-level TryCatch/Rethrow for ExitTest, InOut
arguments on Invoke Workflow File, and whether an exception from an invoked
workflow keeps its original type. Modern activities (decided as the target)
wait for the Activity Lab examples from Studio.

## Known gaps

- Function bodies in the sample libraries still block on: `WinRadioButton.Set`
  without a value and `.Type`, `WaitProperty` (returns True/False in UFT, while
  UiPath's Wait Attribute throws on timeout), `ExitComponent`, `CreateObject`
  (FileSystemObject, WScript.Shell), date functions (`Date`, `Day`, `Month`,
  `Year`), arrays, and variables that change type (VBScript Variants, e.g. a
  number later concatenated as a string).
- `Excel_ReadValue` and other functions whose library is not in the export.
- Navigate, Close, Activate, Back, UIA objects, descriptive programming
  (`Browser("title:=...")`).
- UFT regular expressions in object properties (e.g. `innertext="Admin|ESS"`)
  are copied into selectors literally; UiPath needs explicit regex matching.
- Output parameters are exposed per step, but BPT links from one component's
  output to a later component's input are not wired yet.
