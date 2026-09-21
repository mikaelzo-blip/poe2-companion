"""Unit tests for passive logical identity, hardened canonicalization, and passive delta."""

import pytest
from companion.sources.models_normalized import WeaponSetContext
from companion.sources.models_raw import RawPassiveEntry
from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.schema import CharacterState
from companion.build.input import ObservationCoverage
from companion.build.eligibility import EligibilityState
from companion.build.conflicts import ConflictRecord
from companion.build.policy import DeltaReason, DeltaStatus
from companion.build.passives import (
    CanonicalTargetPassive,
    PassiveDeltaEntry,
    canonicalize_target_passives,
    evaluate_passive_delta,
)


def test_identical_duplicate_raw_rows_canonicalize_cleanly() -> None:
    """Identical duplicate raw rows canonicalize cleanly to 1 logical allocation requirement."""
    # Simulates real M0 anomaly where dexterity30_ appears at indices 9 and 21 in DEFAULT_OR_SHARED
    raw_entries = [
        RawPassiveEntry(id="dexterity30_", weapon_set=None),
        RawPassiveEntry(id="dexterity30_", weapon_set=None),
    ]
    canonical, conflicts = canonicalize_target_passives(raw_entries, source_provenance="TEST_STAGE")

    assert len(canonical) == 1
    p = canonical[0]
    assert p.passive_id == "dexterity30_"
    assert p.weapon_set_context == WeaponSetContext.DEFAULT_OR_SHARED
    assert p.required_count == 1
    assert p.source_occurrences == 2
    assert p.source_indices == [0, 1]
    assert p.has_conflict is False
    assert len(conflicts) == 0


def test_distinct_weapon_set_contexts_produce_separate_requirements() -> None:
    """Same passive ID with distinct weapon-set contexts produces separate compound keys."""
    raw_entries = [
        RawPassiveEntry(id="fire62", weapon_set=None),  # DEFAULT_OR_SHARED
        RawPassiveEntry(id="fire62", weapon_set=1),     # SPECIALISATION_1
        RawPassiveEntry(id="fire62", weapon_set=2),     # SPECIALISATION_2
        RawPassiveEntry(id="fire62", weapon_set=0),     # UNKNOWN_RESERVED
    ]
    canonical, conflicts = canonicalize_target_passives(raw_entries)

    assert len(canonical) == 4
    contexts = {p.weapon_set_context for p in canonical}
    assert contexts == {
        WeaponSetContext.DEFAULT_OR_SHARED,
        WeaponSetContext.SPECIALISATION_1,
        WeaponSetContext.SPECIALISATION_2,
        WeaponSetContext.UNKNOWN_RESERVED,
    }
    for p in canonical:
        assert p.required_count == 1
        assert p.source_occurrences == 1
    assert len(conflicts) == 0


def test_duplicate_logical_keys_with_conflicting_metadata_produce_conflict_record() -> None:
    """Duplicate logical keys with conflicting metadata produce structured CONFLICTING_EVIDENCE."""
    raw_entries = [
        {"id": "node_a", "weapon_set": None, "metadata": {"interval": [1, 50]}},
        {"id": "node_a", "weapon_set": None, "metadata": {"interval": [51, 100]}},
    ]
    canonical, conflicts = canonicalize_target_passives(raw_entries, source_provenance="TEST_SOURCE")

    assert len(canonical) == 1
    assert canonical[0].has_conflict is True
    assert canonical[0].required_count == 1
    assert len(conflicts) == 1
    assert conflicts[0].status == "CONFLICTING_EVIDENCE"
    assert "node_a" in conflicts[0].field_name


def test_target_variant_changes_remove_and_add_passive_requirements() -> None:
    """Switching target variant re-evaluates passive deltas non-monotonically."""
    # Target 1 requires node_mageblood
    target_v1 = [
        CanonicalTargetPassive(
            key=("node_mb", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="node_mb",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            required_count=1,
            source_occurrences=1,
            source_indices=[0],
        )
    ]
    # Target 2 requires node_dotcap
    target_v2 = [
        CanonicalTargetPassive(
            key=("node_dot", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="node_dot",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            required_count=1,
            source_occurrences=1,
            source_indices=[0],
        )
    ]

    # Player has allocated node_mb
    char = CharacterState.create_initial("hero1", "Hero")
    char.audit["allocated_passives"] = [("node_mb", WeaponSetContext.DEFAULT_OR_SHARED)]
    char.audit["passives_verification"] = VerificationState.VERIFIED

    # Under target 1: node_mb is PRESENT
    delta_v1 = evaluate_passive_delta(
        target_passives=target_v1,
        character_state=char,
        coverage=ObservationCoverage.COMPLETE,
    )
    mb_entry_v1 = next(d for d in delta_v1 if d.passive_id == "node_mb")
    assert mb_entry_v1.status == DeltaStatus.PRESENT

    # Under target 2: node_mb is EXTRA and node_dot is MISSING
    delta_v2 = evaluate_passive_delta(
        target_passives=target_v2,
        character_state=char,
        coverage=ObservationCoverage.COMPLETE,
    )
    dot_entry_v2 = next(d for d in delta_v2 if d.passive_id == "node_dot")
    assert dot_entry_v2.status == DeltaStatus.MISSING

    mb_entry_v2 = next(d for d in delta_v2 if d.passive_id == "node_mb")
    assert mb_entry_v2.status == DeltaStatus.EXTRA


def test_verified_passive_state_with_unknown_coverage_is_unknown() -> None:
    """VERIFIED passive state with coverage UNKNOWN evaluates to UNKNOWN (OBSERVATION_COVERAGE_UNKNOWN), never MISSING."""
    target = [
        CanonicalTargetPassive(
            key=("node_fire", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="node_fire",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            required_count=1,
            source_occurrences=1,
            source_indices=[0],
        )
    ]
    char = CharacterState.create_initial("hero1", "Hero")
    char.audit["allocated_passives"] = []
    char.audit["passives_verification"] = VerificationState.VERIFIED

    delta = evaluate_passive_delta(
        target_passives=target,
        character_state=char,
        coverage=ObservationCoverage.UNKNOWN,
    )
    assert len(delta) == 1
    assert delta[0].status == DeltaStatus.UNKNOWN
    assert delta[0].reason == DeltaReason.OBSERVATION_COVERAGE_UNKNOWN


def test_fresh_verified_partial_passive_observation_is_unknown() -> None:
    """Fresh VERIFIED but PARTIAL passive observation evaluates to UNKNOWN with PARTIAL_PLAYER_OBSERVATION, never MISSING."""
    target = [
        CanonicalTargetPassive(
            key=("node_fire", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="node_fire",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            required_count=1,
            source_occurrences=1,
            source_indices=[0],
        )
    ]
    char = CharacterState.create_initial("hero1", "Hero")
    char.audit["allocated_passives"] = []
    char.audit["passives_verification"] = VerificationState.VERIFIED

    delta = evaluate_passive_delta(
        target_passives=target,
        character_state=char,
        coverage=ObservationCoverage.PARTIAL,
    )
    assert len(delta) == 1
    assert delta[0].status == DeltaStatus.UNKNOWN
    assert delta[0].reason == DeltaReason.PARTIAL_PLAYER_OBSERVATION


def test_complete_fresh_passive_observation_missing() -> None:
    """Complete fresh passive observation with target absent evaluates to MISSING."""
    target = [
        CanonicalTargetPassive(
            key=("node_fire", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="node_fire",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            required_count=1,
            source_occurrences=1,
            source_indices=[0],
        )
    ]
    char = CharacterState.create_initial("hero1", "Hero")
    char.audit["allocated_passives"] = []
    char.audit["passives_verification"] = VerificationState.VERIFIED

    delta = evaluate_passive_delta(
        target_passives=target,
        character_state=char,
        coverage=ObservationCoverage.COMPLETE,
    )
    assert len(delta) == 1
    assert delta[0].status == DeltaStatus.MISSING
    assert delta[0].reason == DeltaReason.NONE


def test_coverage_never_inferred_from_verified_alone() -> None:
    """Coverage is never inferred from VerificationState.VERIFIED alone."""
    target = [
        CanonicalTargetPassive(
            key=("node_fire", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="node_fire",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            required_count=1,
            source_occurrences=1,
            source_indices=[0],
        )
    ]
    char = CharacterState.create_initial("hero1", "Hero")
    char.audit["allocated_passives"] = []
    char.audit["passives_verification"] = VerificationState.VERIFIED

    # Default coverage is UNKNOWN
    delta = evaluate_passive_delta(
        target_passives=target,
        character_state=char,
    )
    assert delta[0].status == DeltaStatus.UNKNOWN
    assert delta[0].reason == DeltaReason.OBSERVATION_COVERAGE_UNKNOWN


def test_stale_player_observations_evaluate_to_unknown_with_stale_reason() -> None:
    """Stale player observations evaluate to UNKNOWN with reason STALE_PLAYER_STATE."""
    target = [
        CanonicalTargetPassive(
            key=("node_fire", WeaponSetContext.DEFAULT_OR_SHARED),
            passive_id="node_fire",
            weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
            required_count=1,
            source_occurrences=1,
            source_indices=[0],
        )
    ]
    char = CharacterState.create_initial("hero1", "Hero")
    char.audit["allocated_passives"] = []
    char.audit["passives_verification"] = VerificationState.STALE
    char.audit["passives_is_stale"] = True

    delta = evaluate_passive_delta(
        target_passives=target,
        character_state=char,
        coverage=ObservationCoverage.COMPLETE,
    )
    assert len(delta) == 1
    assert delta[0].status == DeltaStatus.UNKNOWN
    assert delta[0].reason == DeltaReason.STALE_PLAYER_STATE
