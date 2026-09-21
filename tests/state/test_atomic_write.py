"""Unit tests for crash-safe atomic write staging and failure handling."""

from pathlib import Path
import pytest
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore, atomic_write_file


def test_atomic_write_file_success(tmp_path: Path) -> None:
    dest = tmp_path / "data.json"
    atomic_write_file(dest, b'{"hello": "world"}')

    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == '{"hello": "world"}'
    # Ensure no leftover temporary files in directory
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_atomic_write_file_cleans_up_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "dest.json"

    # Simulate failure during os.replace
    def fake_replace(src: Path, dst: Path) -> None:
        raise OSError("Disk failure simulation")

    monkeypatch.setattr("os.replace", fake_replace)

    with pytest.raises(OSError):
        atomic_write_file(dest, b"payload")

    # Destination should not exist and temporary file should be removed
    assert not dest.exists()
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_canonical_file_remains_intact_if_write_fails_before_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = CharacterStateStore(tmp_path)
    char = CharacterState.create_initial("char_safe", "HeroSafe")
    store.save_character(char)

    canonical = store.get_character_path("char_safe")
    original_mtime = canonical.stat().st_mtime_ns
    original_bytes = canonical.read_bytes()

    # Now attempt a second save that fails during os.replace
    def fake_replace(src: Path, dst: Path) -> None:
        raise OSError("Simulated crash before atomic replace")

    monkeypatch.setattr("os.replace", fake_replace)

    char.level = char.level.with_update(10, "TEST", char.level.verification_state)
    with pytest.raises(OSError):
        store.save_character(char)

    # Canonical file must remain unchanged
    assert canonical.is_file()
    assert canonical.read_bytes() == original_bytes
    assert canonical.stat().st_mtime_ns == original_mtime
    # No temporary files left
    assert list(store.characters_dir.glob("*.tmp.*")) == []


def test_active_character_atomic_write(tmp_path: Path) -> None:
    store = CharacterStateStore(tmp_path)
    char = CharacterState.create_initial("char_active", "ActiveHero")
    store.save_character(char)

    active_path = store.set_active_character("char_active")
    assert active_path.is_file()
    loaded_active = store.get_active_character()
    assert loaded_active is not None
    assert loaded_active.character_id == "char_active"
