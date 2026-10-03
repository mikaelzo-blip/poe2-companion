import pytest

from companion.equipment.rules import BuildProgressionStage
from companion.equipment.tactical_advisor import evaluate_tactical_map_hazards

def test_tactical_map_hazard_ignited_ground_pre_swap():
    """Pre-swap stage should not warn about ignited ground."""
    warnings = evaluate_tactical_map_hazards(
        map_modifiers=["Area has patches of Ignited Ground"],
        stage=BuildProgressionStage.LEVELING_33_51,
        has_ignite_immunity=False
    )
    assert not warnings

def test_tactical_map_hazard_ignited_ground_post_swap_no_immunity():
    """Post-swap stage without immunity should warn about ignited ground."""
    warnings = evaluate_tactical_map_hazards(
        map_modifiers=["Area has patches of Ignited Ground"],
        stage=BuildProgressionStage.SWAP_52,
        has_ignite_immunity=False
    )
    assert len(warnings) == 1
    assert "Ignited Ground" in warnings[0]
    assert "Tornado" in warnings[0]

def test_tactical_map_hazard_ignited_ground_post_swap_with_immunity():
    """Post-swap stage with immunity should still warn about ignited ground (it affects the oil, not just the player)."""
    warnings = evaluate_tactical_map_hazards(
        map_modifiers=["Area has patches of Ignited Ground"],
        stage=BuildProgressionStage.ENDGAME,
        has_ignite_immunity=True
    )
    assert len(warnings) == 1
    assert "Ignited Ground" in warnings[0]
    assert "Tornado" in warnings[0]

def test_tactical_map_hazard_player_ignite_risk_no_immunity():
    """Post-swap stage without immunity should warn about player ignite risk."""
    warnings = evaluate_tactical_map_hazards(
        map_modifiers=["Monsters Ignite on Hit"],
        stage=BuildProgressionStage.SWAP_52,
        has_ignite_immunity=False
    )
    assert len(warnings) == 1
    assert "Ignite Immune" in warnings[0]
    assert "Thawing Charm" in warnings[0]

def test_tactical_map_hazard_player_ignite_risk_with_immunity():
    """Post-swap stage with immunity should NOT warn about player ignite risk."""
    warnings = evaluate_tactical_map_hazards(
        map_modifiers=["Monsters Ignite on Hit"],
        stage=BuildProgressionStage.SWAP_52,
        has_ignite_immunity=True
    )
    assert not warnings
