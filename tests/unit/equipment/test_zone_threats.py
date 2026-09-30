"""Unit tests for PoE2 Zone & Encounter Threat Matrix (TDD RED)."""

from __future__ import annotations

import pytest

from companion.equipment.zone_threats import (
    ZoneThreatMatrix,
    ZoneThreatProfile,
    get_zone_threat_profile,
)


def test_zone_matrix_resolves_g2_1_act2_vastiri():
    """Zone G2_1 must resolve to Act 2 Vastiri Outskirts with Fire/Physical threat."""
    profile = get_zone_threat_profile("G2_1")

    assert profile.act == 2
    assert "Vastiri" in profile.friendly_name or "Caravan" in profile.friendly_name
    assert "Fire" in profile.lethal_damage_types
    assert "Physical" in profile.lethal_damage_types
    assert profile.recommended_res.get("fire", 0) >= 30
    assert "Dreadnought" in profile.upcoming_boss or "Jamanra" in profile.upcoming_boss
    assert "Fire" in profile.survival_notes


def test_zone_matrix_resolves_g1_crypt_and_clear_fell():
    """Act 1 zones must resolve their specific threats."""
    p_crypt = get_zone_threat_profile("The Crypt")
    assert p_crypt.act == 1
    assert "Cold" in p_crypt.lethal_damage_types or "Physical" in p_crypt.lethal_damage_types

    p_fell = get_zone_threat_profile("Clear Fell")
    assert p_fell.act == 1


def test_zone_matrix_handles_unknown_zone_gracefully_with_level_fallback():
    """Unknown zone ID falls back to stage/level heuristic without crashing."""
    profile = get_zone_threat_profile("UNKNOWN_ZONE_999", character_level=19)
    assert profile.act == 2  # Level 19 is Act 2
    assert len(profile.lethal_damage_types) > 0
    assert profile.friendly_name is not None


def test_zone_matrix_detects_lethal_resistance_loss():
    """Verify check_lethal_resistance_loss flags dangerous drops for the current zone."""
    matrix = ZoneThreatMatrix()
    profile = matrix.get_profile("G2_1")

    # In G2_1, Fire is lethal. A -15% Fire Res drop is dangerous!
    is_dangerous, warning = profile.is_resistance_drop_dangerous(fire_delta=-15, cold_delta=0, lightning_delta=-4)
    assert is_dangerous is True
    assert "Fire" in warning

    # Safe drop: losing Cold res in a non-cold zone with minor delta
    is_dan_cold, _ = profile.is_resistance_drop_dangerous(fire_delta=0, cold_delta=-2, lightning_delta=0)
    assert is_dan_cold is False
