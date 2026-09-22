"""Unit tests for OS-backed lifetime single-writer lease and mutator contention."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import pytest

from companion.cli import handle_session_tail, handle_state_init, handle_state_inspect
from companion.runtime.lease import (
    RUNTIME_WRITER_ACTIVE_CODE,
    WriterActiveError,
    WriterLeaseManager,
)
from companion.runtime.models import WriterLease
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


def test_atomic_lease_acquisition(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    manager = WriterLeaseManager(runtime_dir)
    lease = manager.acquire(run_id="run-1", character_id="Witch")

    assert lease.owner_pid == os.getpid()
    assert lease.run_id == "run-1"
    assert lease.character_id == "Witch"
    assert (runtime_dir / "writer_lease.lock").exists()
    assert (runtime_dir / "writer_lease.json").exists()

    manager.release()
    assert manager._lock is None


def test_concurrent_acquisition_raises_runtime_writer_active(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    manager1 = WriterLeaseManager(runtime_dir)
    manager1.acquire(run_id="run-1")

    # Second acquisition must fail immediately with RUNTIME_WRITER_ACTIVE
    manager2 = WriterLeaseManager(runtime_dir)
    with pytest.raises(WriterActiveError) as exc_info:
        manager2.acquire(run_id="run-2")

    assert RUNTIME_WRITER_ACTIVE_CODE in str(exc_info.value)

    # Release manager1
    manager1.release()

    # Now manager2 can acquire successfully
    lease2 = manager2.acquire(run_id="run-2")
    assert lease2.run_id == "run-2"
    manager2.release()


def test_stale_metadata_does_not_block_acquisition_if_os_lock_free(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Write stale metadata simulating crash of previous process
    stale_lease = WriterLease(
        owner_pid=999999,
        run_id="stale-run",
        acquired_at="2026-09-23T10:00:00Z",
        last_heartbeat="2026-09-23T10:00:01Z",
        character_id="StaleChar",
    )
    (runtime_dir / "writer_lease.json").write_text(stale_lease.model_dump_json(), encoding="utf-8")

    manager = WriterLeaseManager(runtime_dir)
    # Lock is free, so new owner acquires without issue
    lease = manager.acquire(run_id="new-run-1")
    assert lease.run_id == "new-run-1"
    assert lease.owner_pid == os.getpid()
    manager.release()


def test_held_lock_cannot_be_stolen_even_with_old_heartbeat(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    manager1 = WriterLeaseManager(runtime_dir)
    manager1.acquire(run_id="run-1")

    # Manually tamper with JSON to make heartbeat appear ancient (e.g. 1 hour ago)
    stale_json = WriterLease(
        owner_pid=os.getpid(),
        run_id="run-1",
        acquired_at="2026-09-23T09:00:00Z",
        last_heartbeat="2026-09-23T09:00:00Z",
    )
    (runtime_dir / "writer_lease.json").write_text(stale_json.model_dump_json(), encoding="utf-8")

    # Manager 2 attempts to acquire; OS lock is held so it MUST NOT steal
    manager2 = WriterLeaseManager(runtime_dir)
    with pytest.raises(WriterActiveError) as exc_info:
        manager2.acquire(run_id="run-2")

    assert RUNTIME_WRITER_ACTIVE_CODE in str(exc_info.value)
    manager1.release()


def test_mutator_commands_blocked_by_active_runtime_lease(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Initialize a character first
    store = CharacterStateStore(runtime_dir)
    char = CharacterState.create_initial(character_id="TestChar", character_name="TestChar")
    store.save_character(char)
    store.set_active_character("TestChar")

    # Hold writer lease
    manager = WriterLeaseManager(runtime_dir)
    manager.acquire(run_id="active-runtime-run")

    # 1. handle_state_init should fail with code 1 and log error
    init_args = argparse.Namespace(
        runtime=str(runtime_dir),
        id="char_2",
        name="Char Two",
        class_name="Mercenary",
        ascendancy="Gemling Legionnaire",
    )
    rc_init = handle_state_init(init_args)
    assert rc_init == 1
    captured_init = capsys.readouterr()
    assert RUNTIME_WRITER_ACTIVE_CODE in captured_init.err

    # 2. handle_session_tail should fail with code 1 and log error
    tail_args = argparse.Namespace(
        runtime=str(runtime_dir),
        char="TestChar",
        log=None,
        json=False,
    )
    rc_tail = handle_session_tail(tail_args)
    assert rc_tail == 1
    captured_tail = capsys.readouterr()
    assert RUNTIME_WRITER_ACTIVE_CODE in captured_tail.err

    # 3. Read-only command (handle_state_inspect) MUST succeed even while lock is held!
    inspect_args = argparse.Namespace(
        runtime=str(runtime_dir),
        id="TestChar",
        json=False,
    )
    rc_inspect = handle_state_inspect(inspect_args)
    assert rc_inspect == 0
    captured_inspect = capsys.readouterr()
    assert "TestChar" in captured_inspect.out

    manager.release()
