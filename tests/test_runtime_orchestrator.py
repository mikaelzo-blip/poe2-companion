"""Unit tests for ContinuousRuntimeOrchestrator deterministic pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from companion.runtime.models import RuntimeConfig, SessionLifecycleState
from companion.runtime.orchestrator import ContinuousRuntimeOrchestrator
from companion.sensing.process_presence import ProcessInfo, ProcessState, ProcessTransition
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


@pytest.fixture
def test_env(tmp_path: Path) -> tuple[Path, Path]:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_path / "Client.txt"
    log_file.write_bytes(b"Header line 1\nHeader line 2\n" + b"x" * 600)

    # Initialize a character in store
    store = CharacterStateStore(runtime_dir)
    char = CharacterState.create_initial(character_id="Witch", character_name="Witch")
    store.save_character(char)
    store.set_active_character("Witch")

    return runtime_dir, log_file


def test_dirty_on_start_persisted_before_ingestion(test_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = test_env
    config = RuntimeConfig(
        runtime_dir=runtime_dir,
        client_log_path=log_file,
        character_id="Witch",
        poll_interval=0.01,
    )

    orchestrator = ContinuousRuntimeOrchestrator(config)
    orchestrator.initialize_startup()

    # Checkpoint on disk must be dirty immediately
    cp = orchestrator.checkpoint_store.load()
    assert cp is not None
    assert cp.clean_shutdown is False
    assert cp.clean_shutdown_at is None
    assert cp.run_id == orchestrator.run_id

    # Writer lease must be active
    assert orchestrator.lease_manager.current_lease is not None
    assert orchestrator.lease_manager.current_lease.run_id == orchestrator.run_id

    orchestrator.shutdown()


def test_crash_recovery_resumes_from_checkpoint_offset(test_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = test_env

    # Simulate prior unclean checkpoint at offset 200
    config = RuntimeConfig(
        runtime_dir=runtime_dir,
        client_log_path=log_file,
        character_id="Witch",
        poll_interval=0.01,
    )
    orchestrator1 = ContinuousRuntimeOrchestrator(config)
    orchestrator1.initialize_startup()

    # Artificially set checkpoint offset to 200 and crash (release lock without clean marker)
    cp = orchestrator1.checkpoint_store.load()
    assert cp is not None
    cp_modified = cp.model_copy(update={"last_offset": 200, "clean_shutdown": False})
    orchestrator1.checkpoint_store.save(cp_modified)
    orchestrator1.lease_manager.release()

    # Second orchestrator starts
    orchestrator2 = ContinuousRuntimeOrchestrator(config)
    orchestrator2.initialize_startup()

    assert orchestrator2.is_crash_recovery is True
    assert orchestrator2.current_offset == 200

    orchestrator2.shutdown()


def test_poll_batch_ingests_and_persists_state_and_checkpoint(test_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = test_env
    config = RuntimeConfig(
        runtime_dir=runtime_dir,
        client_log_path=log_file,
        character_id="Witch",
        poll_interval=0.01,
    )

    orchestrator = ContinuousRuntimeOrchestrator(config)
    orchestrator.initialize_startup()

    initial_offset = orchestrator.current_offset

    # Append a level-up line to log_file
    level_line = b"2026/09/23 12:00:00 123456 [INFO Client 1234] : Witch is now level 2\n"
    with open(log_file, "ab") as f:
        f.write(level_line)

    # Mock process monitor to return running game
    orchestrator.process_monitor.poll = MagicMock(return_value=ProcessTransition(
        previous_state=ProcessState.RUNNING,
        current_state=ProcessState.RUNNING,
        process_info=ProcessInfo(pid=1234, executable_name="PathOfExileSteam.exe"),
        is_transition=False,
    ))

    # Execute one poll tick
    orchestrator.poll_tick()

    assert orchestrator.current_offset > initial_offset

    # Check updated CharacterState on disk
    store = CharacterStateStore(runtime_dir)
    reloaded_char = store.load_character("Witch")
    assert reloaded_char.level.value == 2

    # Check updated checkpoint on disk
    cp = orchestrator.checkpoint_store.load()
    assert cp is not None
    assert cp.last_offset == orchestrator.current_offset
    assert cp.clean_shutdown is False

    orchestrator.shutdown()


def test_backfill_suppresses_notifications_and_transitions_to_live(test_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = test_env

    # Append historical zone line
    zone_line1 = b"2026/09/23 10:00:00 123456 [INFO Client 1234] : Entered area \"The Coast\"\n"
    with open(log_file, "ab") as f:
        f.write(zone_line1)

    config = RuntimeConfig(
        runtime_dir=runtime_dir,
        client_log_path=log_file,
        character_id="Witch",
        poll_interval=0.01,
        backfill=True,
    )

    orchestrator = ContinuousRuntimeOrchestrator(config)
    orchestrator.initialize_startup()

    assert orchestrator.is_backfill_mode is True
    assert orchestrator.startup_backfill_end_offset == log_file.stat().st_size
    assert orchestrator.notification_manager.suppress_notifications is True

    # Process batch up to backfill end
    orchestrator.poll_tick()

    # Now backfill catch-up is complete, should transition to live
    assert orchestrator.is_backfill_mode is False
    assert orchestrator.notification_manager.suppress_notifications is False

    orchestrator.shutdown()
