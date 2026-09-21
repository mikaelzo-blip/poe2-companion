"""Unit tests for rolling backup management and corrupt state recovery."""

from pathlib import Path
import time
import pytest
from companion.state.backup import MAX_BACKUPS
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore, CorruptStateError


def test_rolling_backup_retention_bounded(tmp_path: Path) -> None:
    store = CharacterStateStore(tmp_path)
    char = CharacterState.create_initial("char_backup", "BackupHero")

    # Perform 6 successive saves
    for lvl in range(1, 7):
        char.level = char.level.with_update(lvl, "TEST", char.level.verification_state)
        store.save_character(char)
        # Sleep slightly to ensure distinct timestamp filenames
        time.sleep(0.01)

    backup_dir = store.get_backup_dir("char_backup")
    backups = list(backup_dir.glob("state.*.bak"))
    assert len(backups) == MAX_BACKUPS


def test_corrupt_canonical_restores_from_latest_valid_backup(tmp_path: Path) -> None:
    store = CharacterStateStore(tmp_path)
    char = CharacterState.create_initial("char_recover", "RecoverHero")

    # Save initial version (level 1)
    store.save_character(char)

    # Save second version (level 20) -> generates backup of version 1 (level 1)
    char.level = char.level.with_update(20, "TEST", char.level.verification_state)
    store.save_character(char)

    # Corrupt canonical file
    canonical = store.get_character_path("char_recover")
    canonical.write_text("{corrupt json broken...", encoding="utf-8")

    # Loading character should detect corruption and restore from latest valid backup
    recovered = store.load_character("char_recover")
    assert recovered.character_id == "char_recover"
    assert recovered.level.value in (1, 20)

    # Canonical file on disk should now be valid again
    assert "corrupt" not in canonical.read_text(encoding="utf-8")


def test_corrupt_canonical_never_displaces_valid_backups(tmp_path: Path) -> None:
    store = CharacterStateStore(tmp_path)
    char = CharacterState.create_initial("char_protect", "ProtectHero")

    # Initial valid save
    store.save_character(char)

    # Second valid save (creates backup)
    char.level = char.level.with_update(15, "TEST", char.level.verification_state)
    store.save_character(char)

    backup_dir = store.get_backup_dir("char_protect")
    initial_backups = sorted(list(backup_dir.glob("state.*.bak")))
    assert len(initial_backups) == 1
    backup_content_before = initial_backups[0].read_text(encoding="utf-8")

    # Now corrupt the canonical file
    canonical = store.get_character_path("char_protect")
    canonical.write_text("GARBAGE DATA CORRUPT", encoding="utf-8")

    # Now perform another save with a valid state object
    char.level = char.level.with_update(30, "TEST", char.level.verification_state)
    store.save_character(char)

    # Ensure garbage was NOT copied into backup!
    for b in backup_dir.glob("state.*.bak"):
        content = b.read_text(encoding="utf-8")
        assert "GARBAGE" not in content


def test_unrecoverable_corrupt_state_raises_error(tmp_path: Path) -> None:
    store = CharacterStateStore(tmp_path)
    canonical = store.get_character_path("char_lost")
    canonical.write_text("UNRECOVERABLE", encoding="utf-8")

    with pytest.raises(CorruptStateError):
        store.load_character("char_lost")
