"""Data models for session recaps and progression summaries."""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field


class SessionRecap(BaseModel):
    """Structured metrics and summary for a gameplay session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    character_id: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    duration_seconds: float = 0.0
    starting_level: int | None = None
    ending_level: int | None = None
    levels_gained: int = 0
    zones_visited: list[str] = Field(default_factory=list)
    total_deaths: int = 0
    total_events: int = 0
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
