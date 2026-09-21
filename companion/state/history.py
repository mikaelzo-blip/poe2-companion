"""Append-only persistent journey history logger with strict privacy sanitization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field

from companion.observations.schema import ObservationEvent

_FORBIDDEN_CHAT_PATTERNS = ("@From", "@To", "$", "#", "%")


class JourneyHistoryEntry(BaseModel):
    """Immutable record in journey_history.jsonl."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str
    character_id: str | None = None
    event_type: str
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)


class JourneyHistoryLogger:
    """Safe append-only logger for normalized game progression events."""

    def __init__(self, log_path: Path | str = "runtime/journey_history.jsonl") -> None:
        self.log_path = Path(log_path)

    def record_event(self, event: ObservationEvent) -> JourneyHistoryEntry:
        """Sanitize and append an observation event to the history log."""
        # Privacy verification
        payload_str = json.dumps(event.payload)
        for pattern in _FORBIDDEN_CHAT_PATTERNS:
            if pattern in payload_str:
                raise ValueError(f"Privacy violation: chat pattern '{pattern}' detected in observation payload")

        entry = JourneyHistoryEntry(
            entry_id=event.event_id,
            timestamp=event.timestamp.isoformat(),
            character_id=event.character_id,
            event_type=event.event_type.value,
            source=event.source.value,
            payload=event.payload,
        )

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

        return entry

    def read_history(self, limit: int | None = None) -> list[JourneyHistoryEntry]:
        """Read historical entries in chronological order."""
        if not self.log_path.exists():
            return []

        entries: list[JourneyHistoryEntry] = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                clean = line.strip()
                if clean:
                    try:
                        entries.append(JourneyHistoryEntry.model_validate_json(clean))
                    except Exception:
                        continue

        if limit is not None and limit > 0:
            return entries[-limit:]
        return entries
