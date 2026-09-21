# uft2uipath converter

UFT / OpenText ALM `.qcp` to UiPath Test Project migration tool.

The project is currently focused on building a conservative, reviewable migration pipeline: when a UFT construct cannot be mapped safely, the converter preserves the source context and marks the generated UiPath workflow as blocked instead of silently producing incorrect automation.

## Current end-to-end pipeline

The `convert` command accepts an ALM/UFT `.qcp`, `.zip`, or an already extracted project folder and runs the following stages:

```text
QCP / ZIP / extracted ALM project
  -> extract
  -> decode ALM PTD tables
  -> build project/test/component model
  -> resolve UFT tests, actions and Script.mts files
  -> resolve local/shared Object Repositories
  -> propose UiPath selector candidates
  -> parse and analyse VBScript
  -> bind accepted selectors and runtime inputs
  -> emit UiPath workflows and test cases
  -> generate UiPath project.json
```

Each major stage writes reviewable JSON artifacts under `<output>/artifacts`.

## What is implemented

- QCP/ZIP extraction
- ALM PTD table decoding
- BPT/test/component relationship reconstruction
- UFT test/action script resolution
- `Script.mts` decoding and preservation
- local and shared Object Repository reading
- UFT object-reference resolution
- UiPath selector candidate generation
- selector review / confidence-based acceptance for generation
- VBScript parsing and coverage reporting
- function-library discovery and call annotation
- generation of UiPath XAML workflows
- generation of UiPath Test Project metadata and individual test cases
- explicit blocking with `Throw` when migration semantics remain unresolved
- migration reports and intermediate artifacts for manual review

Which UiPath activities each UFT construct becomes is decided by one mapping registry (`uft2uipath/mapping/operation_registry.py`). The emitter currently supports UI actions (click, set, secure set, select, sync), `If` with `Exist`, comparisons and `And`/`Or`/`Not`, `GetROProperty`, typed assignments, output parameters, `Reporter.ReportEvent` (micFail logs an error and fails the test at its end), `ExitTest`, arithmetic and the common VBScript string and number functions. Unsupported or ambiguous constructs remain visible as blockers with their reason.

See [docs/MAPPING_REGISTRY.md](docs/MAPPING_REGISTRY.md) for the full mapping table, semantics and how to add a mapping.

## Current verification level

The converter can generate a UiPath Test Project, but the project does **not yet claim runtime equivalence**.

Current status:

- Structural generation: implemented
- Semantic migration: partially implemented and explicitly reported
- UiPath project generation: implemented
- Studio load validation: not yet automated
- Executable verification: not yet completed end-to-end
- UFT/UiPath behavioural equivalence: not yet verified

Generated reports intentionally keep:

```text
studio_load_verified = false
executable_verified = false
equivalent_verified = false
```

until those stages are actually proven.

## Run the end-to-end converter

From the repository root:

```powershell
python -m uft2uipath convert ALM_DEMO_26.1.qcp --out output\alm_demo
```

Convert selected ALM test IDs:

```powershell
python -m uft2uipath convert ALM_DEMO_26.1.qcp --out output\alm_demo --test-id 5 --test-id 8
```

For web selectors accepted automatically above a confidence threshold, also specify the target browser:

```powershell
python -m uft2uipath convert ALM_DEMO_26.1.qcp --out output\alm_demo --accept-selectors 0.8 --browser-type Edge
```

For reviewed selectors, edit the generated `selector-review.template.json` and pass it back with:

```powershell
python -m uft2uipath convert ALM_DEMO_26.1.qcp --out output\alm_demo_reviewed --selector-review selector-review.json
```

## Important generated artifacts

Typical output:

```text
output/
  artifacts/
    decoded-tables.json
    resolved-project.json
    resolved-scripts.json
    selector-candidates.json
    script-analysis.json
    conversion-plan.json
    selector-review.template.json
    migration-coverage.json
    studio-validation.json
    pipeline-report.json

  project/
    project.json
    Main.xaml
    generation-report.json
    Tests/
      Test_<id>.xaml
    Workflows/
      Action_<...>.xaml
```

The generated test cases are registered in `project.json` and are intended to be run through UiPath Test Explorer. `Main.xaml` is not used to invoke private test cases.

## Migration coverage

`migration-coverage.json` counts mapped and blocked lines, blockers by reason (missing mapping, unsupported expression, library function, missing selector, ...) and coverage per test. To summarize one or more outputs:

```powershell
python -m uft2uipath inventory output\alm_demo output\bpt --out coverage.json
```

Use it to choose the next mappings by how many lines they unblock.

## Selector safety model

Selectors derived from UFT repositories are candidates. Acceptance for generation does **not** mean the selector has been verified against the live target application.

The next iteration should make the distinction explicit between:

- candidate
- accepted for generation
- Studio validated
- runtime verified

This avoids treating a confidence threshold as proof that the target matches during execution.

## Secure values

UFT `SetSecure` encoded values are not decoded or copied into the generated project. The current implementation requires the real value to be supplied through an input binding.

The current binding type is still `String`; migrating this to a UiPath credential / secure input strategy is a planned hardening step.

## Development

Install the package with development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run the test suite:

```powershell
pytest
```

Generated output, IDE metadata, virtual environments and caches are excluded through `.gitignore`.

## Main architecture

```text
uft2uipath/
  alm/                 ALM/PTD data and repository resolution
  archive/             QCP/ZIP extraction
  ast/                 neutral project model
  mapping/             UFT -> UiPath mapping registry, coverage inventory,
                       selector candidates and acceptance
  parser/              ALM entities and VBScript parsing (neutral AST)
  script_analysis/     references, blockers and coverage per script
  script_generation/   UiPath XAML and Test Project generation
    emitters/          one handler per UFT construct (ui, flow, testing, functions)
  uft/                 UFT Object Repository and resource readers
  pipeline.py          end-to-end conversion orchestration
  cli.py               command-line interface
```

Further documentation in `docs/`:

- [MAPPING_REGISTRY.md](docs/MAPPING_REGISTRY.md): mappings, semantics, coverage, adding a mapping
- [SCRIPT_ANALYSIS.md](docs/SCRIPT_ANALYSIS.md): VBScript analysis
- [WORKFLOW_EMISSION.md](docs/WORKFLOW_EMISSION.md): workflow emission and binding contract
- [PROJECT_MIGRATION.md](docs/PROJECT_MIGRATION.md): project-level migration
- [MAPPING_SPEC.md](docs/MAPPING_SPEC.md): original mapping principles

## Next milestone

The next development branch should focus on Studio validation rather than adding broad new parser coverage.

Target:

```text
ALM_DEMO_26.1.qcp
  -> uft2uipath convert
  -> generated UiPath Test Project
  -> open/validate in UiPath Studio
  -> Workflow Analyzer without blocking structural errors
  -> execute one representative Login test
```

Only after that milestone should the project claim an executable migration path.

## Legacy / auxiliary commands

The repository still contains lower-level commands such as `build-model`, `convert-rows`, `analyze-scripts`, `emit-workflows` and `migrate-project`. These remain useful for diagnostics and focused development, while `convert` is the primary end-to-end entry point.
