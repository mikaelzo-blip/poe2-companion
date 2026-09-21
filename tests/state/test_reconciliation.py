"""Unit tests for state reconciliation from observation events."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from companion.observations.schema import (
    ObservationEvent,
    ObservationEventType,
    ObservationSource,
)
from companion.state.provenance import VerificationState
from companion.state.reconciliation import reconcile_observation
from companion.state.schema import CharacterState
from companion.state.staleness import is_observation_stale


def test_staleness_check() -> None:
    now = datetime.now(timezone.utc)
    old_ts = "2020-01-01T00:00:00+00:00"
    fresh_ts = now.isoformat()

    assert is_observation_stale(old_ts, max_age_seconds=3600) is True
    assert is_observation_stale(fresh_ts, max_age_seconds=3600) is False
    assert is_observation_stale(None) is True


def test_reconcile_level_up_observation() -> None:
    char = CharacterState.create_initial("hero_test", "HeroTest")
    assert char.level.value == 1

    event = ObservationEvent.create(
        event_type=ObservationEventType.LEVEL_UP,
        source=ObservationSource.CLIENT_LOG,
        payload={"character_name": "HeroTest", "level": 14},
    )

    updated = reconcile_observation(char, event)
    assert updated.level.value == 14
    assert updated.level.source == "client_log"
    assert updated.level.verification_state == VerificationState.VERIFIED
    assert updated.last_observed_at is not None


def test_reconcile_zone_transition() -> None:
    char = CharacterState.create_initial("hero_test", "HeroTest")
    assert char.current_zone.value == "Unknown"

    event = ObservationEvent.create(
        event_type=ObservationEventType.ZONE_TRANSITION,
        source=ObservationSource.CLIENT_LOG,
        payload={"zone": "The Forest Encampment"},
    )

    updated = reconcile_observation(char, event)
    assert updated.current_zone.value == "The Forest Encampment"
    assert updated.current_zone.source == "client_log"


def test_reconcile_death_event() -> None:
    char = CharacterState.create_initial("hero_test", "HeroTest")
    assert char.death_count.value == 0

    event = ObservationEvent.create(
        event_type=ObservationEventType.DEATH,
        source=ObservationSource.CLIENT_LOG,
        payload={"character_name": "HeroTest"},
    )

    updated = reconcile_observation(char, event)
    assert updated.death_count.value == 1


def test_reconcile_process_state_change() -> None:
    char = CharacterState.create_initial("hero_test", "HeroTest")
    assert char.session_active is False

    ev_start = ObservationEvent.create(
        event_type=ObservationEventType.PROCESS_STATE_CHANGE,
        source=ObservationSource.PROCESS,
        payload={"state": "RUNNING"},
    )
    updated = reconcile_observation(char, ev_start)
    assert updated.session_active is True

    ev_stop = ObservationEvent.create(
        event_type=ObservationEventType.PROCESS_STATE_CHANGE,
        source=ObservationSource.PROCESS,
        payload={"state": "TERMINATED"},
    )
    updated2 = reconcile_observation(updated, ev_stop)
    assert updated2.session_active is False
