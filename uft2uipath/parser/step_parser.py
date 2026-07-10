from uft2uipath.ast import ConversionIssue, IssueSeverity, Step, StepType
from uft2uipath.mapper.activity_mapping import ActivityMappingRegistry


class StepParser:
    def __init__(self, registry: ActivityMappingRegistry | None = None):
        self.registry = registry or ActivityMappingRegistry()

    def parse_action(self, name: str, action: str, target: str | None = None, value=None, raw=None) -> Step:
        mapping = self.registry.resolve(action)

        step = Step(
            name=name,
            type=StepType.ACTION,
            action=mapping.uipath_activity,
            target=target,
            value=value,
            status=mapping.status,
            raw=raw or {},
        )

        if mapping.notes:
            step.issues.append(
                ConversionIssue(
                    message=mapping.notes,
                    severity=IssueSeverity.WARNING,
                    source=action,
                    recommendation=mapping.uipath_activity,
                )
            )

        return step
