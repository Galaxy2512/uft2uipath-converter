"""How far a mapping is trusted, in words every registry uses.

The operation, function and object-method registries all classify their entries
the same way, so a coverage report can count them together and a reader learns
the vocabulary once.

    supported          an implementation emits it
    no_effect          nothing to emit, by design (a declaration, a released object)
    planned            the target is known, nobody has written it yet
    requires_strategy  a decision is missing first, e.g. how to migrate arrays
    unsupported        no target semantics identified at all
"""

SUPPORTED = "supported"
NO_EFFECT = "no_effect"
PLANNED = "planned"
REQUIRES_STRATEGY = "requires_strategy"
UNSUPPORTED = "unsupported"

#: Every status, from most to least migrated.
STATUSES = (SUPPORTED, NO_EFFECT, PLANNED, REQUIRES_STRATEGY, UNSUPPORTED)
#: Statuses that promise an implementation; the rest document what is missing.
EMITTED = (SUPPORTED, NO_EFFECT)
