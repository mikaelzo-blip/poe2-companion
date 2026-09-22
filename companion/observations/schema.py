"""Schema models for observation events across sensing providers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field


class ObservationSource(str, Enum):
    """Origin sensor producing the observation."""

    CLIENT_LOG = "client_log"
    PROCESS = "process"
    MANUAL_CHECKPOINT = "manual_checkpoint"
    VISION = "vision"
    API = "api"


class ObservationEventType(str, Enum):
    """Semantic type of game observation."""

    ZONE_TRANSITION = "zone_transition"
    LEVEL_UP = "level_up"
    DEATH = "death"
    PROCESS_STATE_CHANGE = "process_state_change"
    OBJECTIVE_COMPLETED = "objective_completed"
    STAT_OBSERVATION = "stat_observation"
    CUSTOM = "custom"


class ObservationEvent(BaseModel):
    """Normalized typed game observation event with provenance metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    event_type: ObservationEventType
    source: ObservationSource
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    character_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        event_type: ObservationEventType,
        source: ObservationSource,
        character_id: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
        event_id: str | None = None,
    ) -> ObservationEvent:
        """Convenience constructor generating unique event ID."""
        return cls(
            event_id=event_id or str(uuid.uuid4()),
            event_type=event_type,
            source=source,
            timestamp=timestamp or datetime.now(timezone.utc),
            character_id=character_id,
            payload=payload or {},
        )
