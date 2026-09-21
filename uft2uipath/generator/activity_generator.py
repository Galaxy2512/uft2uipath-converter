# Renders a single neutral Step into its equivalent UiPath activity as a raw
# XAML string snippet (Click, TypeInto, Delay, LogMessage), falling back to a
# WriteLine TODO placeholder for unsupported or unrecognized UFT actions.

from xml.sax.saxutils import quoteattr

from uft2uipath.ast import ConversionStatus, Step


class ActivityGenerator:
    """Legacy XAML snippets for model steps; unsupported steps become TODO placeholders. Legacy
    path, not used by convert.
    """
    def generate(self, step: Step) -> str:
        """XAML snippet for one step."""
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
        """Placeholder snippet preserving an unsupported UFT action."""
        original = step.raw.get("action", step.action or "Unknown")
        name = quoteattr(f"TODO: {step.name}")
        text = quoteattr(f"Unsupported UFT action: {original}")
        return f'<WriteLine DisplayName={name} Text={text} />'
