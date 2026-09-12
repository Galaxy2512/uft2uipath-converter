from xml.sax.saxutils import quoteattr

from uft2uipath.ast import ConversionStatus, Step


class ActivityGenerator:
    def generate(self, step: Step) -> str:
        if step.status == ConversionStatus.UNSUPPORTED:
            return self._todo(step)

        name = quoteattr(str(step.name))

        if step.action == "Click":
            return f'<ui:Click DisplayName={name} />'

        if step.action == "Type Into":
            value = "" if step.value is None else str(step.value)
            return f'<ui:TypeInto DisplayName={name} Text={quoteattr(value)} />'

        if step.action == "Delay":
            return f'<Delay DisplayName={name} Duration="00:00:01" />'

        if step.action == "Log Message":
            value = step.name if step.value is None else str(step.value)
            return f'<ui:LogMessage DisplayName={name} Message={quoteattr(value)} />'

        return self._todo(step)

    def _todo(self, step: Step) -> str:
        original = step.raw.get("action", step.action or "Unknown")
        name = quoteattr(f"TODO: {step.name}")
        text = quoteattr(f"Unsupported UFT action: {original}")
        return f'<WriteLine DisplayName={name} Text={text} />'
