"""Bounded rolling backup management and recovery for character states.

Ensures that:
- Only valid, uncorrupted canonical states are copied to backup.
- Canonical state files are never moved or deleted before replacement.
- Old backups are pruned only after successful replacement (retention max 3).
- Automated recovery restores from the newest valid backup if canonical is corrupt.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

MAX_BACKUPS = 3


class BackupError(RuntimeError):
    """Raised when backup operations fail."""
    pass


def is_valid_state_file(file_path: Path) -> bool:
    """Check whether a file exists, is non-empty, and contains valid JSON."""
    if not file_path.is_file() or file_path.stat().st_size == 0:
        return False
    try:
        content = file_path.read_text(encoding="utf-8")
        parsed = json.loads(content)
        return isinstance(parsed, dict) and "character_id" in parsed
    except Exception:
        return False


def copy_canonical_to_backup(
    canonical_file: Path,
    backup_dir: Path,
    timestamp: str | None = None,
) -> Path | None:
    """Safely copy existing valid canonical file to a timestamped backup.
    
    Returns backup Path if copied, or None if canonical was absent or invalid.
    Does NOT move or delete canonical file.
    """
    if not canonical_file.exists():
        return None

    # Corrupt or unreadable canonical files must never displace valid backups
    if not is_valid_state_file(canonical_file):
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"state.{ts}.bak"

    shutil.copyfile(canonical_file, backup_path)
    return backup_path


def prune_backups(backup_dir: Path, max_backups: int = MAX_BACKUPS) -> list[Path]:
    """Prune historical backups exceeding max_backups, keeping the newest ones.
    
    Returns list of deleted backup paths.
    """
    if not backup_dir.is_dir():
        return []

    # Find all .bak files sorted by filename/timestamp ascending
    backups = sorted(
        [p for p in backup_dir.glob("state.*.bak") if p.is_file()],
        key=lambda p: p.name,
    )

    deleted: list[Path] = []
    if len(backups) > max_backups:
        to_delete = backups[: len(backups) - max_backups]
        for b in to_delete:
            b.unlink(missing_ok=True)
            deleted.append(b)

    return deleted


def find_latest_valid_backup(backup_dir: Path) -> Path | None:
    """Find the most recent valid backup file, searching newest to oldest."""
    if not backup_dir.is_dir():
        return None

    backups = sorted(
        [p for p in backup_dir.glob("state.*.bak") if p.is_file()],
        key=lambda p: p.name,
        reverse=True,
    )

    for b in backups:
        if is_valid_state_file(b):
            return b
    return None
