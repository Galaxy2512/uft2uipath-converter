# Package for mapping decisions between UFT and UiPath:
# - operation_registry.py: the UFT -> UiPath registry, one entry per parser node
#   type with its target activities, status and emitter (the source of truth)
# - inventory.py: operation inventory and migration coverage from generation reports
# - selector_candidates.py / acceptance.py: UiPath selector proposals from UFT
#   object properties and which of them are accepted for generation
