"""Unit tests for StateChangeTracker and batch coalescing."""

from __future__ import annotations

import pytest

from companion.runtime.change_tracker import DirtyTrigger, StateChangeTracker
from companion.state.provenance import ProvenancedField
from companion.state.schema import CharacterState


def test_dirty_trigger_values() -> None:
    assert DirtyTrigger.LEVEL.value == "level"
    assert DirtyTrigger.ZONE.value == "zone"
    assert DirtyTrigger.SESSION_STATE.value == "session_state"
    assert DirtyTrigger.CHARACTER_IDENTITY.value == "character_identity"
    assert DirtyTrigger.GEAR_AUDIT.value == "gear_audit"


def test_no_changes_detected_when_states_identical() -> None:
    tracker = StateChangeTracker()
    state1 = CharacterState(character_id="TestChar", character_name="TestChar")
    state2 = state1.model_copy(deep=True)

    triggers = tracker.compute_delta(state1, state2)
    assert len(triggers) == 0
    assert not tracker.has_changes()
    assert not tracker.should_reevaluate_objectives()


def test_level_change_detected() -> None:
    tracker = StateChangeTracker()
    state1 = CharacterState(character_id="TestChar", character_name="TestChar")
    state2 = state1.model_copy(deep=True)
    state2.level = ProvenancedField[int].create(5, source="TEST")

    triggers = tracker.compute_delta(state1, state2)
    assert DirtyTrigger.LEVEL in triggers
    assert tracker.has_changes()
    assert tracker.should_reevaluate_objectives()


def test_zone_change_detected() -> None:
    tracker = StateChangeTracker()
    state1 = CharacterState(character_id="TestChar", character_name="TestChar")
    state2 = state1.model_copy(deep=True)
    state2.current_zone = ProvenancedField[str].create("The Mud Flats", source="TEST")

    triggers = tracker.compute_delta(state1, state2)
    assert DirtyTrigger.ZONE in triggers
    assert tracker.has_changes()
    assert tracker.should_reevaluate_objectives()


def test_batch_coalescing_multiple_updates() -> None:
    tracker = StateChangeTracker()
    state1 = CharacterState(character_id="TestChar", character_name="TestChar")
    state2 = state1.model_copy(deep=True)
    state2.level = ProvenancedField[int].create(2, source="TEST")

    state3 = state2.model_copy(deep=True)
    state3.level = ProvenancedField[int].create(3, source="TEST")
    state3.current_zone = ProvenancedField[str].create("The Coast", source="TEST")

    tracker.compute_delta(state1, state2)
    tracker.compute_delta(state2, state3)

    assert tracker.has_changes()
    assert DirtyTrigger.LEVEL in tracker.active_triggers
    assert DirtyTrigger.ZONE in tracker.active_triggers
    assert tracker.should_reevaluate_objectives()

    # Clear after batch evaluation
    tracker.clear()
    assert not tracker.has_changes()
    assert not tracker.should_reevaluate_objectives()
