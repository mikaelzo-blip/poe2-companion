"""Unit tests for CharacterStatBaseline and provenanced CharacterFact models."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.baseline import (
    BaselineSource,
    CharacterFact,
    CharacterStatBaseline,
)


def test_baseline_source_enum():
    assert BaselineSource.MANUAL_USER_INPUT.value == "MANUAL_USER_INPUT"
    assert BaselineSource.MANUAL_SNAPSHOT.value == "MANUAL_SNAPSHOT"
    assert BaselineSource.DERIVED_CALCULATION.value == "DERIVED_CALCULATION"
    assert BaselineSource.GGG_OFFICIAL_API.value == "GGG_OFFICIAL_API"
    assert BaselineSource.UNKNOWN.value == "UNKNOWN"


def test_character_fact_unknown_by_default():
    fact = CharacterFact[int].unknown()
    assert fact.value is None
    assert fact.source == BaselineSource.UNKNOWN
    assert fact.verification == VerificationState.UNKNOWN
    assert fact.is_known is False


def test_character_fact_known():
    fact = CharacterFact[int].create(
        value=1500,
        source=BaselineSource.MANUAL_USER_INPUT,
        verification=VerificationState.VERIFIED,
    )
    assert fact.value == 1500
    assert fact.is_known is True
    assert fact.verification == VerificationState.VERIFIED

    stale_fact = fact.mark_stale()
    assert stale_fact.verification == VerificationState.STALE
    assert stale_fact.value == 1500


def test_baseline_omitted_stats_remain_unknown():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_001",
        character_id="char_merc",
        anchored_loadout_revision=1,
        life=1400,
        fire_res=75,
        fire_raw=115,
        max_fire_res=78,
    )
    assert baseline.anchored_loadout_revision == 1
    assert baseline.life.value == 1400
    assert baseline.life.is_known is True

    # Check Fire resistance breakdown
    assert baseline.effective_fire_res.value == 75
    assert baseline.raw_fire_res.value == 115
    assert baseline.max_fire_res.value == 78
    assert baseline.fire_overcap_buffer.value == 37  # 115 - 78 = 37

    # Omitted stats remain strictly UNKNOWN, never 0
    assert baseline.armour.value is None
    assert baseline.armour.verification == VerificationState.UNKNOWN
    assert baseline.armour.is_known is False

    assert baseline.cold_res_known is False
    assert baseline.effective_cold_res.value is None
    assert baseline.effective_cold_res.verification == VerificationState.UNKNOWN

    assert baseline.strength.value is None
    assert baseline.strength.verification == VerificationState.UNKNOWN
