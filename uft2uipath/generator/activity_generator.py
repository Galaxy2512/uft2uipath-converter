from uft2uipath.ast import ConversionStatus, Step


class ActivityGenerator:
    def generate(self, step: Step) -> str:
        if step.status == ConversionStatus.UNSUPPORTED:
            return self._todo(step)

        if step.action == "Click":
            return f'<ui:Click DisplayName="{step.name}" />'

        if step.action == "Type Into":
            value = step.value or ""
            return f'<ui:TypeInto DisplayName="{step.name}" Text="{value}" />'

        if step.action == "Delay":
            return f'<Delay DisplayName="{step.name}" Duration="00:00:01" />'

        if step.action == "Log Message":
            value = step.value or step.name
            return f'<ui:LogMessage DisplayName="{step.name}" Message="{value}" />'

        return self._todo(step)

    def _todo(self, step: Step) -> str:
        original = step.raw.get("action", step.action or "Unknown")
        return f'<WriteLine DisplayName="TODO: {step.name}" Text="Unsupported UFT action: {original}" />'