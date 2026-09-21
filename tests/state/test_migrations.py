"""Unit tests for schema migrations and version dispatch."""

import pytest
from companion.state.migrations import (
    UnsupportedSchemaVersionError,
    apply_migrations,
)
from companion.state.provenance import VerificationState
from companion.state.schema import CharacterState


def test_current_schema_version_no_op() -> None:
    data = {
        "schema_version": "2.0",
        "character_id": "test_01",
        "character_name": "Hero",
    }
    result = apply_migrations(data)
    assert result == data


def test_migrates_v1_to_v2() -> None:
    v1_data = {
        "schema_version": "1.0",
        "character_id": "legacy_char",
        "character_name": "OldHero",
        "level": 45,
        "current_zone": "The Forest",
        "current_act": 2,
    }
    upgraded = apply_migrations(v1_data)
    assert upgraded["schema_version"] == "2.0"
    assert upgraded["level"]["value"] == 45
    assert upgraded["level"]["source"] == "MIGRATION_1_0"
    assert upgraded["level"]["verification_state"] == VerificationState.CORROBORATED.value
    assert upgraded["current_zone"]["value"] == "The Forest"

    # Verify it validates into CharacterState model
    model = CharacterState.model_validate(upgraded)
    assert model.character_id == "legacy_char"
    assert model.level.value == 45


def test_rejects_future_schema_version() -> None:
    future_data = {
        "schema_version": "3.0",
        "character_id": "future_char",
    }
    with pytest.raises(UnsupportedSchemaVersionError):
        apply_migrations(future_data)
