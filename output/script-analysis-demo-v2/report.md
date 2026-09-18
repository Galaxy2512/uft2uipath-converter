# UFT script analysis

Unique components: 2

Tests: 2

## Limitations

- Analysis only: no executable UiPath workflows are produced.
- Manifest mappings must be supplied from verified ALM relationships; names and ProjRep numbers are not guessed.
- Recognition coverage is not semantic equivalence or migration success.
- Source declarations, unsupported constructs and expressions remain preserved for review.
- Argument definitions, instance values, selectors and full UFT semantics are not resolved.
- Reference inventories cover parsed nodes; references inside unsupported expressions remain in raw source.

## Findings by code

- assertion_mapping_required: 2
- environment_binding_required: 2
- exist_mapping_required: 1
- exit_mapping_required: 1
- parameter_binding_required: 2
- secure_value_mapping_required: 1
- selector_mapping_required: 5
- unsupported_expression: 1
- unsupported_statement: 3

Detailed component, test, source-line and relationship findings: report.json.
