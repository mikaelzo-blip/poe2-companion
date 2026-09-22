"""Unit tests for runtime cross-process status inspection and heartbeat detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import pytest

from companion.runtime.lease import WriterLeaseManager
from companion.runtime.models import RuntimeStatus, SessionLifecycleState
from companion.runtime.status import inspect_runtime_status, is_pid_alive


def test_is_pid_alive_current_process() -> None:
    assert is_pid_alive(os.getpid()) is True
    assert is_pid_alive(9999999) is False


def test_inspect_status_no_runtime(tmp_path: Path) -> None:
    summary = inspect_runtime_status(tmp_path / "runtime")
    assert summary.status == "NOT RUNNING"
    assert summary.writer_lock_held is False


def test_inspect_status_active(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Hold writer lease
    manager = WriterLeaseManager(runtime_dir)
    manager.acquire(run_id="run-1", character_id="Witch")

    # Publish fresh heartbeat
    now_iso = datetime.now(timezone.utc).isoformat()
    status = RuntimeStatus(
        runtime_pid=os.getpid(),
        lifecycle_state=SessionLifecycleState.SESSION_ACTIVE,
        session_id="session-1",
        game_process_running=True,
        game_pid=1234,
        last_heartbeat=now_iso,
        last_consumed_offset=1024,
        active_character_id="Witch",
        started_at=now_iso,
    )
    (runtime_dir / "runtime_status.json").write_text(status.model_dump_json(indent=2), encoding="utf-8")

    summary = inspect_runtime_status(runtime_dir)
    assert summary.status == "ACTIVE"
    assert summary.writer_lock_held is True
    assert summary.runtime_pid == os.getpid()
    assert summary.active_character_id == "Witch"

    manager.release()


def test_inspect_status_stale_heartbeat(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Hold writer lease
    manager = WriterLeaseManager(runtime_dir)
    manager.acquire(run_id="run-1")

    # Publish stale heartbeat (> 10s ago)
    old_iso = (datetime.now(timezone.utc) - timedelta(seconds=25)).isoformat()
    status = RuntimeStatus(
        runtime_pid=os.getpid(),
        lifecycle_state=SessionLifecycleState.SESSION_ACTIVE,
        session_id="session-1",
        game_process_running=True,
        game_pid=1234,
        last_heartbeat=old_iso,
        last_consumed_offset=1024,
        active_character_id="Witch",
        started_at=old_iso,
    )
    (runtime_dir / "runtime_status.json").write_text(status.model_dump_json(indent=2), encoding="utf-8")

    summary = inspect_runtime_status(runtime_dir)
    assert summary.status == "STALE"
    assert summary.heartbeat_age_seconds is not None
    assert summary.heartbeat_age_seconds > 10.0

    manager.release()


def test_inspect_status_metadata_active_but_lock_not_held(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Do NOT acquire lock (lock not held), but JSON claims active
    now_iso = datetime.now(timezone.utc).isoformat()
    status = RuntimeStatus(
        runtime_pid=os.getpid(),
        lifecycle_state=SessionLifecycleState.SESSION_ACTIVE,
        session_id="session-1",
        game_process_running=True,
        game_pid=1234,
        last_heartbeat=now_iso,
        last_consumed_offset=1024,
        active_character_id="Witch",
        started_at=now_iso,
    )
    (runtime_dir / "runtime_status.json").write_text(status.model_dump_json(indent=2), encoding="utf-8")

    summary = inspect_runtime_status(runtime_dir)
    # Lock is not held, so it cannot be ACTIVE!
    assert summary.status in ("NOT RUNNING", "STALE")
    assert summary.writer_lock_held is False
