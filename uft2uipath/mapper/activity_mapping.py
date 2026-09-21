# Registry mapping UFT action names (e.g. "Click", "Set", "Wait") to their
# UiPath activity equivalents, with a ConversionStatus and optional notes;
# unknown actions resolve to an unsupported "Manual Action Placeholder".

from dataclasses import dataclass

from uft2uipath.ast import ConversionStatus


@dataclass(frozen=True)
class ActivityMapping:
    """UFT action name -> UiPath activity name, with a conversion status."""
    uft_action: str
    uipath_activity: str
    status: ConversionStatus = ConversionStatus.SUCCESS
    notes: str | None = None


class ActivityMappingRegistry:
    """Legacy name-based mapping used by StepParser. Legacy path, not used by convert. The convert
    pipeline uses mapping.operation_registry.
    """
    def __init__(self):
        """Start with the default mappings."""
        self._mappings: dict[str, ActivityMapping] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the built-in action mappings."""
        self.register("Click", "Click")
        self.register("Set", "Type Into")
        self.register("Type", "Type Into")
        self.register("Wait", "Delay")
        self.register("Exist", "Element Exists")
        self.register("Reporter.ReportEvent", "Log Message", ConversionStatus.PARTIAL)

    def register(
        self,
        uft_action: str,
        uipath_activity: str,
        status: ConversionStatus = ConversionStatus.SUCCESS,
        notes: str | None = None,
    ) -> None:
        """Map a UFT action name to a UiPath activity."""
        key = self._normalize(uft_action)
        self._mappings[key] = ActivityMapping(
            uft_action=uft_action,
            uipath_activity=uipath_activity,
            status=status,
            notes=notes,
        )

    def resolve(self, uft_action: str) -> ActivityMapping:
        """Mapping of an action name; unknown actions map to a manual placeholder."""
        key = self._normalize(uft_action)

        if key in self._mappings:
            return self._mappings[key]

        return ActivityMapping(
            uft_action=uft_action,
            uipath_activity="Manual Action Placeholder",
            status=ConversionStatus.UNSUPPORTED,
            notes="No automatic UiPath mapping exists yet.",
        )

    def _normalize(self, value: str) -> str:
        """Case- and whitespace-insensitive key of an action name."""
        return value.strip().lower()