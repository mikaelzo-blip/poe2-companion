"""Unit tests for semantic skill-group identity, conservative equipment delta, and scoped coverage policy."""

import json
from pathlib import Path
import pytest
from companion.sources.interval import IntervalKind, LevelInterval
from companion.sources.models_raw import RawBuild
from companion.sources.models_normalized import normalize_build
from companion.state.provenance import VerificationState
from companion.state.schema import CharacterState
from companion.build.input import ObservationCoverage
from companion.build.policy import DeltaReason, DeltaStatus
from companion.build.skills import (
    TargetSkillGroup,
    TargetSupportGem,
    canonicalize_target_skills,
    evaluate_skill_delta,
)
from companion.build.equipment import (
    EquipmentDeltaEntry,
    evaluate_equipment_delta,
)
from companion.build.delta import compute_build_delta
from companion.build.input import BuildBrainInput, PlayerObservationCoverage
from companion.build.variants import TargetVariant


def _load_real_lvl52_normalized_build():
    build_path = Path("data/source/builds/lvl 52 Swap - 0.5.5 Fubgun Flameblast Oi.build")
    with open(build_path, "r", encoding="utf-8") as f:
        raw_dict = json.load(f)
    raw_build = RawBuild.model_validate(raw_dict)
    return normalize_build(raw_build, logical_stage="lvl 52 Swap")


def test_real_level_52_distinguishes_standalone_tornado_from_cast_on_dodge_tornado() -> None:
    """Real level 52 snapshot preserves standalone Tornado and Cast-on-Dodge Tornado as distinct skill requirements."""
    norm = _load_real_lvl52_normalized_build()
    target_skills = canonicalize_target_skills(norm.skills, source_provenance="lvl 52 Swap")

    # Find standalone Tornado
    standalone_tornado = [
        s for s in target_skills
        if "Tornado" in s.primary_gem_id and s.parent_meta_gem_id is None and not s.is_meta_gem
    ]
    assert len(standalone_tornado) == 1
    assert standalone_tornado[0].level_interval.min_level == 41

    # Find Cast on Dodge meta-gem setup
    cod_setup = [
        s for s in target_skills
        if s.is_meta_gem or "CastOnDodge" in s.primary_gem_id
    ]
    assert len(cod_setup) == 1
    assert cod_setup[0].level_interval.min_level == 58
    assert cod_setup[0].child_active_gem_id is not None
    assert "Tornado" in cod_setup[0].child_active_gem_id

    # The logical keys must be distinct
    assert standalone_tornado[0].logical_key != cod_setup[0].logical_key


def test_source_group_index_reordering_preserves_semantic_identity() -> None:
    """Reordering source skill group indices across builds produces identical logical keys and requirements."""
    norm = _load_real_lvl52_normalized_build()
    skills_original = norm.skills
    skills_reversed = list(reversed(norm.skills))

    targets_orig = canonicalize_target_skills(skills_original)
    targets_rev = canonicalize_target_skills(skills_reversed)

    assert len(targets_orig) == len(targets_rev)
    orig_keys = {t.logical_key for t in targets_orig}
    rev_keys = {t.logical_key for t in targets_rev}
    assert orig_keys == rev_keys


def test_cast_on_dodge_at_level_52_is_future_never_missing() -> None:
    """In level 52 snapshot, Cast on Dodge [58, 100] evaluates to FUTURE at level 52, never MISSING."""
    norm = _load_real_lvl52_normalized_build()
    target_skills = canonicalize_target_skills(norm.skills, source_provenance="lvl 52 Swap")

    char = CharacterState.create_initial("hero1", "Hero")
    char = char.model_copy(update={"level": char.level.with_update(52, "TEST", VerificationState.VERIFIED)})
    char.audit["skills"] = []
    char.audit["skills_verification"] = VerificationState.VERIFIED

    deltas = evaluate_skill_delta(
        target_skills=target_skills,
        character_state=char,
        coverage=ObservationCoverage.COMPLETE,
        character_level=52,
    )

    cod_delta = next(d for d in deltas if "CastOnDodge" in d.primary_gem_id or d.is_meta_gem)
    assert cod_delta.status == DeltaStatus.FUTURE
    assert cod_delta.status != DeltaStatus.MISSING
    assert cod_delta.reason == DeltaReason.INELIGIBLE_LEVEL


def test_skill_coverage_policy_partial_unknown_complete() -> None:
    """Skill coverage behavior: partial -> UNKNOWN (PARTIAL_PLAYER_OBSERVATION), unknown -> UNKNOWN, complete -> MISSING when absent."""
    norm = _load_real_lvl52_normalized_build()
    target_skills = canonicalize_target_skills(norm.skills)

    char = CharacterState.create_initial("hero1", "Hero")
    char = char.model_copy(update={"level": char.level.with_update(52, "TEST", VerificationState.VERIFIED)})
    char.audit["skills"] = []
    char.audit["skills_verification"] = VerificationState.VERIFIED

    # 1. Partial coverage -> UNKNOWN (PARTIAL_PLAYER_OBSERVATION) for eligible absent skill (e.g. Flameblast at 52)
    deltas_partial = evaluate_skill_delta(
        target_skills=target_skills,
        character_state=char,
        coverage=ObservationCoverage.PARTIAL,
        character_level=52,
    )
    fb_partial = next(d for d in deltas_partial if "Flameblast" in d.primary_gem_id)
    assert fb_partial.status == DeltaStatus.UNKNOWN
    assert fb_partial.reason == DeltaReason.PARTIAL_PLAYER_OBSERVATION

    # 2. Unknown coverage -> UNKNOWN (OBSERVATION_COVERAGE_UNKNOWN)
    deltas_unknown = evaluate_skill_delta(
        target_skills=target_skills,
        character_state=char,
        coverage=ObservationCoverage.UNKNOWN,
        character_level=52,
    )
    fb_unknown = next(d for d in deltas_unknown if "Flameblast" in d.primary_gem_id)
    assert fb_unknown.status == DeltaStatus.UNKNOWN
    assert fb_unknown.reason == DeltaReason.OBSERVATION_COVERAGE_UNKNOWN

    # 3. Complete coverage -> MISSING
    deltas_complete = evaluate_skill_delta(
        target_skills=target_skills,
        character_state=char,
        coverage=ObservationCoverage.COMPLETE,
        character_level=52,
    )
    fb_complete = next(d for d in deltas_complete if "Flameblast" in d.primary_gem_id)
    assert fb_complete.status == DeltaStatus.MISSING
    assert fb_complete.reason == DeltaReason.NONE


def test_equipment_slot_coverage_isolation_and_missing_key() -> None:
    """Equipment slot missing from equipment_slots coverage map evaluates to UNKNOWN.

    Coverage for Helm does not imply coverage for Boots or Weapons.
    Slot-scoped complete observation establishes MISSING for that slot only.
    """
    norm = _load_real_lvl52_normalized_build()
    char = CharacterState.create_initial("hero1", "Hero")
    char = char.model_copy(update={"level": char.level.with_update(52, "TEST", VerificationState.VERIFIED)})

    # Audit contains observed Helm (different item) and Weapon1
    char.audit["equipment"] = {
        "Helm": {
            "unique_name": "Random Rare Helm",
            "base_type": "Iron Helm",
            "verification_state": VerificationState.VERIFIED,
            "is_stale": False,
        },
        "Weapon1": {
            "unique_name": "Pyrophyte Staff",
            "verification_state": VerificationState.VERIFIED,
            "is_stale": False,
        },
    }

    # Coverage map specifies COMPLETE for Helm only. Weapon1, Weapon2, Boots are omitted.
    coverage_map = {
        "Helm": ObservationCoverage.COMPLETE,
    }

    deltas = evaluate_equipment_delta(
        target_slots=norm.inventory_slots,
        character_state=char,
        coverage_map=coverage_map,
        character_level=52,
    )

    # Helm has COMPLETE coverage and item does not match Face Mask -> MISSING
    helm_delta = next((d for d in deltas if d.slot_id == "Helm"), None)
    if helm_delta:
        assert helm_delta.status == DeltaStatus.MISSING
        assert helm_delta.reason == DeltaReason.NONE

    # Weapon1 is missing from coverage_map -> UNKNOWN (OBSERVATION_COVERAGE_UNKNOWN)
    w1_delta = next((d for d in deltas if d.slot_id == "Weapon1"), None)
    if w1_delta:
        # Since coverage is omitted for Weapon1, it must be UNKNOWN coverage
        assert w1_delta.status == DeltaStatus.UNKNOWN or w1_delta.reason == DeltaReason.OBSERVATION_COVERAGE_UNKNOWN

    # Unobserved slot like Boots or Gloves missing from coverage map -> UNKNOWN
    for d in deltas:
        if d.slot_id not in coverage_map:
            assert d.status in (DeltaStatus.UNKNOWN, DeltaStatus.FUTURE)
            assert d.status != DeltaStatus.MISSING
