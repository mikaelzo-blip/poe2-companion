"""Read-only Client.txt log tailer with rotation safety and privacy filtering."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import os
from pathlib import Path
import re
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ParsedLogEventType(str, Enum):
    """Categorical type of recognized game log events."""

    ZONE_ENTER = "zone_enter"
    ZONE_GENERATE = "zone_generate"
    LEVEL_UP = "level_up"
    DEATH = "death"


class ParsedLogEvent(BaseModel):
    """Normalized event extracted from Client.txt without raw chat."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: ParsedLogEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


# Regex patterns for recognized log lines (Section 6.1)
# Example timestamp prefix: 2026/09/22 10:00:00 123456 [INFO Client 1234]
_TIMESTAMP_PATTERN = r"^(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"

_ZONE_GENERATE_RE = re.compile(
    r':\s+Generating level\s+(?P<level>\d+)\s+area\s+"(?P<zone>[^"]+)"'
)
_ZONE_ENTER_RE = re.compile(r':\s+Entered area\s+"(?P<zone>[^"]+)"')
_LEVEL_UP_RE = re.compile(
    r':\s+(?P<char>[a-zA-Z0-9_\u00C0-\u017F-]+)\s+is now level\s+(?P<level>\d+)'
)
_DEATH_RE = re.compile(
    r':\s+(?P<char>[a-zA-Z0-9_\u00C0-\u017F-]+)\s+has been slain'
)

# Chat indicators to drop immediately
_CHAT_PREFIXES = ("@From", "@To", "$", "#", "%")


def parse_log_line(line: str) -> ParsedLogEvent | None:
    """Parse a single raw log line enforcing strict privacy filter."""
    clean = line.strip()
    if not clean:
        return None

    # Privacy filter: discard chat immediately
    for prefix in _CHAT_PREFIXES:
        if prefix in clean:
            return None

    # Extract timestamp if present
    ts = datetime.now(timezone.utc)
    ts_match = re.match(_TIMESTAMP_PATTERN, clean)
    if ts_match:
        try:
            ts = datetime(
                year=int(ts_match.group("year")),
                month=int(ts_match.group("month")),
                day=int(ts_match.group("day")),
                hour=int(ts_match.group("hour")),
                minute=int(ts_match.group("minute")),
                second=int(ts_match.group("second")),
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass

    # Match recognized patterns
    m_enter = _ZONE_ENTER_RE.search(clean)
    if m_enter:
        zone = m_enter.group("zone")
        return ParsedLogEvent(
            event_type=ParsedLogEventType.ZONE_ENTER,
            timestamp=ts,
            payload={"zone": zone},
        )

    m_gen = _ZONE_GENERATE_RE.search(clean)
    if m_gen:
        zone = m_gen.group("zone")
        lvl = int(m_gen.group("level"))
        return ParsedLogEvent(
            event_type=ParsedLogEventType.ZONE_GENERATE,
            timestamp=ts,
            payload={"zone": zone, "area_level": lvl},
        )

    m_lvl = _LEVEL_UP_RE.search(clean)
    if m_lvl:
        char = m_lvl.group("char")
        lvl = int(m_lvl.group("level"))
        return ParsedLogEvent(
            event_type=ParsedLogEventType.LEVEL_UP,
            timestamp=ts,
            payload={"character_name": char, "level": lvl},
        )

    m_death = _DEATH_RE.search(clean)
    if m_death:
        char = m_death.group("char")
        return ParsedLogEvent(
            event_type=ParsedLogEventType.DEATH,
            timestamp=ts,
            payload={"character_name": char},
        )

    return None


class ClientLogTailer:
    """Read-only incremental log file reader with rotation handling."""

    def __init__(self, log_path: Path | str) -> None:
        self.log_path = Path(log_path)
        self._offset: int = 0
        self._partial_buffer: str = ""

    @property
    def current_offset(self) -> int:
        return self._offset

    def poll(self, max_lines: int = 1000) -> list[ParsedLogEvent]:
        """Poll the log file for new appended lines and parse recognized events."""
        if not self.log_path.exists():
            return []

        try:
            current_size = self.log_path.stat().st_size
        except OSError:
            return []

        # Handle log rotation or truncation: file shrank
        if current_size < self._offset:
            self._offset = 0
            self._partial_buffer = ""

        events: list[ParsedLogEvent] = []
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._offset)
                chunk = f.read()
                self._offset = f.tell()

            if not chunk:
                return []

            full_text = self._partial_buffer + chunk
            lines = full_text.split("\n")

            # If the last element does not end with newline, buffer it
            if not full_text.endswith("\n"):
                self._partial_buffer = lines.pop()
            else:
                self._partial_buffer = ""

            for line in lines[:max_lines]:
                ev = parse_log_line(line)
                if ev is not None:
                    events.append(ev)

        except OSError:
            return []

        return events
