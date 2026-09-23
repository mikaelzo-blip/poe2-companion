"""Unit tests for marginal value weighting of resistances."""

import pytest
from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.resistance import (
    ResistanceType,
    ResistanceTarget,
    evaluate_resistance_delta,
)


def test_deficit_reduction_has_high_marginal_value():
    # 55% fire res (20% deficit under 75% cap)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_def",
        character_id="char_def",
        anchored_loadout_revision=1,
        fire_res=55,
        fire_raw=55,
        max_fire_res=75,
    )
    target = ResistanceTarget(target_effective=75, target_overcap_buffer=20, max_res=75)

    # Gaining +20 fire res cures deficit completely
    proj_cure = evaluate_resistance_delta(baseline, ResistanceType.FIRE, delta=+20.0, target=target)
    # Gaining +20 fire res when already at 100% (surplus)
    baseline_surplus = CharacterStatBaseline.create_partial(
        baseline_id="base_sur",
        character_id="char_sur",
        anchored_loadout_revision=1,
        fire_res=75,
        fire_raw=115,
        max_fire_res=75,
    )
    proj_surplus = evaluate_resistance_delta(baseline_surplus, ResistanceType.FIRE, delta=+20.0, target=target)

    assert proj_cure.marginal_value_score > proj_surplus.marginal_value_score * 3.0


def test_losing_excess_overcap_beyond_buffer_has_zero_penalty():
    # 135% fire res (60% overcap buffer)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_high",
        character_id="char_high",
        anchored_loadout_revision=1,
        fire_res=75,
        fire_raw=135,
        max_fire_res=75,
    )
    target = ResistanceTarget(target_effective=75, target_overcap_buffer=20, max_res=75)

    # Losing 25% fire res -> drops from 135 to 110 (overcap drops from 60 to 35, still above 20 buffer)
    proj = evaluate_resistance_delta(baseline, ResistanceType.FIRE, delta=-25.0, target=target)
    assert proj.projected_effective == 75
    # Marginal value penalty should be near 0 (score >= 0 or very small loss)
    assert proj.marginal_value_score >= -0.5
