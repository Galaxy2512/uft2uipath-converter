# Converts one raw UFT action (name/action/target/value) into a Step AST
# object by resolving the action name through ActivityMappingRegistry to its
# UiPath activity equivalent, recording a ConversionIssue when the mapping
# carries caveats. Used by ComponentParser for the generic nested-dict path.

from uft2uipath.ast import ConversionIssue, IssueSeverity, Step, StepType
from uft2uipath.mapper.activity_mapping import ActivityMappingRegistry


class StepParser:
    """Builds a Step from an action name through ActivityMappingRegistry. Legacy path, not used by convert."""
    def __init__(self, registry: ActivityMappingRegistry | None = None):
        """Use the given registry, or the default one."""
        self.registry = registry or ActivityMappingRegistry()

    def parse_action(self, name: str, action: str, target: str | None = None, value=None, raw=None) -> Step:
        """Step for one UFT action with the mapping's status."""
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
