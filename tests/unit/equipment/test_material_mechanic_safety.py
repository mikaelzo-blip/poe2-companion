"""Unit tests for material equipment build mechanic safety."""

from companion.equipment.mechanics import (
    KNOWN_SPECIAL_MECHANICS,
    ProjectionSupport,
    lookup_special_mechanic,
    normalize_mechanic_key,
)
from companion.state.provenance import VerificationState


def test_mechanic_registry_iron_reflexes_metadata():
    """Iron Reflexes must be registered with verified identity and unmodeled projection support."""
    assert "iron_reflexes" in KNOWN_SPECIAL_MECHANICS
    mech = lookup_special_mechanic("Iron Reflexes — Unscalable Value")
    assert mech.mechanic_id == "iron_reflexes"
    assert mech.canonical_name == "Iron Reflexes"
    assert mech.verification == VerificationState.VERIFIED
    assert mech.projection_support == ProjectionSupport.UNMODELED


def test_mechanic_key_normalization():
    """Special mechanic names normalize consistently to canonical snake_case keys."""
    assert normalize_mechanic_key("Iron Reflexes — Unscalable Value") == "iron_reflexes"
    assert normalize_mechanic_key("Iron Reflexes") == "iron_reflexes"
    assert normalize_mechanic_key("Chaos Inoculation") == "chaos_inoculation"
