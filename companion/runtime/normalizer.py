"""Observation normalization with stable source stream generation and provenance."""

from __future__ import annotations

from typing import Any

from companion.observations.schema import ObservationEvent, ObservationEventType, ObservationSource
from companion.sensing.client_log import ParsedLogEvent, ParsedLogEventType


def build_source_stream_id(prefix_hash: str, stream_epoch: int) -> str:
    """Generate stable stream identifier incorporating fingerprint and stream epoch."""
    # Use first 16 characters of prefix hash if longer, or full string
    short_hash = prefix_hash[:16] if len(prefix_hash) >= 16 else prefix_hash
    return f"{short_hash}:epoch_{stream_epoch}"


def build_observation_id(
    source_stream_id: str,
    start_offset: int,
    end_offset: int,
    event_type: str,
) -> str:
    """Generate globally stable observation identifier preventing collisions across epochs."""
    return f"{source_stream_id}:{start_offset}:{end_offset}:{event_type}"


_EVENT_TYPE_MAP: dict[ParsedLogEventType, ObservationEventType] = {
    ParsedLogEventType.ZONE_ENTER: ObservationEventType.ZONE_TRANSITION,
    ParsedLogEventType.ZONE_GENERATE: ObservationEventType.ZONE_TRANSITION,
    ParsedLogEventType.LEVEL_UP: ObservationEventType.LEVEL_UP,
    ParsedLogEventType.DEATH: ObservationEventType.DEATH,
}


def normalize_log_event(
    parsed_event: ParsedLogEvent,
    source_stream_id: str,
    start_offset: int,
    end_offset: int,
    character_id: str | None = None,
) -> ObservationEvent:
    """Normalize a parsed Client.txt event into a strongly-typed ObservationEvent."""
    obs_type = _EVENT_TYPE_MAP.get(parsed_event.event_type, ObservationEventType.CUSTOM)
    obs_id = build_observation_id(
        source_stream_id=source_stream_id,
        start_offset=start_offset,
        end_offset=end_offset,
        event_type=obs_type.value,
    )

    payload: dict[str, Any] = dict(parsed_event.payload)
    payload["start_offset"] = start_offset
    payload["end_offset"] = end_offset
    payload["source_stream_id"] = source_stream_id

    return ObservationEvent.create(
        event_id=obs_id,
        event_type=obs_type,
        source=ObservationSource.CLIENT_LOG,
        character_id=character_id,
        payload=payload,
        timestamp=parsed_event.timestamp,
    )
