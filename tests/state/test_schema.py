"""Unit tests for CharacterState v2 schema and character ID validation."""

import pytest
from companion.state.schema import (
    CURRENT_SCHEMA_VERSION,
    CharacterState,
    InvalidCharacterIdError,
    validate_character_id,
)


def test_valid_character_id() -> None:
    assert validate_character_id("fubgun_gemling_01") == "fubgun_gemling_01"
    assert validate_character_id("char-123_ABC") == "char-123_ABC"
    assert validate_character_id("a") == "a"
    assert validate_character_id("a" * 64) == "a" * 64


def test_rejects_invalid_character_id() -> None:
    with pytest.raises(InvalidCharacterIdError):
        validate_character_id("")

    with pytest.raises(InvalidCharacterIdError):
        validate_character_id("a" * 65)

    with pytest.raises(InvalidCharacterIdError):
        validate_character_id("../escape")

    with pytest.raises(InvalidCharacterIdError):
        validate_character_id("path/sub")

    with pytest.raises(InvalidCharacterIdError):
        validate_character_id("char.name")

    with pytest.raises(InvalidCharacterIdError):
        validate_character_id("char name")

    with pytest.raises(InvalidCharacterIdError):
        validate_character_id("char$1")


def test_character_state_creation_and_roundtrip() -> None:
    char = CharacterState.create_initial(
        character_id="char_test_01",
        character_name="FlameblastTester",
    )
    assert char.character_id == "char_test_01"
    assert char.character_name == "FlameblastTester"
    assert char.schema_version == CURRENT_SCHEMA_VERSION
    assert char.level.value == 1

    json_str = char.model_dump_json()
    reloaded = CharacterState.model_validate_json(json_str)

    assert reloaded.character_id == "char_test_01"
    assert reloaded.level.value == 1
    assert reloaded.schema_version == CURRENT_SCHEMA_VERSION


def test_character_state_rejects_invalid_id_on_init() -> None:
    with pytest.raises(InvalidCharacterIdError):
        CharacterState.create_initial(
            character_id="invalid/path",
            character_name="Hacker",
        )
