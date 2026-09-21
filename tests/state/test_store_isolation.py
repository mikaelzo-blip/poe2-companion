"""Unit tests for multi-character data isolation and character ID safety."""

from pathlib import Path
import pytest
from companion.state.schema import CharacterState, InvalidCharacterIdError
from companion.state.store import CharacterStateStore


def test_multi_character_data_isolation(tmp_path: Path) -> None:
    store = CharacterStateStore(tmp_path)

    char1 = CharacterState.create_initial("char_alpha", "Alpha Hero")
    char2 = CharacterState.create_initial("char_beta", "Beta Hero")

    char1.level = char1.level.with_update(25, "TEST", char1.level.verification_state)
    char2.level = char2.level.with_update(70, "TEST", char2.level.verification_state)

    store.save_character(char1)
    store.save_character(char2)

    loaded1 = store.load_character("char_alpha")
    loaded2 = store.load_character("char_beta")

    assert loaded1.character_id == "char_alpha"
    assert loaded1.level.value == 25

    assert loaded2.character_id == "char_beta"
    assert loaded2.level.value == 70

    # Modifying char1 and saving must not mutate char2
    char1.level = char1.level.with_update(26, "TEST", char1.level.verification_state)
    store.save_character(char1)

    reloaded2 = store.load_character("char_beta")
    assert reloaded2.level.value == 70


def test_character_id_safety_and_collision_prevention(tmp_path: Path) -> None:
    store = CharacterStateStore(tmp_path)

    # Valid ID works
    char_valid = CharacterState.create_initial("char_01", "ValidHero")
    store.save_character(char_valid)

    # Similar but invalid IDs containing traversal/separators/dots are rejected without lossy collapsing
    for bad_id in ["char/01", "char\\01", "char.01", "../char_01", "char 01"]:
        with pytest.raises(InvalidCharacterIdError):
            store.get_character_path(bad_id)
        with pytest.raises(InvalidCharacterIdError):
            store.load_character(bad_id)


def test_list_characters(tmp_path: Path) -> None:
    store = CharacterStateStore(tmp_path)
    store.save_character(CharacterState.create_initial("char_c", "Hero C"))
    store.save_character(CharacterState.create_initial("char_a", "Hero A"))
    store.save_character(CharacterState.create_initial("char_b", "Hero B"))

    # Stray temp file or invalid file
    (store.characters_dir / "char_a.tmp.12345.json").write_text("temp", encoding="utf-8")
    (store.characters_dir / "invalid.name.json").write_text("{}", encoding="utf-8")

    char_list = store.list_characters()
    assert char_list == ["char_a", "char_b", "char_c"]
