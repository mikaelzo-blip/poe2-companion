"""End-to-end integration and crash consistency tests for continuous runtime."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from companion.cli import handle_session_tail, handle_state_init, handle_state_inspect
from companion.notifications.schema import (
    NotificationCategory,
    NotificationPayload,
    NotificationSeverity,
)
from companion.runtime.checkpoint import (
    FileIdentityClassification,
    RuntimeCheckpointStore,
    classify_file_identity,
    generate_file_fingerprint,
)
from companion.runtime.lease import (
    RUNTIME_WRITER_ACTIVE_CODE,
    WriterActiveError,
    WriterLeaseManager,
    guard_state_mutation,
)
from companion.runtime.models import (
    FileFingerprint,
    RuntimeCheckpoint,
    RuntimeConfig,
    SessionLifecycleState,
    WriterLease,
)
from companion.runtime.normalizer import (
    build_observation_id,
    build_source_stream_id,
    normalize_log_event,
)
from companion.runtime.notifications import BoundedNotificationQueue
from companion.runtime.orchestrator import ContinuousRuntimeOrchestrator
from companion.runtime.status import inspect_runtime_status
from companion.sensing.client_log import ParsedLogEvent, ParsedLogEventType
from companion.sensing.process_presence import ProcessInfo, ProcessState, ProcessTransition
from companion.state.reconciliation import reconcile_observation
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


@pytest.fixture
def integration_env(tmp_path: Path) -> tuple[Path, Path]:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_path / "Client.txt"
    log_file.write_bytes(b"Header line 1\nHeader line 2\n" + b"x" * 600)

    store = CharacterStateStore(runtime_dir)
    char = CharacterState.create_initial(character_id="Witch", character_name="Witch")
    store.save_character(char)
    store.set_active_character("Witch")

    return runtime_dir, log_file


def test_truncation_produces_new_epoch_and_unique_observation_ids(integration_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = integration_env
    fp = generate_file_fingerprint(log_file)
    assert fp is not None

    cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=620,
        last_file_size=log_file.stat().st_size,
        updated_at=datetime.now(timezone.utc).isoformat(),
        clean_shutdown=True,
    )

    # In-place truncation
    log_file.write_bytes(log_file.read_bytes()[:550])

    decision = classify_file_identity(log_file, cp)
    assert decision.classification == FileIdentityClassification.TRUNCATION
    assert decision.stream_epoch == 2
    assert decision.read_offset == 0

    id_epoch1 = build_observation_id(build_source_stream_id(fp.prefix_hash, 1), 0, 50, "zone_transition")
    id_epoch2 = build_observation_id(build_source_stream_id(fp.prefix_hash, decision.stream_epoch), 0, 50, "zone_transition")
    assert id_epoch1 != id_epoch2


def test_replacement_allocates_new_epoch(integration_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = integration_env
    fp = generate_file_fingerprint(log_file)
    assert fp is not None

    cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=200,
        last_file_size=log_file.stat().st_size,
        updated_at=datetime.now(timezone.utc).isoformat(),
        clean_shutdown=True,
    )

    log_file.unlink()
    log_file.write_bytes(b"Different replacement header line\n" + b"y" * 600)

    decision = classify_file_identity(log_file, cp)
    assert decision.classification == FileIdentityClassification.REPLACEMENT
    assert decision.stream_epoch == 2
    assert decision.read_offset == 0


def test_normal_append_preserves_epoch(integration_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = integration_env
    fp = generate_file_fingerprint(log_file)
    assert fp is not None

    cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=200,
        last_file_size=log_file.stat().st_size,
        updated_at=datetime.now(timezone.utc).isoformat(),
        clean_shutdown=True,
    )

    with open(log_file, "ab") as f:
        f.write(b"appended line\n")

    decision = classify_file_identity(log_file, cp)
    assert decision.classification == FileIdentityClassification.NORMAL_APPEND
    assert decision.stream_epoch == 1
    assert decision.read_offset == 200


def test_death_events_large_batch_replay_idempotency() -> None:
    char = CharacterState(character_id="Witch", character_name="Witch")
    stream_id = "test_stream:epoch_1"

    events = [
        normalize_log_event(
            parsed_event=ParsedLogEvent(event_type=ParsedLogEventType.DEATH, payload={"character_name": "Witch"}),
            source_stream_id=stream_id,
            start_offset=i * 20,
            end_offset=(i + 1) * 20,
            character_id="Witch",
        )
        for i in range(120)
    ]

    for ev in events:
        char = reconcile_observation(char, ev)

    assert char.death_count.value == 120

    # Replay all 120 events after simulated crash
    for ev in events:
        char = reconcile_observation(char, ev)

    assert char.death_count.value == 120


def test_distinct_death_events_advance_watermark_and_counter() -> None:
    char = CharacterState(character_id="Witch", character_name="Witch")
    ev1 = normalize_log_event(
        parsed_event=ParsedLogEvent(event_type=ParsedLogEventType.DEATH, payload={"character_name": "Witch"}),
        source_stream_id="stream:epoch_1",
        start_offset=10,
        end_offset=30,
        character_id="Witch",
    )
    ev2 = normalize_log_event(
        parsed_event=ParsedLogEvent(event_type=ParsedLogEventType.DEATH, payload={"character_name": "Witch"}),
        source_stream_id="stream:epoch_1",
        start_offset=30,
        end_offset=60,
        character_id="Witch",
    )
    char = reconcile_observation(char, ev1)
    char = reconcile_observation(char, ev2)
    assert char.death_count.value == 2
    assert any("watermark:stream:epoch_1:60" in ref for ref in char.death_count.evidence_refs)


def test_counted_event_watermark_resets_on_epoch_change() -> None:
    char = CharacterState(character_id="Witch", character_name="Witch")
    ev1 = normalize_log_event(
        parsed_event=ParsedLogEvent(event_type=ParsedLogEventType.DEATH, payload={"character_name": "Witch"}),
        source_stream_id="stream:epoch_1",
        start_offset=100,
        end_offset=200,
        character_id="Witch",
    )
    char = reconcile_observation(char, ev1)
    assert char.death_count.value == 1

    ev2 = normalize_log_event(
        parsed_event=ParsedLogEvent(event_type=ParsedLogEventType.DEATH, payload={"character_name": "Witch"}),
        source_stream_id="stream:epoch_2",
        start_offset=10,
        end_offset=30,
        character_id="Witch",
    )
    char = reconcile_observation(char, ev2)
    assert char.death_count.value == 2
    assert any("watermark:stream:epoch_2:30" in ref for ref in char.death_count.evidence_refs)


def test_counter_and_watermark_survive_state_save_and_reload(tmp_path: Path) -> None:
    store = CharacterStateStore(tmp_path / "runtime")
    char = CharacterState.create_initial(character_id="Witch", character_name="Witch")
    ev = normalize_log_event(
        parsed_event=ParsedLogEvent(event_type=ParsedLogEventType.DEATH, payload={"character_name": "Witch"}),
        source_stream_id="stream:epoch_1",
        start_offset=10,
        end_offset=50,
        character_id="Witch",
    )
    reconciled = reconcile_observation(char, ev)
    store.save_character(reconciled)

    reloaded = store.load_character("Witch")
    assert reloaded.death_count.value == 1
    assert any("watermark:stream:epoch_1:50" in ref for ref in reloaded.death_count.evidence_refs)


def test_concurrent_runtimes_one_winner(integration_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = integration_env
    config = RuntimeConfig(runtime_dir=runtime_dir, client_log_path=log_file, character_id="Witch")

    orch1 = ContinuousRuntimeOrchestrator(config)
    orch1.initialize_startup()

    orch2 = ContinuousRuntimeOrchestrator(config)
    with pytest.raises(WriterActiveError) as exc_info:
        orch2.initialize_startup()

    assert RUNTIME_WRITER_ACTIVE_CODE in str(exc_info.value)
    orch1.shutdown()


def test_mutating_cli_refused_while_runtime_active(integration_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = integration_env
    config = RuntimeConfig(runtime_dir=runtime_dir, client_log_path=log_file, character_id="Witch")
    orch = ContinuousRuntimeOrchestrator(config)
    orch.initialize_startup()

    # handle_state_init should fail
    rc_init = handle_state_init(argparse.Namespace(
        runtime=str(runtime_dir),
        id="char_x",
        name="Char X",
        class_name="Mercenary",
        ascendancy="Gemling Legionnaire",
    ))
    assert rc_init == 1

    # handle_session_tail should fail
    rc_tail = handle_session_tail(argparse.Namespace(
        runtime=str(runtime_dir),
        char="Witch",
        log=None,
        json=False,
    ))
    assert rc_tail == 1

    # read-only command succeeds
    rc_inspect = handle_state_inspect(argparse.Namespace(
        runtime=str(runtime_dir),
        id="Witch",
        json=False,
    ))
    assert rc_inspect == 0

    orch.shutdown()


def test_stale_metadata_cannot_block_new_owner(integration_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = integration_env

    # Write stale metadata with dead PID
    stale = WriterLease(
        owner_pid=9999999,
        run_id="dead-run",
        acquired_at="2026-09-23T10:00:00Z",
        last_heartbeat="2026-09-23T10:00:01Z",
        character_id="Witch",
    )
    (runtime_dir / "writer_lease.json").write_text(stale.model_dump_json(), encoding="utf-8")

    config = RuntimeConfig(runtime_dir=runtime_dir, client_log_path=log_file, character_id="Witch")
    orch = ContinuousRuntimeOrchestrator(config)
    # Should succeed because OS lock is not held
    orch.initialize_startup()
    assert orch.lease_manager.current_lease is not None
    assert orch.lease_manager.current_lease.run_id == orch.run_id
    orch.shutdown()


def test_batch_coalesces_objective_reevaluation(integration_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = integration_env
    config = RuntimeConfig(runtime_dir=runtime_dir, client_log_path=log_file, character_id="Witch")
    orch = ContinuousRuntimeOrchestrator(config)
    orch.initialize_startup()

    # Append 3 level lines in a single batch
    lines = (
        b"2026/09/23 12:00:01 123456 [INFO Client 1234] : Witch is now level 2\n"
        b"2026/09/23 12:00:02 123456 [INFO Client 1234] : Witch is now level 3\n"
        b"2026/09/23 12:00:03 123456 [INFO Client 1234] : Witch is now level 4\n"
    )
    with open(log_file, "ab") as f:
        f.write(lines)

    with patch("companion.runtime.orchestrator.run_objective_pipeline", wraps=ContinuousRuntimeOrchestrator) as mock_obj:
        with patch("companion.runtime.orchestrator.save_current_objective_artifact") as mock_save_obj:
            orch.poll_tick()
            # Only one objective evaluation cycle should occur for the whole batch
            assert mock_save_obj.call_count <= 1

    orch.shutdown()


def test_game_exit_triggers_bounded_final_drain(integration_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = integration_env
    config = RuntimeConfig(runtime_dir=runtime_dir, client_log_path=log_file, character_id="Witch")
    orch = ContinuousRuntimeOrchestrator(config)
    orch.initialize_startup()

    # Game transitions from RUNNING to TERMINATED
    proc_info = ProcessInfo(pid=1234, executable_name="PathOfExileSteam.exe")
    orch.process_monitor.poll = MagicMock(return_value=ProcessTransition(
        previous_state=ProcessState.RUNNING,
        current_state=ProcessState.TERMINATED,
        process_info=proc_info,
        is_transition=True,
    ))

    # Append final exit line before poll
    final_line = b"2026/09/23 12:05:00 123456 [INFO Client 1234] : Entered area \"Lioneye's Watch\"\n"
    with open(log_file, "ab") as f:
        f.write(final_line)

    orch.poll_tick()

    # State must be idle after exit drain and finalization
    assert orch.lifecycle_manager.state == SessionLifecycleState.IDLE
    assert orch._active_character is not None
    assert orch._active_character.current_zone.value == "Lioneye's Watch"

    orch.shutdown()


def test_notification_queue_bounded_and_deduplicated() -> None:
    queue = BoundedNotificationQueue(max_depth=20)
    for i in range(25):
        payload = NotificationPayload.create(
            title="Objective Advisory",
            message=f"Take node {i}",
            severity=NotificationSeverity.INFO,
            category=NotificationCategory.OPTIMIZATION,
            dedupe_key=f"passive:node_{i % 5}",  # Only 5 unique keys!
        )
        queue.push(payload)

    # Since there are only 5 keys, in-place replacement keeps queue length at 5!
    assert len(queue) == 5


def test_runtime_status_active_vs_stale_or_dead(integration_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = integration_env
    config = RuntimeConfig(runtime_dir=runtime_dir, client_log_path=log_file, character_id="Witch")
    orch = ContinuousRuntimeOrchestrator(config)
    orch.initialize_startup()

    # Active status
    summary_active = inspect_runtime_status(runtime_dir)
    assert summary_active.status == "ACTIVE"
    assert summary_active.writer_lock_held is True

    orch.shutdown()

    # After shutdown, status is NOT RUNNING
    summary_stopped = inspect_runtime_status(runtime_dir)
    assert summary_stopped.status == "NOT RUNNING"
    assert summary_stopped.writer_lock_held is False


def test_client_log_opened_strictly_read_only(integration_env: tuple[Path, Path]) -> None:
    runtime_dir, log_file = integration_env
    config = RuntimeConfig(runtime_dir=runtime_dir, client_log_path=log_file, character_id="Witch")
    orch = ContinuousRuntimeOrchestrator(config)

    # Verify that orchestrator only uses "rb" mode
    real_open = open
    open_modes = []

    def tracking_open(file, mode="r", *args, **kwargs):
        if str(file) == str(log_file):
            open_modes.append(mode)
        return real_open(file, mode, *args, **kwargs)

    with patch("builtins.open", side_effect=tracking_open):
        orch.initialize_startup()
        orch.poll_tick()
        orch.shutdown()

    # Every open of Client.txt must be strictly read-only binary ("rb")
    assert len(open_modes) > 0
    for mode in open_modes:
        assert mode == "rb", f"Unexpected open mode: {mode}"
