from uft2uipath.parser.project_builder import ProjectBuilder


def test_project_builder_links_tests_components_and_steps():
    # TEST table
    test_rows = [
        {
            "TS_TEST_ID": "102",
            "TS_NAME": "Fully_BPT_TestCase",
            "TS_TYPE": "BUSINESS-PROCESS",
            "TS_EXEC_STATUS": "Passed",
        }
    ]

    # COMPONENT table
    component_rows = [
        {
            "CO_ID": "10",
            "CO_NAME": "BrowserStart_QWERTZ",
            "CO_STATUS": "Ready",
            "CO_SCRIPT_TYPE": "QT-SCRIPTED",
        },
        {
            "CO_ID": "20",
            "CO_NAME": "BrowserNavigate_QWERTZ",
            "CO_STATUS": "Ready",
            "CO_SCRIPT_TYPE": "QT-SCRIPTED",
        },
    ]

    # COMPONENT_STEP table
    component_step_rows = [
        {
            "CS_STEP_ID": "201",
            "CS_COMPONENT_ID": "10",
            "CS_STEP_ORDER": "2",
            "CS_STEP_NAME": "Second browser step",
        },
        {
            "CS_STEP_ID": "200",
            "CS_COMPONENT_ID": "10",
            "CS_STEP_ORDER": "1",
            "CS_STEP_NAME": "First browser step",
        },
        {
            "CS_STEP_ID": "300",
            "CS_COMPONENT_ID": "20",
            "CS_STEP_ORDER": "1",
            "CS_STEP_NAME": "Navigate to URL",
        },
    ]

    # BPTEST_TO_COMPONENTS table
    test_component_rows = [
        {
            "BC_ID": "2",
            "BC_BPT_ID": "102",
            "BC_CO_ID": "20",
            "BC_ORDER": "2",
        },
        {
            "BC_ID": "1",
            "BC_BPT_ID": "102",
            "BC_CO_ID": "10",
            "BC_ORDER": "1",
        },
    ]

    project = ProjectBuilder().build(
        project_name="Migration_BPT",
        test_rows=test_rows,
        component_rows=component_rows,
        component_step_rows=component_step_rows,
        test_component_rows=test_component_rows,
        source_path="Migration_BPT.qcp",
    )

    assert project.name == "Migration_BPT"
    assert len(project.tests) == 1

    test_case = project.tests[0]

    # Components must follow BC_ORDER.
    assert [component.name for component in test_case.components] == [
        "BrowserStart_QWERTZ",
        "BrowserNavigate_QWERTZ",
    ]

    # Steps must follow CS_STEP_ORDER.
    assert [
        step.name
        for step in test_case.components[0].steps
    ] == [
        "First browser step",
        "Second browser step",
    ]

    assert project.metadata["test_count"] == 1
    assert project.metadata["component_definition_count"] == 2
    assert project.metadata["component_step_count"] == 3


def test_component_instance_is_copied_for_each_test():
    test_rows = [
        {"TS_TEST_ID": "1", "TS_NAME": "Test A"},
        {"TS_TEST_ID": "2", "TS_NAME": "Test B"},
    ]

    component_rows = [
        {"CO_ID": "10", "CO_NAME": "SharedComponent"},
    ]

    relations = [
        {
            "BC_ID": "1",
            "BC_BPT_ID": "1",
            "BC_CO_ID": "10",
            "BC_ORDER": "1",
        },
        {
            "BC_ID": "2",
            "BC_BPT_ID": "2",
            "BC_CO_ID": "10",
            "BC_ORDER": "1",
        },
    ]

    project = ProjectBuilder().build(
        project_name="Demo",
        test_rows=test_rows,
        component_rows=component_rows,
        component_step_rows=[],
        test_component_rows=relations,
    )

    first_component = project.tests[0].components[0]
    second_component = project.tests[1].components[0]

    # They represent the same ALM definition, but separate test instances.
    assert first_component.id == second_component.id == 10
    assert first_component is not second_component