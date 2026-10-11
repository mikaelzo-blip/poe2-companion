"""Tests for PoE2 class and ascendancy code mapping."""

import pytest
from companion.state.schema import CharacterState, split_class_code


def test_split_class_code_known():
    assert split_class_code("Witch3") == ("Witch", "Lich")
    assert split_class_code("Witch3b") == ("Witch", "Abyssal Lich")


def test_split_class_code_unrecognized():
    assert split_class_code("Mercenary") == ("Mercenary", None)


def test_split_class_code_empty_and_none():
    assert split_class_code(None) == (None, None)
    assert split_class_code("") == (None, None)
    assert split_class_code("   ") == (None, None)


def test_character_state_init_with_class_code():
    char = CharacterState(
        character_id="x",
        character_name="x",
        character_class="Sorceress1",
    )
    assert char.character_class == "Sorceress"
    assert char.ascendancy == "Stormweaver"


def test_character_state_load_dict_overrides_stored_ascendancy():
    raw_data = {
        "character_id": "test_witch",
        "character_name": "TestWitch",
        "character_class": "Witch3",
        "ascendancy": "Gemling Legionnaire",
    }
    raw_copy = dict(raw_data)
    char = CharacterState.model_validate(raw_data)
    assert char.character_class == "Witch"
    assert char.ascendancy == "Lich"
    # Ensure caller dict was not mutated
    assert raw_data == raw_copy


def test_character_state_without_class_defaults_to_none():
    char = CharacterState(character_id="x", character_name="x")
    assert char.character_class is None
    assert char.ascendancy is None


def test_set_class_with_code():
    char = CharacterState(character_id="x", character_name="x")
    char.set_class("Druid2")
    assert char.character_class == "Druid"
    assert char.ascendancy == "Shaman"


def test_set_class_same_class_keeps_ascendancy():
    char = CharacterState(
        character_id="x",
        character_name="x",
        character_class="Witch3",
    )
    assert char.character_class == "Witch"
    assert char.ascendancy == "Lich"
    char.set_class("Witch")
    assert char.character_class == "Witch"
    assert char.ascendancy == "Lich"


def test_set_class_different_class_clears_ascendancy():
    char = CharacterState(
        character_id="x",
        character_name="x",
        character_class="Witch3",
    )
    assert char.character_class == "Witch"
    assert char.ascendancy == "Lich"
    char.set_class("Monk")
    assert char.character_class == "Monk"
    assert char.ascendancy is None


def test_set_class_none_or_empty_is_noop():
    char = CharacterState(
        character_id="x",
        character_name="x",
        character_class="Witch3",
    )
    assert char.character_class == "Witch"
    assert char.ascendancy == "Lich"
    char.set_class(None)
    assert char.character_class == "Witch"
    assert char.ascendancy == "Lich"
    char.set_class("")
    assert char.character_class == "Witch"
    assert char.ascendancy == "Lich"
