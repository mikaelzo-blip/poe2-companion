"""Invariant property tests explicitly proving the 20 core domain invariants of M2 Offline Build Brain."""

import json
from pathlib import Path
import pytest
from companion.sources.models_raw import RawBuild, RawPassiveEntry
from companion.sources.models_normalized import normalize_build, WeaponSetContext
from companion.sources.interval import IntervalKind, LevelInterval
from companion.state.provenance import VerificationState
from companion.state.schema import CharacterState
from companion.build.validation import InvalidCharacterLevelError, validate_character_level
from companion.build.eligibility import EligibilityState, evaluate_eligibility
from companion.build.progression import ProgressionPhase, resolve_progression_phase
from companion.build.variants import (
    TargetVariant,
    TargetVariantResolution,
    VariantResolutionStatus,
    resolve_target_variant,
)
from companion.build.input import (
    BuildBrainInput,
    ObservationCoverage,
    PlayerObservationCoverage,
)
from companion.build.policy import DeltaReason, DeltaStatus, evaluate_delta_item
from companion.build.passives import (
    CanonicalTargetPassive,
    canonicalize_target_passives,
    evaluate_passive_delta,
)
from companion.build.skills import (
    TargetSkillGroup,
    canonicalize_target_skills,
    evaluate_skill_delta,
)
from companion.build.equipment import evaluate_equipment_delta
from companion.build.delta import compute_build_delta


def _load_build(filename: str, logical_stage: str):
    path = Path("data/source/builds") / filename
    with open(path, "r", encoding="utf-8") as f:
        raw_dict = json.load(f)
    raw = RawBuild.model_validate(raw_dict)
    return normalize_build(raw, logical_stage=logical_stage)


# Invariant 1: VERIFIED passive state with coverage UNKNOWN evaluates to UNKNOWN (OBSERVATION_COVERAGE_UNKNOWN), never MISSING
def test_invariant_01_verified_passive_unknown_coverage_never_missing() -> None:
    target = [
        CanonicalTargetPassive(
            key=("p1", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="p1",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            source_occurrences=1,
            source_indices=[0],
        )
    ]
    char = CharacterState.create_initial("h1", "Hero")
    char.audit["passives"] = []
    char.audit["passives_verification"] = VerificationState.VERIFIED

    delta = evaluate_passive_delta(target, char, coverage=ObservationCoverage.UNKNOWN)
    assert delta[0].status == DeltaStatus.UNKNOWN
    assert delta[0].status != DeltaStatus.MISSING
    assert delta[0].reason == DeltaReason.OBSERVATION_COVERAGE_UNKNOWN


# Invariant 2: Fresh VERIFIED but PARTIAL passive observation evaluates to UNKNOWN (PARTIAL_PLAYER_OBSERVATION), never MISSING
def test_invariant_02_verified_passive_partial_coverage_never_missing() -> None:
    target = [
        CanonicalTargetPassive(
            key=("p1", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="p1",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            source_occurrences=1,
            source_indices=[0],
        )
    ]
    char = CharacterState.create_initial("h1", "Hero")
    char.audit["passives"] = []
    char.audit["passives_verification"] = VerificationState.VERIFIED

    delta = evaluate_passive_delta(target, char, coverage=ObservationCoverage.PARTIAL)
    assert delta[0].status == DeltaStatus.UNKNOWN
    assert delta[0].status != DeltaStatus.MISSING
    assert delta[0].reason == DeltaReason.PARTIAL_PLAYER_OBSERVATION


# Invariant 3: Complete fresh passive observation with target absent evaluates to MISSING
def test_invariant_03_complete_fresh_passive_absent_evaluates_missing() -> None:
    target = [
        CanonicalTargetPassive(
            key=("p1", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="p1",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            source_occurrences=1,
            source_indices=[0],
        )
    ]
    char = CharacterState.create_initial("h1", "Hero")
    char.audit["passives"] = []
    char.audit["passives_verification"] = VerificationState.VERIFIED

    delta = evaluate_passive_delta(target, char, coverage=ObservationCoverage.COMPLETE)
    assert delta[0].status == DeltaStatus.MISSING
    assert delta[0].reason == DeltaReason.NONE


# Invariant 4: Skill coverage behaves equivalently (UNKNOWN coverage -> UNKNOWN, PARTIAL -> PARTIAL_PLAYER_OBSERVATION, COMPLETE -> MISSING when absent)
def test_invariant_04_skill_coverage_behaves_equivalently() -> None:
    target = [
        TargetSkillGroup(
            logical_key=("s1", None),
            primary_gem_id="s1",
            level_interval=LevelInterval(kind=IntervalKind.UNRESTRICTED),
            source_group_index=0,
        )
    ]
    char = CharacterState.create_initial("h1", "Hero")
    char.audit["skills"] = []
    char.audit["skills_verification"] = VerificationState.VERIFIED

    d_unk = evaluate_skill_delta(target, char, coverage=ObservationCoverage.UNKNOWN)[0]
    assert d_unk.status == DeltaStatus.UNKNOWN
    assert d_unk.reason == DeltaReason.OBSERVATION_COVERAGE_UNKNOWN

    d_part = evaluate_skill_delta(target, char, coverage=ObservationCoverage.PARTIAL)[0]
    assert d_part.status == DeltaStatus.UNKNOWN
    assert d_part.reason == DeltaReason.PARTIAL_PLAYER_OBSERVATION

    d_comp = evaluate_skill_delta(target, char, coverage=ObservationCoverage.COMPLETE)[0]
    assert d_comp.status == DeltaStatus.MISSING
    assert d_comp.reason == DeltaReason.NONE


# Invariant 5: Equipment slot missing from equipment_slots coverage map evaluates to UNKNOWN (OBSERVATION_COVERAGE_UNKNOWN)
def test_invariant_05_equipment_slot_missing_from_coverage_map_evaluates_unknown() -> None:
    char = CharacterState.create_initial("h1", "Hero")
    char.audit["equipment"] = {
        "Boots": {"unique_name": "Wanderlust", "verification_state": VerificationState.VERIFIED}
    }
    slots = [{"inventory_id": "Boots", "level_interval": None, "unique_name": "Seven-League Step"}]

    delta = evaluate_equipment_delta(slots, char, coverage_map={})[0]
    assert delta.status == DeltaStatus.UNKNOWN
    assert delta.reason == DeltaReason.OBSERVATION_COVERAGE_UNKNOWN


# Invariant 6: One equipment slot COMPLETE establishes absence (MISSING) for that slot only
def test_invariant_06_one_slot_complete_establishes_absence_for_that_slot_only() -> None:
    char = CharacterState.create_initial("h1", "Hero")
    char.audit["equipment"] = {
        "Helm": {"unique_name": "Iron Cap", "verification_state": VerificationState.VERIFIED},
        "Boots": {"unique_name": "Wanderlust", "verification_state": VerificationState.VERIFIED},
    }
    slots = [
        {"inventory_id": "Helm", "level_interval": None, "unique_name": "Crown of Eyes"},
        {"inventory_id": "Boots", "level_interval": None, "unique_name": "Seven-League Step"},
    ]

    coverage_map = {"Helm": ObservationCoverage.COMPLETE}
    deltas = evaluate_equipment_delta(slots, char, coverage_map=coverage_map)
    d_helm = next(d for d in deltas if d.slot_id == "Helm")
    d_boots = next(d for d in deltas if d.slot_id == "Boots")

    assert d_helm.status == DeltaStatus.MISSING
    assert d_boots.status == DeltaStatus.UNKNOWN


# Invariant 7: Coverage for helmet must not imply coverage for boots or weapons
def test_invariant_07_helmet_coverage_does_not_imply_boots_or_weapons() -> None:
    char = CharacterState.create_initial("h1", "Hero")
    char.audit["equipment"] = {
        "Helm": {"unique_name": "Crown of Eyes", "verification_state": VerificationState.VERIFIED},
    }
    slots = [
        {"inventory_id": "Helm", "level_interval": None, "unique_name": "Crown of Eyes"},
        {"inventory_id": "Boots", "level_interval": None, "unique_name": "Seven-League Step"},
        {"inventory_id": "Weapon1", "level_interval": None, "unique_name": "Staff"},
    ]
    coverage_map = {"Helm": ObservationCoverage.COMPLETE}
    deltas = evaluate_equipment_delta(slots, char, coverage_map=coverage_map)

    for d in deltas:
        if d.slot_id != "Helm":
            assert d.status != DeltaStatus.MISSING


# Invariant 8: Coverage must never be inferred from VerificationState.VERIFIED
def test_invariant_08_coverage_never_inferred_from_verified() -> None:
    char = CharacterState.create_initial("h1", "Hero")
    char.audit["passives"] = []
    char.audit["passives_verification"] = VerificationState.VERIFIED

    # With default PlayerObservationCoverage, coverage is UNKNOWN
    target = [
        CanonicalTargetPassive(
            key=("p1", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="p1",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            source_occurrences=1,
            source_indices=[0],
        )
    ]
    d = evaluate_passive_delta(target, char)[0]
    assert d.status == DeltaStatus.UNKNOWN
    assert d.reason == DeltaReason.OBSERVATION_COVERAGE_UNKNOWN


# Invariant 9: Source skill group indices reordered while semantic groups remain identical produces unchanged logical interpretation
def test_invariant_09_source_skill_group_indices_reordering_invariance() -> None:
    b = _load_build("lvl 52 Swap - 0.5.5 Fubgun Flameblast Oi.build", "lvl 52 Swap")
    orig_skills = b.skills
    rev_skills = list(reversed(b.skills))

    t_orig = canonicalize_target_skills(orig_skills)
    t_rev = canonicalize_target_skills(rev_skills)

    assert {t.logical_key for t in t_orig} == {t.logical_key for t in t_rev}


# Invariant 10: HIGH_END with selected_target_variant=None returns TargetVariantResolution(status=UNRESOLVED, reason=NO_EXPLICIT_HIGH_END_VARIANT), never silently defaulting to LVL85
def test_invariant_10_high_end_unselected_variant_returns_unresolved_never_lvl85() -> None:
    res = resolve_target_variant(ProgressionPhase.HIGH_END, None)
    assert res.status == VariantResolutionStatus.UNRESOLVED
    assert res.variant is None
    assert res.reason == "NO_EXPLICIT_HIGH_END_VARIANT"


# Invariant 11: 69–84 fallback is deterministic (binds to lvl 53-68 with fallback provenance)
def test_invariant_11_fallback_69_84_deterministic() -> None:
    for lvl in range(69, 85):
        res = resolve_progression_phase(lvl)
        assert res.phase == ProgressionPhase.LEVELING_69_84_FALLBACK
        assert res.target_snapshot_name == "lvl 53-68"
        assert res.provenance == "COMPANION_FALLBACK_SOURCE_GAP"


# Invariant 12: Duplicate raw passive rows do not create duplicate allocation requirements
def test_invariant_12_duplicate_raw_passive_rows_clean_canonicalization() -> None:
    entries = [
        RawPassiveEntry(id="dex30", weapon_set=None),
        RawPassiveEntry(id="dex30", weapon_set=None),
        RawPassiveEntry(id="dex30", weapon_set=None),
    ]
    canonical, conflicts = canonicalize_target_passives(entries)
    assert len(canonical) == 1
    assert canonical[0].required_count == 1
    assert canonical[0].source_occurrences == 3
    assert len(conflicts) == 0


# Invariant 13: Conflicting duplicate passive metadata produces structured CONFLICTING_EVIDENCE
def test_invariant_13_conflicting_duplicate_passive_metadata_produces_conflicts() -> None:
    entries = [
        {"id": "node_x", "weapon_set": None, "metadata": {"power": 10}},
        {"id": "node_x", "weapon_set": None, "metadata": {"power": 20}},
    ]
    canonical, conflicts = canonicalize_target_passives(entries)
    assert len(canonical) == 1
    assert canonical[0].has_conflict is True
    assert len(conflicts) == 1
    assert conflicts[0].status == "CONFLICTING_EVIDENCE"


# Invariant 14: Distinct weapon-set contexts produce separate passive logical identities
def test_invariant_14_distinct_weapon_set_contexts_produce_separate_identities() -> None:
    entries = [
        RawPassiveEntry(id="fire62", weapon_set=None),
        RawPassiveEntry(id="fire62", weapon_set=1),
        RawPassiveEntry(id="fire62", weapon_set=2),
    ]
    canonical, _ = canonicalize_target_passives(entries)
    assert len(canonical) == 3
    keys = {c.key for c in canonical}
    assert ("fire62", WeaponSetContext.DEFAULT_OR_SHARED) in keys
    assert ("fire62", WeaponSetContext.SPECIALISATION_1) in keys
    assert ("fire62", WeaponSetContext.SPECIALISATION_2) in keys


# Invariant 15: Standalone Tornado and Cast on Dodge -> Tornado remain distinct skill requirements
def test_invariant_15_standalone_vs_cast_on_dodge_tornado_distinct() -> None:
    b = _load_build("lvl 52 Swap - 0.5.5 Fubgun Flameblast Oi.build", "lvl 52 Swap")
    skills = canonicalize_target_skills(b.skills)
    standalone = [s for s in skills if "Tornado" in s.primary_gem_id and not s.is_meta_gem]
    cod = [s for s in skills if s.is_meta_gem]
    assert len(standalone) == 1
    assert len(cod) == 1
    assert standalone[0].logical_key != cod[0].logical_key


# Invariant 16: Cast on Dodge at level 52 evaluates to FUTURE, never MISSING
def test_invariant_16_cast_on_dodge_level_52_is_future_never_missing() -> None:
    b = _load_build("lvl 52 Swap - 0.5.5 Fubgun Flameblast Oi.build", "lvl 52 Swap")
    skills = canonicalize_target_skills(b.skills)
    char = CharacterState.create_initial("h1", "Hero")
    char = char.model_copy(update={"level": char.level.with_update(52, "TEST", VerificationState.VERIFIED)})
    char.audit["skills"] = []
    char.audit["skills_verification"] = VerificationState.VERIFIED

    deltas = evaluate_skill_delta(skills, char, coverage=ObservationCoverage.COMPLETE, character_level=52)
    cod_delta = next(d for d in deltas if d.is_meta_gem or "CastOnDodge" in d.primary_gem_id)
    assert cod_delta.status == DeltaStatus.FUTURE
    assert cod_delta.status != DeltaStatus.MISSING


# Invariant 17: Stale or unobserved player data evaluates to UNKNOWN with reason, never MISSING
def test_invariant_17_stale_or_unobserved_evaluates_unknown_never_missing() -> None:
    char_unobserved = CharacterState.create_initial("h1", "Hero")
    target = [
        CanonicalTargetPassive(
            key=("p1", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="p1",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            source_occurrences=1,
            source_indices=[0],
        )
    ]
    d_unobs = evaluate_passive_delta(target, char_unobserved, coverage=ObservationCoverage.COMPLETE)[0]
    assert d_unobs.status == DeltaStatus.UNKNOWN
    assert d_unobs.status != DeltaStatus.MISSING
    assert d_unobs.reason == DeltaReason.UNOBSERVED_SUBSYSTEM

    char_stale = CharacterState.create_initial("h2", "Hero")
    char_stale.audit["passives"] = []
    char_stale.audit["passives_is_stale"] = True
    char_stale.audit["passives_verification"] = VerificationState.STALE
    d_stale = evaluate_passive_delta(target, char_stale, coverage=ObservationCoverage.COMPLETE)[0]
    assert d_stale.status == DeltaStatus.UNKNOWN
    assert d_stale.status != DeltaStatus.MISSING
    assert d_stale.reason == DeltaReason.STALE_PLAYER_STATE


# Invariant 18: Invalid character levels (<= 0 or > 100) are rejected with InvalidCharacterLevelError
def test_invariant_18_invalid_character_levels_rejected() -> None:
    for bad_lvl in [0, -1, -50, 101, 150]:
        with pytest.raises(InvalidCharacterLevelError):
            validate_character_level(bad_lvl)
        with pytest.raises(InvalidCharacterLevelError):
            resolve_progression_phase(bad_lvl)


# Invariant 19: Determinism: identical inputs produce identical BuildDeltaResult
def test_invariant_19_determinism_identical_inputs_identical_output() -> None:
    b = _load_build("lvl 1-14 - 0.5.5 Fubgun Flameblast Oil G.build", "lvl 1-14")
    char = CharacterState.create_initial("h1", "Hero")
    brain_input = BuildBrainInput(
        character_state=char,
        observation_coverage=PlayerObservationCoverage(),
    )
    res1 = compute_build_delta(brain_input, b, manifest_sha256="test_sha")
    res2 = compute_build_delta(brain_input, b, manifest_sha256="test_sha")
    assert res1.model_dump() == res2.model_dump()


# Invariant 20: Changing high-end target variant adds and removes requirements non-monotonically
def test_invariant_20_changing_high_end_variant_adds_and_removes_non_monotonically() -> None:
    mb_build = _load_build("Mageblood - 0.5.5 Fubgun Flameblast Oil.build", "Mageblood")
    dot_build = _load_build("DoT Cap - 0.5.5 Fubgun Flameblast Oil Gr.build", "DoT Cap")

    mb_passives, _ = canonicalize_target_passives(mb_build.passives)
    dot_passives, _ = canonicalize_target_passives(dot_build.passives)

    mb_keys = {p.key for p in mb_passives}
    dot_keys = {p.key for p in dot_passives}

    # They are non-monotonic: neither is a superset of the other
    assert not mb_keys.issubset(dot_keys)
    assert not dot_keys.issubset(mb_keys)
    assert len(mb_keys - dot_keys) > 0  # Passives unique to Mageblood
    assert len(dot_keys - mb_keys) > 0  # Passives unique to DoT Cap


def test_evidence_quality_matrix() -> None:
    """Verify evidence quality matrix across all VerificationStates for ACTIVE requirement with COMPLETE coverage."""
    # Absent cases:
    # VERIFIED and CORROBORATED establish definitive absence (MISSING)
    assert evaluate_delta_item(
        target_eligibility=EligibilityState.ACTIVE,
        player_observation_exists=True,
        is_stale=False,
        verification_state=VerificationState.VERIFIED,
        observation_coverage=ObservationCoverage.COMPLETE,
        is_entity_present=False,
    ) == (DeltaStatus.MISSING, DeltaReason.NONE)

    assert evaluate_delta_item(
        target_eligibility=EligibilityState.ACTIVE,
        player_observation_exists=True,
        is_stale=False,
        verification_state=VerificationState.CORROBORATED,
        observation_coverage=ObservationCoverage.COMPLETE,
        is_entity_present=False,
    ) == (DeltaStatus.MISSING, DeltaReason.NONE)

    # SINGLE_SOURCE cannot prove absence
    assert evaluate_delta_item(
        target_eligibility=EligibilityState.ACTIVE,
        player_observation_exists=True,
        is_stale=False,
        verification_state=VerificationState.SINGLE_SOURCE,
        observation_coverage=ObservationCoverage.COMPLETE,
        is_entity_present=False,
    ) == (DeltaStatus.UNKNOWN, DeltaReason.INSUFFICIENT_EVIDENCE_RELIABILITY)

    # STALE evaluates to STALE_PLAYER_STATE
    assert evaluate_delta_item(
        target_eligibility=EligibilityState.ACTIVE,
        player_observation_exists=True,
        is_stale=False,
        verification_state=VerificationState.STALE,
        observation_coverage=ObservationCoverage.COMPLETE,
        is_entity_present=False,
    ) == (DeltaStatus.UNKNOWN, DeltaReason.STALE_PLAYER_STATE)

    # UNKNOWN and CONFLICTING evaluate to INSUFFICIENT_EVIDENCE_RELIABILITY
    assert evaluate_delta_item(
        target_eligibility=EligibilityState.ACTIVE,
        player_observation_exists=True,
        is_stale=False,
        verification_state=VerificationState.UNKNOWN,
        observation_coverage=ObservationCoverage.COMPLETE,
        is_entity_present=False,
    ) == (DeltaStatus.UNKNOWN, DeltaReason.INSUFFICIENT_EVIDENCE_RELIABILITY)

    assert evaluate_delta_item(
        target_eligibility=EligibilityState.ACTIVE,
        player_observation_exists=True,
        is_stale=False,
        verification_state=VerificationState.CONFLICTING,
        observation_coverage=ObservationCoverage.COMPLETE,
        is_entity_present=False,
    ) == (DeltaStatus.UNKNOWN, DeltaReason.INSUFFICIENT_EVIDENCE_RELIABILITY)

    # Present cases:
    for v_state in (VerificationState.VERIFIED, VerificationState.CORROBORATED, VerificationState.SINGLE_SOURCE):
        assert evaluate_delta_item(
            target_eligibility=EligibilityState.ACTIVE,
            player_observation_exists=True,
            is_stale=False,
            verification_state=v_state,
            observation_coverage=ObservationCoverage.COMPLETE,
            is_entity_present=True,
        ) == (DeltaStatus.PRESENT, DeltaReason.NONE)


def test_unknown_character_level_representability_and_orchestration() -> None:
    """Verify that unknown/unobserved level is representable and orchestrates cleanly without error."""
    char = CharacterState.create_initial("c_unknown", "UnknownHero")
    assert char.level.value == 1  # default initial is 1
    # Create character state with level=None (unobserved)
    char_no_level = char.model_copy(update={"level": None})
    assert char_no_level.level is None

    # 1. validate_character_level returns None
    assert validate_character_level(None) is None

    # 2. Progression phase evaluates to UNKNOWN
    prog = resolve_progression_phase(None)
    assert prog.phase == ProgressionPhase.UNKNOWN
    assert prog.target_snapshot_name is None

    # 3. Variant resolution evaluates to NONE / NOT_APPLICABLE
    var_res = resolve_target_variant(prog.phase, None)
    assert var_res.variant == TargetVariant.NONE
    assert var_res.status == VariantResolutionStatus.NOT_APPLICABLE

    # 4. Root BuildDeltaResult orchestrator accepts unobserved level cleanly
    b = _load_build("lvl 1-14 - 0.5.5 Fubgun Flameblast Oil G.build", "lvl 1-14")
    brain_input = BuildBrainInput(
        character_state=char_no_level,
        observation_coverage=PlayerObservationCoverage(),
    )
    result = compute_build_delta(brain_input, b)
    assert result.character_level is None
    assert result.progression_phase == ProgressionPhase.UNKNOWN
    assert result.target_stage_name is None
    assert result.target_variant_resolution.status == VariantResolutionStatus.NOT_APPLICABLE

