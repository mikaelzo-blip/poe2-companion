"""Atomic cross-process manual marker inbox writer and consumer."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
import uuid

from companion.observe.models import UserMarkerRecord


def write_marker(
    note: str,
    inbox_dir: Path,
    session_id: str | None = None,
) -> tuple[Path, str]:
    """Atomically write a manual marker to the inbox via .tmp -> .json rename."""
    inbox_dir.mkdir(parents=True, exist_ok=True)
    marker_id = f"marker_{uuid.uuid4().hex}"
    created_at = datetime.now(timezone.utc).isoformat()

    data = {
        "marker_id": marker_id,
        "created_at": created_at,
        "note": note,
        "session_id": session_id,
    }

    tmp_path = inbox_dir / f"{marker_id}.tmp"
    final_path = inbox_dir / f"{marker_id}.json"

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, final_path)
    return final_path, marker_id


class MarkerInboxManager:
    """Consumes complete .json marker files from the inbox directory."""

    def __init__(self, inbox_dir: Path) -> None:
        self.inbox_dir = Path(inbox_dir)

    def consume_markers(self) -> list[UserMarkerRecord]:
        """Read and drain complete marker records, ignoring .tmp files."""
        if not self.inbox_dir.exists():
            return []

        records: list[UserMarkerRecord] = []
        for file_path in sorted(self.inbox_dir.glob("*.json")):
            if file_path.name.endswith(".tmp"):
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                raw = json.loads(content)
                rec = UserMarkerRecord(
                    marker_id=raw["marker_id"],
                    created_at=raw["created_at"],
                    note=raw["note"],
                    character_id=raw.get("character_id"),
                    zone=raw.get("zone"),
                    top_objective_id=raw.get("top_objective_id"),
                    correlated_sequence_number=raw.get("correlated_sequence_number"),
                )
                records.append(rec)
                file_path.unlink(missing_ok=True)
            except Exception:
                # Corrupt or concurrent file access; skip for this cycle
                pass

        return records


def is_session_active(runtime_dir: Path) -> bool:
    """Check runtime_status.json to determine if continuous companion session is active."""
    status_file = Path(runtime_dir) / "runtime_status.json"
    if not status_file.exists():
        return False

    try:
        data = json.loads(status_file.read_text(encoding="utf-8"))
        state = data.get("lifecycle_state")
        return state in ("SESSION_ACTIVE", "GAME_RUNNING")
    except Exception:
        return False
