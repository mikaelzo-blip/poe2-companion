"""Unit tests for schema version 3.0, migration, and persistence round-trip.

Verifies:
1. Sequential migration chain 1.0 -> 2.0 -> 3.0.
2. Direct migration 2.0 -> 3.0 leaving transition = None for levels 20, 52, and 60.
3. Deterministic initialization on first evaluation after migration:
   - Level 20 character with transition = None evaluates to NOT_RELEVANT.
   - Level 52 character with transition = None and no evidence evaluates to VERIFYING.
   - Level 60 character with transition = None and verified completion evidence evaluates to COMPLETE.
4. Round-trip persistence of transition state across process restart using CharacterStateStore
   for all 7 states (NOT_RELEVANT, PREPARING, VERIFYING, BLOCKED, READY, TRANSITIONING, COMPLETE),
   especially proving COMPLETE restart -> COMPLETE and READY restart -> READY.
5. Rejection of unrecognized future schema versions (e.g. 4.0).
"""

from __future__ import annotations

import pytest
from pathlib import Path

from companion.state.migrations import (
    UnsupportedSchemaVersionError,
    apply_migrations,
    migrate_2_0_to_3_0,
)
from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.schema import CURRENT_SCHEMA_VERSION, CharacterState
from companion.state.store import CharacterStateStore
from companion.transition.evaluator import evaluate_level52_transition
from companion.transition.requirements import RequirementReadiness
from companion.transition.state import (
    Level52TransitionRecord,
    Level52TransitionState,
)


def test_sequential_migration_1_0_to_2_0_to_3_0() -> None:
    """A legacy v1.0 character state dict sequentially migrates through 2.0 to 3.0."""
    v1_data = {
        "schema_version": "1.0",
        "character_id": "legacy_char",
        "character_name": "OldHero",
        "level": 45,
        "current_zone": "The Forest",
        "current_act": 2,
    }
    migrated = apply_migrations(v1_data)

    assert migrated["schema_version"] == "3.0"
    assert migrated["transition"] is None
    assert migrated["level"]["value"] == 45
    assert migrated["level"]["source"] == "MIGRATION_1_0"
    assert migrated["level"]["verification_state"] == VerificationState.CORROBORATED.value
    assert migrated["current_zone"]["value"] == "The Forest"

    # Verify model validation into CharacterState
    char = CharacterState.model_validate(migrated)
    assert char.schema_version == "3.0"
    assert char.character_id == "legacy_char"
    assert char.level.value == 45
    assert char.transition is None


@pytest.mark.parametrize("level", [20, 52, 60])
def test_direct_migration_2_0_to_3_0_leaves_transition_none(level: int) -> None:
    """Migrating 2.0 to 3.0 leaves transition uninitialized (None) without domain inference."""
    v2_data = {
        "schema_version": "2.0",
        "character_id": f"hero_lvl_{level}",
        "character_name": f"Hero{level}",
        "level": {
            "value": level,
            "source": "PLAYER_LEVEL_POLLED",
            "verification_state": VerificationState.VERIFIED.value,
        },
    }

    # Test direct migration function
    direct_migrated = migrate_2_0_to_3_0(dict(v2_data))
    assert direct_migrated["schema_version"] == "3.0"
    assert direct_migrated["transition"] is None

    # Test full migration chain dispatcher
    migrated = apply_migrations(v2_data)
    assert migrated["schema_version"] == "3.0"
    assert migrated["transition"] is None

    # Model validation preserves transition = None
    char = CharacterState.model_validate(migrated)
    assert char.schema_version == "3.0"
    assert char.level.value == level
    assert char.transition is None


def test_deterministic_initialization_on_first_evaluation_after_migration() -> None:
    """First evaluation post-migration deterministically initializes transition state."""
    # 1. Level 20 character with transition = None -> NOT_RELEVANT
    char_20 = CharacterState.create_initial(character_id="hero_20", character_name="Hero20")
    char_20.level = ProvenancedField[int].create(20, source="TEST", verification_state=VerificationState.VERIFIED)
    assert char_20.transition is None

    eval_20 = evaluate_level52_transition(character_state=char_20)
    assert eval_20.state == Level52TransitionState.NOT_RELEVANT
    assert eval_20.character_level == 20

    # 2. Level 52 character with transition = None and no evidence -> VERIFYING
    char_52 = CharacterState.create_initial(character_id="hero_52", character_name="Hero52")
    char_52.level = ProvenancedField[int].create(52, source="TEST", verification_state=VerificationState.VERIFIED)
    assert char_52.transition is None

    eval_52 = evaluate_level52_transition(character_state=char_52)
    assert eval_52.state == Level52TransitionState.VERIFYING
    assert eval_52.character_level == 52

    # 3. Level 60 character with transition = None and verified completion evidence -> COMPLETE
    char_60 = CharacterState.create_initial(character_id="hero_60", character_name="Hero60")
    char_60.level = ProvenancedField[int].create(60, source="TEST", verification_state=VerificationState.VERIFIED)
    assert char_60.transition is None

    eval_60 = evaluate_level52_transition(
        character_state=char_60,
        has_verified_completion_evidence=True,
    )
    assert eval_60.state == Level52TransitionState.COMPLETE
    assert eval_60.character_level == 60


def test_round_trip_persistence_across_restart(tmp_path: Path) -> None:
    """CharacterStateStore persists all 7 transition states across process restart."""
    store = CharacterStateStore(tmp_path)

    all_states = [
        Level52TransitionState.NOT_RELEVANT,
        Level52TransitionState.PREPARING,
        Level52TransitionState.VERIFYING,
        Level52TransitionState.BLOCKED,
        Level52TransitionState.READY,
        Level52TransitionState.TRANSITIONING,
        Level52TransitionState.COMPLETE,
    ]

    for state in all_states:
        char_id = f"char_{state.value.lower()}"
        char = CharacterState.create_initial(character_id=char_id, character_name=f"Hero_{state.value}")
        char.level = ProvenancedField[int].create(52, source="TEST", verification_state=VerificationState.VERIFIED)

        # Build requirement mock
        req_readiness = (
            RequirementReadiness.SATISFIED
            if state in (Level52TransitionState.READY, Level52TransitionState.COMPLETE)
            else RequirementReadiness.UNSATISFIED
            if state == Level52TransitionState.BLOCKED
            else RequirementReadiness.UNKNOWN
        )

        char.transition = Level52TransitionRecord(
            state=state,
            requirements={"swap_lvl_52": req_readiness},
            last_evaluated_at="2026-09-22T12:00:00Z",
            verified_at="2026-09-22T12:00:00Z" if state == Level52TransitionState.COMPLETE else None,
            notes=f"persisted_notes_for_{state.value}",
        )

        store.save_character(char)

    # Simulate fresh process restart with a new store instance
    fresh_store = CharacterStateStore(tmp_path)

    for state in all_states:
        char_id = f"char_{state.value.lower()}"
        reloaded = fresh_store.load_character(char_id)

        assert reloaded.transition is not None
        assert reloaded.transition.state == state
        assert reloaded.transition.last_evaluated_at == "2026-09-22T12:00:00Z"
        assert reloaded.transition.notes == f"persisted_notes_for_{state.value}"

        req_readiness = (
            RequirementReadiness.SATISFIED
            if state in (Level52TransitionState.READY, Level52TransitionState.COMPLETE)
            else RequirementReadiness.UNSATISFIED
            if state == Level52TransitionState.BLOCKED
            else RequirementReadiness.UNKNOWN
        )
        assert reloaded.transition.requirements == {"swap_lvl_52": req_readiness}

        if state == Level52TransitionState.COMPLETE:
            assert reloaded.transition.verified_at == "2026-09-22T12:00:00Z"
        else:
            assert reloaded.transition.verified_at is None

    # Prove COMPLETE restart -> COMPLETE upon re-evaluation
    reloaded_complete = fresh_store.load_character("char_complete")
    eval_complete = evaluate_level52_transition(character_state=reloaded_complete)
    assert eval_complete.state == Level52TransitionState.COMPLETE

    # Prove READY restart preserves READY in store
    reloaded_ready = fresh_store.load_character("char_ready")
    assert reloaded_ready.transition.state == Level52TransitionState.READY


def test_rejects_unrecognized_future_schema_version() -> None:
    """Migration dispatcher strictly rejects unrecognized future schema versions."""
    future_data = {
        "schema_version": "4.0",
        "character_id": "future_char",
    }
    with pytest.raises(UnsupportedSchemaVersionError) as exc_info:
        apply_migrations(future_data)
    assert "4.0" in str(exc_info.value)

    far_future_data = {
        "schema_version": "5.0",
        "character_id": "far_future_char",
    }
    with pytest.raises(UnsupportedSchemaVersionError):
        apply_migrations(far_future_data)

    invalid_version = {
        "schema_version": "invalid",
        "character_id": "invalid_char",
    }
    with pytest.raises(UnsupportedSchemaVersionError):
        apply_migrations(invalid_version)
