"""Simulated multi-phase game session for live UAT verification."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from unittest.mock import MagicMock, patch

from companion.cli import handle_state_init
from companion.runtime.checkpoint import RuntimeCheckpointStore
from companion.runtime.lease import WriterActiveError, WriterLeaseManager
from companion.runtime.models import RuntimeConfig, SessionLifecycleState
from companion.runtime.orchestrator import ContinuousRuntimeOrchestrator
from companion.runtime.status import inspect_runtime_status
from companion.sensing.process_presence import ProcessInfo, ProcessState, ProcessTransition
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


def run_synthetic_session_uat(base_dir: Path) -> dict:
    runtime_dir = base_dir / "uat_runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_file = base_dir / "Client.txt"

    # Seed initial character
    state_store = CharacterStateStore(runtime_dir)
    initial_char = CharacterState.create_initial("Witch", "Witch")
    state_store.save_character(initial_char)
    state_store.set_active_character("Witch")

    results = {}

    # Phase 1: Startup in Idle state
    config = RuntimeConfig(runtime_dir=runtime_dir, client_log_path=log_file, character_id="Witch")
    orch = ContinuousRuntimeOrchestrator(config)
    orch.initialize_startup()

    results["startup_lifecycle"] = orch.lifecycle_manager.state.value
    results["startup_clean_shutdown"] = orch.checkpoint_store.load().clean_shutdown

    # Phase 2: Game Launches & Process Detected
    proc_info = ProcessInfo(pid=5555, executable_name="PathOfExileSteam.exe")
    t_start = ProcessTransition(
        previous_state=ProcessState.IDLE,
        current_state=ProcessState.RUNNING,
        process_info=proc_info,
        is_transition=True,
    )
    orch.process_monitor.poll = MagicMock(return_value=t_start)
    orch.poll_tick()
    results["game_launch_lifecycle"] = orch.lifecycle_manager.state.value

    # Phase 3: Ingest in-combat log lines (Level up, death)
    orch.process_monitor.poll = MagicMock(return_value=ProcessTransition(
        previous_state=ProcessState.RUNNING,
        current_state=ProcessState.RUNNING,
        process_info=proc_info,
        is_transition=False,
    ))
    with open(log_file, "ab") as f:
        f.write(
            b"2026/09/23 14:00:01 123456 [INFO Client 1234] : Entered area \"The Twilight Strand\"\n"
            b"2026/09/23 14:00:05 123456 [INFO Client 1234] : Witch is now level 2\n"
            b"2026/09/23 14:00:10 123456 [INFO Client 1234] : Witch has been slain\n"
        )
    orch.poll_tick()
    results["combat_level"] = orch._active_character.level.value
    results["combat_deaths"] = orch._active_character.death_count.value
    results["combat_buffered_notifications"] = len(orch.notification_manager.queued_alerts)

    # Phase 4: Safe Zone entry (Flushes buffered notifications)
    with open(log_file, "ab") as f:
        f.write(b"2026/09/23 14:00:20 123456 [INFO Client 1234] : Entered area \"Clearfell Encampment\"\n")
    orch.poll_tick()
    results["safe_zone_buffered_notifications"] = len(orch.notification_manager.queued_alerts)
    results["current_zone"] = orch._active_character.current_zone.value

    # Phase 5: Single-writer contention while running
    contention_rc = handle_state_init(argparse.Namespace(
        runtime=str(runtime_dir),
        id="Rogue",
        name="Rogue",
        class_name="Mercenary",
        ascendancy="Gemling Legionnaire",
    ))
    results["contention_exit_code"] = contention_rc

    # Phase 6: Game Process Exits -> Bounded Exit Drain
    t_exit = ProcessTransition(
        previous_state=ProcessState.RUNNING,
        current_state=ProcessState.TERMINATED,
        process_info=proc_info,
        is_transition=True,
    )
    orch.process_monitor.poll = MagicMock(return_value=t_exit)
    with open(log_file, "ab") as f:
        f.write(b"2026/09/23 14:00:25 123456 [INFO Client 1234] : Final logout trace\n")
    orch.poll_tick()
    results["exit_lifecycle"] = orch.lifecycle_manager.state.value

    # Phase 7: Simulated Crash & Recovery
    # Release the OS file lock without calling shutdown(), simulating OS cleanup on abnormal process death
    if orch.lease_manager._lock is not None:
        orch.lease_manager._lock.release()
        orch.lease_manager._lock = None

    # Status check after ungraceful termination
    status_summary = inspect_runtime_status(runtime_dir)
    results["crash_status_detection"] = status_summary.status

    # Restart second orchestrator for crash recovery
    orch2 = ContinuousRuntimeOrchestrator(config)
    orch2.initialize_startup()
    results["crash_recovery_resumed_offset"] = orch2.current_offset
    results["crash_recovery_is_flagged"] = orch2.is_crash_recovery

    # Clean shutdown of recovered instance
    orch2.shutdown()
    results["clean_shutdown_flag"] = orch2.checkpoint_store.load().clean_shutdown

    return results


def test_synthetic_uat_execution(tmp_path: Path) -> None:
    results = run_synthetic_session_uat(tmp_path)
    assert results["startup_lifecycle"] == "IDLE"
    assert results["startup_clean_shutdown"] is False
    assert results["game_launch_lifecycle"] == "GAME_RUNNING"
    assert results["combat_level"] == 2
    assert results["combat_deaths"] == 1
    assert results["safe_zone_buffered_notifications"] == 0
    assert results["current_zone"] == "Clearfell Encampment"
    assert results["contention_exit_code"] == 1
    assert results["exit_lifecycle"] == "IDLE"
    assert results["crash_status_detection"] in ("NOT RUNNING", "STALE")
    assert results["crash_recovery_resumed_offset"] > 0
    assert results["crash_recovery_is_flagged"] is True
    assert results["clean_shutdown_flag"] is True
