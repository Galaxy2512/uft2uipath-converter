"""How a UFT test object is identified, and what a binding may say about it.

A UFT object is named by its hierarchy: Browser("B").Page("P").WebEdit("User").
The same object is spelled differently in a repository, in a script line, in a
review file and in a binding, so every layer reduces it to the same key before
comparing. The rest here are the closed value sets a binding may use; they are
part of the contract, not of the generator, because a review file is written
against them long before any XAML exists.
"""

#: Target kinds a binding can describe; each selects its own activity family.
TARGET_KINDS = ("web", "desktop")
#: Browser types UiPath accepts for a web target. Never inferred from the UFT
#: script: UFT records that a browser was used, not which one the test needs.
BROWSER_TYPES = {"IE", "Firefox", "Chrome", "Edge", "Custom"}
#: How UiPath sends input to an element.
INPUT_METHODS = {"Simulate", "HardwareEvents", "SendWindowMessages"}
#: Closest to UFT's own replay: does not move the real mouse or keyboard.
DEFAULT_INPUT_METHOD = "Simulate"


def target_key(target: dict) -> tuple:
    """Identity of a UFT object: its hierarchy, however the binding spelled it.

    Accepts either a parsed path ([{"class": ..., "name": ...}, ...]) or the
    flat browser/page/object_type/logical_name form, and returns the same
    case-insensitive key for both.
    """
    path = target.get("path")
    if not path:
        path = [{"class": kind, "name": target.get(name)} for kind, name in
                (("Browser", "browser"), ("Page", "page"))] + [
            {"class": target.get("object_type"), "name": target.get("logical_name")}]
    steps = []
    for step in path:
        kind, name = step.get("class"), step.get("name")
        # A statement on the page repeats it as the target; keep one step for it.
        if kind and name and (kind.casefold(), name.casefold()) not in steps[-1:]:
            steps.append((kind.casefold(), name.casefold()))
    return tuple(steps)
