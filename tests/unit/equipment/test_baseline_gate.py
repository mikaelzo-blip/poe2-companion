"""Unit tests for baseline consistency gate."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.baseline import (
    BaselineSource,
    CharacterFact,
    CharacterStatBaseline,
)
from companion.equipment.baseline_gate import (
    BaselineConsistencyResult,
    check_baseline_consistency,
)


def test_baseline_consistency_gate_matching_revisions():
    fp = "canonical_fp_123"
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="c1",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=fp,
        life=1500,
        fire_res=75,
    )
    result = check_baseline_consistency(baseline, current_loadout_revision=1, current_loadout_fingerprint=fp)
    assert result.is_consistent is True
    assert result.reconciled_baseline.life.is_known is True
    assert result.reconciled_baseline.life.verification == VerificationState.VERIFIED
    assert len(result.notices) == 0


def test_baseline_consistency_gate_mismatched_revisions_marks_stale():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="c1",
        anchored_loadout_revision=1,
        life=1500,
        armour=4000,
        fire_res=75,
    )
    result = check_baseline_consistency(baseline, current_loadout_revision=2)
    assert result.is_consistent is False
    assert result.reconciled_baseline.life.verification == VerificationState.STALE
    assert result.reconciled_baseline.armour.verification == VerificationState.STALE
    assert result.reconciled_baseline.life.value == 1500  # Never zeroed!
    assert len(result.notices) > 0
    assert "revision 1" in result.notices[0]
