from uft2uipath.ast import BusinessComponent, Parameter
from uft2uipath.parser.step_parser import StepParser


class ComponentParser:
    def __init__(self, step_parser: StepParser | None = None):
        self.step_parser = step_parser or StepParser()

    def parse(self, raw_component: dict) -> BusinessComponent:
        component = BusinessComponent(
            name=raw_component.get("name", "UnnamedComponent"),
            description=raw_component.get("description"),
            raw=raw_component,
        )

        for raw_param in raw_component.get("parameters", []):
            component.parameters.append(
                Parameter(
                    name=raw_param.get("name", "UnnamedParameter"),
                    value=raw_param.get("value"),
                    datatype=raw_param.get("datatype"),
                    direction=raw_param.get("direction"),
                    raw=raw_param,
                )
            )

        for raw_step in raw_component.get("steps", []):
            component.steps.append(
                self.step_parser.parse_action(
                    name=raw_step.get("name", "UnnamedStep"),
                    action=raw_step.get("action", "UnknownAction"),
                    target=raw_step.get("target"),
                    value=raw_step.get("value"),
                    raw=raw_step,
                )
            )

        for step in component.steps:
            component.issues.extend(step.issues)

        return component