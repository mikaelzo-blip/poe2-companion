"""Unit tests for ObservationEvent schema and ObservationBus pub/sub dispatch."""

from __future__ import annotations

import pytest

from companion.observations.bus import ObservationBus
from companion.observations.schema import (
    ObservationEvent,
    ObservationEventType,
    ObservationSource,
)


def test_observation_event_creation() -> None:
    ev = ObservationEvent.create(
        event_type=ObservationEventType.ZONE_TRANSITION,
        source=ObservationSource.CLIENT_LOG,
        character_id="char_1",
        payload={"zone": "The Riverbank", "level": 14},
    )
    assert ev.event_id is not None
    assert ev.event_type == ObservationEventType.ZONE_TRANSITION
    assert ev.source == ObservationSource.CLIENT_LOG
    assert ev.character_id == "char_1"
    assert ev.payload["zone"] == "The Riverbank"


def test_bus_subscription_and_dispatch() -> None:
    bus = ObservationBus()
    received: list[ObservationEvent] = []

    def on_zone(event: ObservationEvent) -> None:
        received.append(event)

    token = bus.subscribe(ObservationEventType.ZONE_TRANSITION, on_zone)

    # Publish matching event
    ev1 = ObservationEvent.create(
        event_type=ObservationEventType.ZONE_TRANSITION,
        source=ObservationSource.CLIENT_LOG,
        payload={"zone": "Clear Fell"},
    )
    count = bus.publish(ev1)
    assert count == 1
    assert len(received) == 1
    assert received[0].payload["zone"] == "Clear Fell"

    # Publish non-matching event -> listener not called
    ev2 = ObservationEvent.create(
        event_type=ObservationEventType.LEVEL_UP,
        source=ObservationSource.CLIENT_LOG,
        payload={"level": 2},
    )
    count2 = bus.publish(ev2)
    assert count2 == 0
    assert len(received) == 1

    # Unsubscribe
    bus.unsubscribe(token)
    bus.publish(ev1)
    assert len(received) == 1  # Not called again


def test_bus_wildcard_subscription() -> None:
    bus = ObservationBus()
    received: list[ObservationEvent] = []

    # None event_type means catch-all
    bus.subscribe(None, lambda e: received.append(e))

    bus.publish(
        ObservationEvent.create(
            event_type=ObservationEventType.LEVEL_UP,
            source=ObservationSource.CLIENT_LOG,
            payload={"level": 15},
        )
    )
    bus.publish(
        ObservationEvent.create(
            event_type=ObservationEventType.DEATH,
            source=ObservationSource.CLIENT_LOG,
            payload={},
        )
    )

    assert len(received) == 2
