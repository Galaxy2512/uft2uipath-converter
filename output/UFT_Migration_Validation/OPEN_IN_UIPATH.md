# Open the generated project

1. Extract the entire ZIP into a new folder.
2. In UiPath Studio choose Open and select project.json.
3. Allow dependency restoration.
4. Open Tests/Test_1.xaml (or another generated Test_<ID>.xaml).
5. Open Workflows/Component_<ID>.xaml to inspect migrated branches and activities.
6. Run Studio validation before execution.

Validation corrections: argumentless workflows omit x:Members; Click and Type Into use Attach Browser with partial selectors. Exist stays before If, outside the branch scopes. Keep the UI-DBP-006 analyzer rule enabled.

The sample uses synthetic selectors and is intentionally blocked with Throw. Do not remove the guard merely to make the test pass.

The project targets Windows C#. Python tests check generation and XML, not Studio loading, compilation, execution or UFT equivalence. Read generation-report.json for unresolved items.

Package versions use an official UiPath sample baseline. For your installed versions rerun migrate-project with --project-template pointing to a blank Windows C# test project's project.json containing System, Testing and UIAutomation dependencies.
