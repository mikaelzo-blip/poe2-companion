"""Unit tests for runtime models and schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from companion.runtime.models import (
    FileFingerprint,
    RuntimeCheckpoint,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeStatus,
    SessionLifecycleState,
    WriterLease,
)


def test_session_lifecycle_state_enum() -> None:
    assert SessionLifecycleState.IDLE.value == "IDLE"
    assert SessionLifecycleState.GAME_RUNNING.value == "GAME_RUNNING"
    assert SessionLifecycleState.SESSION_ACTIVE.value == "SESSION_ACTIVE"
    assert SessionLifecycleState.GAME_EXITED.value == "GAME_EXITED"


def test_file_fingerprint_valid() -> None:
    fp = FileFingerprint(
        path="C:/Games/PoE2/Client.txt",
        created_at=1700000000.0,
        prefix_hash="a" * 64,
        file_size_at_fingerprint=1024,
    )
    assert fp.path == "C:/Games/PoE2/Client.txt"
    assert fp.created_at == 1700000000.0
    assert fp.prefix_hash == "a" * 64
    assert fp.file_size_at_fingerprint == 1024

    # Frozen
    with pytest.raises(ValidationError):
        fp.path = "new/path"  # type: ignore[misc]


def test_runtime_checkpoint_valid() -> None:
    fp = FileFingerprint(
        path="C:/Games/PoE2/Client.txt",
        created_at=1700000000.0,
        prefix_hash="a" * 64,
        file_size_at_fingerprint=1024,
    )
    cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=500,
        last_file_size=1024,
        updated_at="2026-09-23T12:00:00Z",
        clean_shutdown=False,
    )
    assert cp.schema_version == "1.0"
    assert cp.stream_epoch == 1
    assert cp.last_offset == 500
    assert cp.clean_shutdown is False
    assert cp.clean_shutdown_at is None
    assert isinstance(cp.run_id, str) and len(cp.run_id) > 0


def test_writer_lease_valid() -> None:
    lease = WriterLease(
        owner_pid=1234,
        run_id="run-1",
        acquired_at="2026-09-23T12:00:00Z",
        last_heartbeat="2026-09-23T12:00:01Z",
        character_id="Witch1",
    )
    assert lease.owner_pid == 1234
    assert lease.character_id == "Witch1"


def test_runtime_status_valid() -> None:
    status = RuntimeStatus(
        runtime_pid=1234,
        lifecycle_state=SessionLifecycleState.SESSION_ACTIVE,
        session_id="session-1",
        game_process_running=True,
        game_pid=5678,
        last_heartbeat="2026-09-23T12:00:01Z",
        last_consumed_offset=500,
        active_character_id="Witch1",
        started_at="2026-09-23T12:00:00Z",
    )
    assert status.runtime_pid == 1234
    assert status.lifecycle_state == SessionLifecycleState.SESSION_ACTIVE
    assert status.game_process_running is True


def test_runtime_config_defaults() -> None:
    cfg = RuntimeConfig()
    assert cfg.poll_interval == 1.0
    assert cfg.backfill is False
    assert cfg.verbose is False
    assert cfg.character_id is None


def test_runtime_event_valid() -> None:
    evt = RuntimeEvent(
        event_type="STATE_CHANGE",
        timestamp="2026-09-23T12:00:00Z",
        payload={"trigger": "zone_change"},
    )
    assert evt.event_type == "STATE_CHANGE"
    assert evt.payload == {"trigger": "zone_change"}
