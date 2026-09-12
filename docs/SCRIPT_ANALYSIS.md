# Script-to-model analysis

This milestone connects explicit source scripts to component identities and test
instances. It does not generate XAML, execute VBScript, discover authoritative
ProjRep ownership, or certify semantic equivalence.

## Run the bundled example

From the repository root:

    python -m uft2uipath analyze-scripts examples/script_analysis/manifest.json --out output/script-analysis-demo

Expect two unique components, two tests and three component instances.
Both sources are analyzed. Blockers are expected: the example includes
declarations and a custom function outside the supported parser subset, and
argument, selector, report-outcome and secure-value mappings are unresolved.

The output directory must not exist. A normal run returns 0 when analysis and
reports are written, even if blockers exist. For automated quality gates add
--fail-on-blockers: exit code 2 then indicates blockers after the reports have
been written. Invalid input schema or ambiguous identity also exits with 2,
but before output creation. See the error text to distinguish them.

## Input contract

Manifest example:

    {
      "rows": "rows.json",
      "bindings": [
        {"component_id": "10", "script": "login.vbs", "encoding": "auto"}
      ]
    }

Paths are relative to the manifest directory, or explicit absolute paths.
Rows use the same project_name and four-table contract as build-model:
TEST, COMPONENT, COMPONENT_STEP, BPTEST_TO_COMPONENTS.

A binding must use the real COMPONENT.CO_ID from verified source metadata.
Do not substitute a component name or the guessed numeric ProjRep path ID.
This milestone consumes an explicit manifest; it does not automate that
discovery. Multiple script files for one component require a future ordered
source model; duplicate bindings are rejected rather than arbitrarily chosen.
Missing bindings produce component-level blockers.

Encoding auto accepts BOM-marked UTF-16 or UTF-8 (optional BOM). For known
legacy source encodings specify e.g. cp1252 explicitly. Invalid bytes are not
discarded or replaced: the component gets an error, its original bytes remain
preserved, and other components continue.

## Outputs

- model.json: project model, component-analysis links on test instances, original
  four tables, complete source_payload including additional unprocessed tables,
  original manifest and limitations.
- Components/component_<ID>.json: explicitly typed script AST, source text,
  normalized source lines, line-number diagnostics, operation recognition
  counts, parsed references, source hash and binding.
- Sources/component_<ID>.source: exact original bytes, including BOM and line
  endings, also retained on decoding failures when the source was readable.
- Sources/alm_rows.json and Sources/manifest.json: original input snapshots.
- report.json: counts, per-definition findings, per-test ordered instance links,
  raw relationship metadata and relationship integrity issues.
- report.md: summary and limitations.

Unsupported code and expressions are retained. The AST uses node_type tags,
so ParameterReference is distinct from LiteralValue. Existing UFT logical
object chains do not become invented UiPath selectors. Argument declarations,
directions, types, instance data binding and variables are not resolved by this
milestone; declarations currently remain unsupported operations with raw text.
Parsed reference lists are not a complete inventory of references hidden in
unsupported statements or expressions.

A shared component is analyzed once per definition. Test instances retain
their separate ALM relationship rows and link to that definition's analysis.
Identical component names do not collide because output files use numeric IDs.
Additional source tables are preserved but not interpreted.

## Status and coverage

- missing_binding: no source mapping.
- error: source read, decoding or parsing failed; other components continue.
- blocked: source parsed but there are known unsupported or unresolved items.
- analyzed: analysis produced no current diagnostics. This is not proof of
  full VBScript support, executable output or equivalent behavior.

generation_ready and executable_verified are always false in this milestone.
Recognition counts describe parser nodes, recursively including nested
branches, not migrated tests, test pass rates or semantic correctness.
Comments and block terminators remain in the source but are not operations.
If nodes and child operations count separately. A global relationship issue
conservatively blocks every test; the offending row is preserved in the report.

The batch uses the current limited parser. A typed AST can still be incomplete
for syntax outside its supported subset. Unsupported/ambiguous code requires
further parsing work and validation before generation.

## Verification

    python -m pytest -q
    git diff --check

Tests cover branch structure, typed expressions, preserved bytes and Unicode,
explicit identity, duplicate and missing mappings, failed-file isolation,
unresolved references, outcome blockers, CLI exit codes, output protection and
a synthetic batch of 4000 tests sharing one component.

The synthetic 4000-test case proves reuse of one analysis; it is not a throughput
benchmark for 4000 unique real scripts. Results are held in memory during the
batch. Checkpoint/resume is not implemented. An I/O failure in the final copy
can leave a partial new output directory; existing outputs are never merged.
