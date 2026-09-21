"""End-to-end integration test suite for Milestone 5 session monitoring and reconciler."""

from __future__ import annotations

from pathlib import Path
import pytest

from companion.observations.bus import ObservationBus
from companion.observations.schema import (
    ObservationEvent,
    ObservationEventType,
    ObservationSource,
)
from companion.objectives.runner import run_objective_pipeline
from companion.sensing.client_log import ClientLogTailer, ParsedLogEventType
from companion.sensing.process_presence import ProcessMonitor, ProcessState
from companion.state.history import JourneyHistoryLogger
from companion.state.reconciliation import reconcile_observation
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


def test_m5_end_to_end_session_lifecycle(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = CharacterStateStore(runtime_dir)
    history_logger = JourneyHistoryLogger(runtime_dir / "journey_history.jsonl")

    # 1. Initialize character at level 1
    char = CharacterState.create_initial("hero_live", "HeroLive")
    store.save_character(char)
    store.set_active_character("hero_live")
    assert char.level.value == 1
    assert char.session_active is False

    # 2. Setup decoupled observation bus and wire up reconciler & history
    bus = ObservationBus()
    bus.subscribe(None, lambda ev: history_logger.record_event(ev))

    def on_observation(ev: ObservationEvent) -> None:
        nonlocal char
        char = reconcile_observation(char, ev)
        store.save_character(char)

    bus.subscribe(None, on_observation)

    # 3. Process monitor detects game start
    game_running = True
    monitor = ProcessMonitor(
        target_executables=["PathOfExileSteam.exe"],
        detector_fn=lambda: [(9999, "PathOfExileSteam.exe")] if game_running else [],
    )

    t_start = monitor.poll()
    assert t_start.current_state == ProcessState.RUNNING

    bus.publish(
        ObservationEvent.create(
            event_type=ObservationEventType.PROCESS_STATE_CHANGE,
            source=ObservationSource.PROCESS,
            character_id=char.character_id,
            payload={"state": "RUNNING"},
        )
    )
    assert char.session_active is True

    # 4. Stream client log events (zone change, level up, chat spam)
    log_file = tmp_path / "Client.txt"
    log_file.write_text(
        "2026/09/22 14:00:00 1234 [INFO Client 1] @From AnnoyingPlayer: trade me please\n"
        "2026/09/22 14:01:00 1234 [INFO Client 1] : Entered area \"The Crypt\"\n"
        "2026/09/22 14:02:00 1234 [INFO Client 1] $GlobalPlayer: wts items\n"
        "2026/09/22 14:05:00 1234 [INFO Client 1] : HeroLive is now level 12\n",
        encoding="utf-8",
    )

    tailer = ClientLogTailer(log_file)
    parsed_events = tailer.poll()
    # Note: 2 chat lines must be dropped, leaving exactly 2 parsed events
    assert len(parsed_events) == 2

    for pe in parsed_events:
        obs_type = {
            ParsedLogEventType.ZONE_ENTER: ObservationEventType.ZONE_TRANSITION,
            ParsedLogEventType.LEVEL_UP: ObservationEventType.LEVEL_UP,
        }.get(pe.event_type, ObservationEventType.CUSTOM)

        bus.publish(
            ObservationEvent.create(
                event_type=obs_type,
                source=ObservationSource.CLIENT_LOG,
                character_id=char.character_id,
                payload=pe.payload,
                timestamp=pe.timestamp,
            )
        )

    # Verify character state was dynamically reconciled
    loaded_char = store.load_character("hero_live")
    assert loaded_char is not None
    assert loaded_char.level.value == 12
    assert loaded_char.current_zone.value == "The Crypt"
    assert loaded_char.session_active is True

    # 5. Verify objective engine consumes newly reconciled state
    obj_result = run_objective_pipeline(loaded_char, builds_dir="data/source/builds")
    assert obj_result.character_level == 12
    assert obj_result.status == "ACTIONABLE"
    assert obj_result.primary_objective is not None

    # 6. Process monitor detects game exit
    game_running = False
    t_end = monitor.poll()
    assert t_end.current_state == ProcessState.TERMINATED

    bus.publish(
        ObservationEvent.create(
            event_type=ObservationEventType.PROCESS_STATE_CHANGE,
            source=ObservationSource.PROCESS,
            character_id=char.character_id,
            payload={"state": "TERMINATED"},
        )
    )
    assert char.session_active is False

    # 7. Verify journey history log
    history = history_logger.read_history()
    assert len(history) == 4  # proc_start, zone, level_up, proc_stop
    history_file_content = (runtime_dir / "journey_history.jsonl").read_text(encoding="utf-8")
    for forbidden in ("@From", "$GlobalPlayer", "trade me"):
        assert forbidden not in history_file_content
