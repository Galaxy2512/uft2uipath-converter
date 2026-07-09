from dataclasses import dataclass

from uft2uipath.ast import ConversionStatus


@dataclass(frozen=True)
class ActivityMapping:
    uft_action: str
    uipath_activity: str
    status: ConversionStatus = ConversionStatus.SUCCESS
    notes: str | None = None


class ActivityMappingRegistry:
    def __init__(self):
        self._mappings: dict[str, ActivityMapping] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
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
        key = self._normalize(uft_action)
        self._mappings[key] = ActivityMapping(
            uft_action=uft_action,
            uipath_activity=uipath_activity,
            status=status,
            notes=notes,
        )

    def resolve(self, uft_action: str) -> ActivityMapping:
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
        return value.strip().lower()