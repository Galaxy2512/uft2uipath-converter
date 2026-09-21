# Convert decoded ALM rows

Run from the repository root:

    python -m uft2uipath convert-rows examples/decoded_alm_demo.json --out output/review

The destination is output/review/DemoMigration. Existing destinations are rejected.
Use another output parent for a subsequent run.

Input requires project_name and four arrays: TEST, COMPONENT, COMPONENT_STEP,
BPTEST_TO_COMPONENTS. This is not a QCP reader. IDs and relationship references
are checked, and step/component order must be present as integers.
Component definition names must be distinct ignoring case.
Repeated references to one component definition are allowed.

Output includes project.json, Main.xaml, Workflows, Data/migration_model.json,
Reports/ConversionReport.json and Reports/ConversionReport.md.

This output is a review scaffold. It is not verified as executable or importable
in UiPath Studio. Source descriptive steps become unsupported TODOs. VBScript,
selectors, arguments and test assertions are not connected. Main.xaml currently
flattens component calls across tests rather than generating independent UiPath
test cases. Source tables are preserved so unreferenced definitions remain visible.

Only convert-rows uses these validation guards; the legacy generator and the
build-model command do not acquire these guarantees. Output is staged before
copying; an I/O failure during the final copy may leave a partial new directory.
