"""Unit tests for dynamic resistance target and overcap buffer calculations."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.baseline import BaselineSource, CharacterFact, CharacterStatBaseline
from companion.equipment.resistance import (
    ResistanceType,
    ResistanceTarget,
    evaluate_resistance_delta,
)


def test_resistance_targets_and_overcap_buffer():
    # Character with 115% raw fire res, max 75%
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base1",
        character_id="char1",
        anchored_loadout_revision=1,
        fire_res=75,
        fire_raw=115,
        max_fire_res=75,
    )

    target = ResistanceTarget(target_effective=75, target_overcap_buffer=20, max_res=75)

    # Swap losing 20% fire res (net -20)
    # raw drops from 115 to 95. Effective remains 75. Overcap remains 20 (still at target buffer).
    proj = evaluate_resistance_delta(baseline, ResistanceType.FIRE, delta=-20.0, target=target)

    assert proj.current_raw == 115
    assert proj.current_effective == 75
    assert proj.projected_raw == 95
    assert proj.projected_effective == 75
    assert proj.projected_overcap_buffer == 20
    assert proj.deficit_after == 0


def test_resistance_drop_breaking_cap():
    # Character with 80% raw fire res, max 75%
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base2",
        character_id="char1",
        anchored_loadout_revision=1,
        fire_res=75,
        fire_raw=80,
        max_fire_res=75,
    )

    target = ResistanceTarget(target_effective=75, target_overcap_buffer=20, max_res=75)

    # Swap losing 20% fire res (net -20)
    # raw drops from 80 to 60. Effective drops to 60. Deficit is 15%.
    proj = evaluate_resistance_delta(baseline, ResistanceType.FIRE, delta=-20.0, target=target)

    assert proj.current_raw == 80
    assert proj.current_effective == 75
    assert proj.projected_raw == 60
    assert proj.projected_effective == 60
    assert proj.projected_overcap_buffer == 0
    assert proj.deficit_after == 15
