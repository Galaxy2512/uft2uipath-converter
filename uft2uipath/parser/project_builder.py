"""
ALM Project Builder

Responsibility
--------------
Builds the neutral Project AST from already-decoded ALM database rows.

This module does NOT:
- read QCP archives
- decode PTD binary files
- generate UiPath XAML

It receives normal Python dictionaries representing rows from:

- TEST
- COMPONENT
- COMPONENT_STEP
- BPTEST_TO_COMPONENTS

It then resolves ALM relationships and creates:

Project
    -> UftTestCase
        -> BusinessComponent
            -> Step

Why this separation matters
---------------------------
The builder understands relationships between ALM entities, but it does
not understand the physical storage format.

That keeps PTD decoding, ALM semantics and UiPath generation independent.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from uft2uipath.ast import BusinessComponent, Project, Step, UftTestCase
from uft2uipath.parser.component_entity_parser import ComponentEntityParser
from uft2uipath.parser.step_entity_parser import StepEntityParser
from uft2uipath.parser.test_entity_parser import TestEntityParser


class ProjectBuilder:
    """
    Builds a complete Project AST from decoded ALM table rows.
    """

    def __init__(
        self,
        test_parser: TestEntityParser | None = None,
        component_parser: ComponentEntityParser | None = None,
        step_parser: StepEntityParser | None = None,
    ):
        # Parsers convert individual ALM rows into neutral AST objects.
        self.test_parser = test_parser or TestEntityParser()
        self.component_parser = component_parser or ComponentEntityParser()
        self.step_parser = step_parser or StepEntityParser()

    def build(
        self,
        project_name: str,
        test_rows: list[dict[str, Any]],
        component_rows: list[dict[str, Any]],
        component_step_rows: list[dict[str, Any]],
        test_component_rows: list[dict[str, Any]],
        source_path: str | None = None,
    ) -> Project:
        """
        Build a Project AST.

        Parameters
        ----------
        project_name:
            Name of the generated neutral project.

        test_rows:
            Decoded rows from ALM TEST table.

        component_rows:
            Decoded rows from ALM COMPONENT table.

        component_step_rows:
            Decoded rows from ALM COMPONENT_STEP table.

        test_component_rows:
            Decoded rows from ALM BPTEST_TO_COMPONENTS table.

        source_path:
            Original QCP or extracted project path.

        Returns
        -------
        Project:
            Project containing tests, ordered components and ordered steps.
        """

        # --------------------------------------------------------------
        # STEP 1
        # Parse all independent ALM entities into neutral AST objects.
        # --------------------------------------------------------------
        tests = [self.test_parser.parse(row) for row in test_rows]

        components = [
            self.component_parser.parse(row)
            for row in component_rows
        ]

        steps = [
            self.step_parser.parse(row)
            for row in component_step_rows
        ]

        # --------------------------------------------------------------
        # STEP 2
        # Build fast lookup dictionaries by ALM primary key.
        #
        # This is important for projects with thousands of tests because
        # repeated list scans would become unnecessarily expensive.
        # --------------------------------------------------------------
        tests_by_id: dict[int, UftTestCase] = {
            test.id: test
            for test in tests
            if test.id is not None
        }

        components_by_id: dict[int, BusinessComponent] = {
            component.id: component
            for component in components
            if component.id is not None
        }

        # --------------------------------------------------------------
        # STEP 3
        # Group COMPONENT_STEP records by CS_COMPONENT_ID.
        # --------------------------------------------------------------
        steps_by_component_id: dict[int, list[Step]] = defaultdict(list)

        for row, step in zip(component_step_rows, steps, strict=True):
            component_id = self._to_int(row.get("CS_COMPONENT_ID"))

            if component_id is None:
                continue

            steps_by_component_id[component_id].append(step)

        # Sort steps according to the order stored in ALM.
        for component_id, component_steps in steps_by_component_id.items():
            component_steps.sort(key=self._step_sort_key)

            component = components_by_id.get(component_id)

            if component is not None:
                component.steps.extend(component_steps)

        # --------------------------------------------------------------
        # STEP 4
        # Group BPTEST_TO_COMPONENTS records by test ID.
        #
        # BC_BPT_ID -> TEST.TS_TEST_ID
        # BC_CO_ID  -> COMPONENT.CO_ID
        # BC_ORDER  -> component order inside the BPT test
        # --------------------------------------------------------------
        relations_by_test_id: dict[int, list[dict[str, Any]]] = defaultdict(list)

        for relation in test_component_rows:
            test_id = self._to_int(relation.get("BC_BPT_ID"))

            if test_id is None:
                continue

            relations_by_test_id[test_id].append(relation)

        # Sort components exactly as they were ordered in ALM.
        for relations in relations_by_test_id.values():
            relations.sort(key=self._relation_sort_key)

        # --------------------------------------------------------------
        # STEP 5
        # Attach ordered Business Components to each UFT test.
        # --------------------------------------------------------------
        for test_id, relations in relations_by_test_id.items():
            test = tests_by_id.get(test_id)

            if test is None:
                # Relationship references a test that was not loaded.
                # Later the validator will report this as an integrity issue.
                continue

            for relation in relations:
                component_id = self._to_int(relation.get("BC_CO_ID"))
                component = components_by_id.get(component_id)

                if component is None:
                    continue

                # A Business Component can appear multiple times in one test.
                # We therefore create a copy for each test instance.
                component_instance = deepcopy(component)

                # Preserve relationship-level ALM metadata.
                component_instance.raw = {
                    **component_instance.raw,
                    "_bpt_relation": dict(relation),
                }

                test.components.append(component_instance)

        # --------------------------------------------------------------
        # STEP 6
        # Return the neutral project consumed by validators and generators.
        # --------------------------------------------------------------
        return Project(
            name=project_name,
            source_path=source_path,
            tests=tests,
            metadata={
                "test_count": len(tests),
                "component_definition_count": len(components),
                "component_step_count": len(steps),
                "test_component_relation_count": len(test_component_rows),
            },
        )

    def _step_sort_key(self, step: Step) -> tuple[int, int]:
        """
        Sort steps by ALM order and then by ID for deterministic output.
        """

        return (
            step.order if step.order is not None else 2**31,
            step.id if step.id is not None else 2**31,
        )

    def _relation_sort_key(
        self,
        relation: dict[str, Any],
    ) -> tuple[int, int]:
        """
        Sort component relations by BC_ORDER and BC_ID.
        """

        order = self._to_int(relation.get("BC_ORDER"))
        relation_id = self._to_int(relation.get("BC_ID"))

        return (
            order if order is not None else 2**31,
            relation_id if relation_id is not None else 2**31,
        )

    def _to_int(self, value: Any) -> int | None:
        """
        Safely convert an ALM numeric value to integer.
        """

        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None