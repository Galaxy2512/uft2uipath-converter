"""What the migration layers agree on, before any of them decides anything.

The converter has three layers that must not depend on each other in a circle:

    parser / script_analysis   what the UFT script says
    mapping                    what it should become and whether that is trusted
    script_generation          the UiPath XAML that comes out

Everything both sides need to name the same thing lives here, and nothing here
imports from those layers:

- value_types.py    the types a migrated value can have, and their XAML names
- targets.py        the identity of a UFT object, browser types, input methods
- selector_state.py how far a selector has been verified

The rule is one-directional: mapping and script_generation import contracts,
contracts imports neither, and mapping never imports script_generation
(tests/unit/test_layering.py enforces it).
"""
