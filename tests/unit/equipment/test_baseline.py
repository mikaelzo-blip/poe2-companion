"""Unit tests for baseline double-count protection, UNKNOWN preservation, and partial projection honesty."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.baseline import (
    BaselineSource,
    CharacterFact,
    CharacterStatBaseline,
)


def test_baseline_double_count_protection():
    # User inputs character sheet total Armour 4200
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_dc",
        character_id="char_1",
        anchored_loadout_revision=1,
        armour=4200,
    )
    # The baseline value is exactly 4200, not altered by separate item stats
    assert baseline.armour.value == 4200
    assert baseline.armour.is_known is True


def test_baseline_omitted_stats_never_become_zero():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_partial",
        character_id="char_1",
        anchored_loadout_revision=1,
        life=1200,
        fire_res=70,
    )
    # Provided
    assert baseline.life.value == 1200
    assert baseline.effective_fire_res.value == 70

    # Unprovided stats are UNKNOWN, not 0
    assert baseline.effective_cold_res.value is None
    assert baseline.effective_cold_res.verification == VerificationState.UNKNOWN
    assert baseline.effective_lightning_res.value is None
    assert baseline.effective_lightning_res.verification == VerificationState.UNKNOWN
    assert baseline.effective_chaos_res.value is None
    assert baseline.effective_chaos_res.verification == VerificationState.UNKNOWN
    assert baseline.evasion.value is None
    assert baseline.evasion.verification == VerificationState.UNKNOWN
    assert baseline.energy_shield.value is None
    assert baseline.energy_shield.verification == VerificationState.UNKNOWN
    assert baseline.movement_speed.value is None
    assert baseline.movement_speed.verification == VerificationState.UNKNOWN


def test_partial_projection_honesty_unknown_stat():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_p",
        character_id="char_1",
        anchored_loadout_revision=1,
        # Lightning res omitted -> UNKNOWN
    )
    assert baseline.effective_lightning_res.is_known is False
    assert baseline.effective_lightning_res.value is None
