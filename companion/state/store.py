"""Crash-safe atomic file store for character runtime states.

Implements ordered persistence:
1. Serialize new state to JSON bytes.
2. Write to same-directory temporary file.
3. Flush and os.fsync.
4. Safely COPY valid current canonical file into rolling backup (never move before replace).
5. Atomically swap temp into canonical via os.replace.
6. Prune old backups beyond max 3 only after successful replace.
7. Corrupt state recovery from newest valid backup.
8. Active character reference updated via the same atomic-write primitive.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
import uuid

from companion.state.backup import (
    copy_canonical_to_backup,
    find_latest_valid_backup,
    is_valid_state_file,
    prune_backups,
)
from companion.state.lock import StateLock
from companion.state.migrations import apply_migrations
from companion.state.schema import (
    CharacterState,
    InvalidCharacterIdError,
    validate_character_id,
)


class CorruptStateError(RuntimeError):
    """Raised when canonical state is corrupt and no valid backup can be recovered."""
    pass


def atomic_write_file(target_path: Path, data_bytes: bytes) -> None:
    """Write bytes to target_path using a same-directory temp file, fsync, and os.replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.parent / f"{target_path.name}.tmp.{uuid.uuid4().hex}"

    try:
        with open(temp_path, "wb") as f:
            f.write(data_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


class CharacterStateStore:
    """Manages persistent per-character state files, backups, and active pointer."""

    def __init__(self, runtime_dir: str | Path) -> None:
        self.runtime_dir = Path(runtime_dir).resolve()
        self.characters_dir = self.runtime_dir / "characters"
        self.backups_dir = self.runtime_dir / "backups"
        self.active_file = self.runtime_dir / "active_character.json"
        self.lock_file = self.runtime_dir / "state.lock"

        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def get_character_path(self, character_id: str) -> Path:
        """Return the canonical file path for a character."""
        valid_id = validate_character_id(character_id)
        return self.characters_dir / f"{valid_id}.json"

    def get_backup_dir(self, character_id: str) -> Path:
        """Return the backup directory path for a character."""
        valid_id = validate_character_id(character_id)
        return self.backups_dir / valid_id

    def save_character(self, state: CharacterState) -> Path:
        """Persist character state with locking, same-dir temp write, fsync, safe backup copy, and atomic replace."""
        char_id = validate_character_id(state.character_id)
        canonical_path = self.get_character_path(char_id)
        backup_dir = self.get_backup_dir(char_id)

        with StateLock(self.lock_file):
            # 1. Update timestamp and serialize state
            state_dict = state.model_dump()
            state_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
            data_bytes = (json.dumps(state_dict, indent=2) + "\n").encode("utf-8")

            # 2. Write to same-directory temporary file
            temp_path = self.characters_dir / f"{char_id}.tmp.{uuid.uuid4().hex}"

            try:
                with open(temp_path, "wb") as f:
                    f.write(data_bytes)
                    f.flush()
                    # 3. Flush user-space buffer and fsync to disk
                    os.fsync(f.fileno())

                # 4. Safely COPY valid current canonical file into backup
                if canonical_path.exists() and is_valid_state_file(canonical_path):
                    copy_canonical_to_backup(canonical_path, backup_dir)

                # 5. Atomically replace temp into canonical path
                os.replace(temp_path, canonical_path)

                # 6. Prune historical backups only after successful replace
                prune_backups(backup_dir)

            except Exception:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)
                raise

        return canonical_path

    def load_character(self, character_id: str) -> CharacterState:
        """Load character state from disk, recovering from backup if canonical is corrupted."""
        char_id = validate_character_id(character_id)
        canonical_path = self.get_character_path(char_id)

        if not canonical_path.is_file():
            raise FileNotFoundError(f"No character state file found for '{char_id}' at {canonical_path}")

        # Check if canonical is valid JSON
        is_valid = False
        raw_dict: dict[str, Any] = {}
        try:
            content = canonical_path.read_text(encoding="utf-8")
            raw_dict = json.loads(content)
            if isinstance(raw_dict, dict) and "character_id" in raw_dict:
                is_valid = True
        except Exception:
            is_valid = False

        if not is_valid:
            # Attempt automatic recovery from latest valid backup
            backup_dir = self.get_backup_dir(char_id)
            latest_backup = find_latest_valid_backup(backup_dir)
            if latest_backup is not None:
                backup_bytes = latest_backup.read_bytes()
                atomic_write_file(canonical_path, backup_bytes)
                raw_dict = json.loads(backup_bytes.decode("utf-8"))
            else:
                raise CorruptStateError(
                    f"Canonical state for '{char_id}' is corrupt and no valid backup exists to restore."
                )

        # Apply schema migrations
        migrated_dict = apply_migrations(raw_dict)
        return CharacterState.model_validate(migrated_dict)

    def set_active_character(self, character_id: str) -> Path:
        """Set the active character reference atomically."""
        char_id = validate_character_id(character_id)
        canonical_path = self.get_character_path(char_id)
        if not canonical_path.is_file():
            raise FileNotFoundError(f"Cannot activate non-existent character '{char_id}'")

        payload = {
            "active_character_id": char_id,
            "file_path": str(canonical_path),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        data_bytes = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        atomic_write_file(self.active_file, data_bytes)
        return self.active_file

    def get_active_character(self) -> CharacterState | None:
        """Read active character state, or return None if none active."""
        if not self.active_file.is_file():
            return None

        try:
            content = self.active_file.read_text(encoding="utf-8")
            data = json.loads(content)
            active_id = data.get("active_character_id")
            if not active_id:
                return None
            return self.load_character(active_id)
        except Exception:
            return None

    def list_characters(self) -> list[str]:
        """List all valid character IDs stored in the repository."""
        ids: list[str] = []
        for p in self.characters_dir.glob("*.json"):
            if ".tmp." in p.name:
                continue
            char_id = p.stem
            try:
                validate_character_id(char_id)
                ids.append(char_id)
            except InvalidCharacterIdError:
                continue
        return sorted(ids)
