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
    """Safe append-only logger for normalized game progression events with replay deduplication."""

    def __init__(self, log_path: Path | str = "runtime/journey_history.jsonl") -> None:
        self.log_path = Path(log_path)
        self._known_entry_ids: set[str] | None = None

    def _ensure_known_ids(self) -> set[str]:
        if self._known_entry_ids is None:
            self._known_entry_ids = set()
            if self.log_path.exists():
                with open(self.log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        clean = line.strip()
                        if clean:
                            try:
                                data = json.loads(clean)
                                eid = data.get("entry_id")
                                if eid:
                                    self._known_entry_ids.add(eid)
                            except Exception:
                                continue
        return self._known_entry_ids

    def record_event(self, event: ObservationEvent) -> JourneyHistoryEntry:
        """Sanitize and append an observation event to the history log, deduplicating replays."""
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

        known_ids = self._ensure_known_ids()
        if entry.entry_id in known_ids:
            # Replay of already recorded event; suppress duplicate append
            return entry

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

        known_ids.add(entry.entry_id)
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
