from uft2uipath.ast import Parameter, UftTestCase
from uft2uipath.parser.component_parser import ComponentParser


class TestParser:
    def __init__(self, component_parser: ComponentParser | None = None):
        self.component_parser = component_parser or ComponentParser()

    def parse(self, raw_test: dict) -> UftTestCase:
        test_case = UftTestCase(
            name=raw_test.get("name", "UnnamedTest"),
            description=raw_test.get("description"),
            raw=raw_test,
        )

        for raw_param in raw_test.get("parameters", []):
            test_case.parameters.append(
                Parameter(
                    name=raw_param.get("name", "UnnamedParameter"),
                    value=raw_param.get("value"),
                    datatype=raw_param.get("datatype"),
                    direction=raw_param.get("direction"),
                    raw=raw_param,
                )
            )

        for raw_component in raw_test.get("components", []):
            component = self.component_parser.parse(raw_component)
            test_case.components.append(component)
            test_case.issues.extend(component.issues)

        return test_case