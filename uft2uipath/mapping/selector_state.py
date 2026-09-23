"""How far a selector has been verified: the states a selector binding can be in.

A selector derived from a UFT Object Repository is a proposal. Accepting it for
generation (by review or by confidence threshold) says only that the converter
may emit it, never that it matches the live application. The later states are
facts someone established with UiPath Studio and with a real run, so nothing in
the converter may set them by itself.

    candidate           proposed from UFT properties, not used for generation
    accepted_unverified accepted for generation; not checked against the application
    studio_validated    a person confirmed it in Studio (UI Explorer/validation)
    runtime_verified    a run against the application found the element

Deliberately no "verified" flag: it cannot say which of these is meant.
"""

CANDIDATE = "candidate"
ACCEPTED_UNVERIFIED = "accepted_unverified"
STUDIO_VALIDATED = "studio_validated"
RUNTIME_VERIFIED = "runtime_verified"
REJECTED = "rejected"

#: Every state, in increasing order of evidence.
STATES = (CANDIDATE, ACCEPTED_UNVERIFIED, STUDIO_VALIDATED, RUNTIME_VERIFIED, REJECTED)
#: States a binding may be emitted with; a person must have recorded the stronger ones.
GENERATION_STATES = (ACCEPTED_UNVERIFIED, STUDIO_VALIDATED, RUNTIME_VERIFIED)


def usable(binding) -> bool:
    """True if a binding may be used for generation: accepted, in a known state."""
    return (isinstance(binding, dict) and binding.get("accepted_for_generation") is True
            and binding.get("verification_status") in GENERATION_STATES)
