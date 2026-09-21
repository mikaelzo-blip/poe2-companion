"""Unit tests for live session tracking fields on CharacterState."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import pytest

from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.schema import CharacterState


def test_character_state_live_fields_defaults() -> None:
    char = CharacterState.create_initial("hero_test", "HeroTest")
    assert char.current_zone.value == "Unknown"
    assert char.death_count.value == 0
    assert char.session_active is False
    assert char.last_observed_at is None


def test_character_state_live_fields_assignment_and_serialization() -> None:
    char = CharacterState.create_initial("hero_test", "HeroTest")
    now_iso = datetime.now(timezone.utc).isoformat()

    char.current_zone = ProvenancedField.create(
        "Clear Fell",
        "client_log",
        VerificationState.VERIFIED,
    )
    char.death_count = ProvenancedField.create(
        1,
        "client_log",
        VerificationState.VERIFIED,
    )
    char.session_active = True
    char.last_observed_at = now_iso

    # Round-trip JSON serialization
    serialized = char.model_dump_json()
    loaded = CharacterState.model_validate_json(serialized)

    assert loaded.current_zone is not None
    assert loaded.current_zone.value == "Clear Fell"
    assert loaded.death_count is not None
    assert loaded.death_count.value == 1
    assert loaded.session_active is True
    assert loaded.last_observed_at == now_iso
