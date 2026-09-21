# Unit tests for ActivityMappingRegistry (uft2uipath/mapper/activity_mapping.py):
# covers resolving a known UFT action to its UiPath activity with SUCCESS status,
# and falling back to a "Manual Action Placeholder" with UNSUPPORTED status for
# unrecognized actions.
from uft2uipath.ast import ConversionStatus
from uft2uipath.mapper.activity_mapping import ActivityMappingRegistry


def test_resolve_known_mapping():
    registry = ActivityMappingRegistry()

    mapping = registry.resolve("Click")

    assert mapping.uipath_activity == "Click"
    assert mapping.status == ConversionStatus.SUCCESS


def test_resolve_unsupported_mapping():
    registry = ActivityMappingRegistry()

    mapping = registry.resolve("SomeUnknownUftAction")

    assert mapping.uipath_activity == "Manual Action Placeholder"
    assert mapping.status == ConversionStatus.UNSUPPORTED