"""Unit tests for runtime fault isolation: malformed bytes, sink exceptions, and transient errors."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from companion.runtime.models import RuntimeConfig
from companion.runtime.orchestrator import ContinuousRuntimeOrchestrator
from companion.sensing.client_log import parse_log_line
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


def test_malformed_utf8_and_corrupt_log_lines_do_not_crash(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_path / "Client.txt"

    store = CharacterStateStore(runtime_dir)
    char = CharacterState.create_initial(character_id="Witch", character_name="Witch")
    store.save_character(char)
    store.set_active_character("Witch")

    config = RuntimeConfig(runtime_dir=runtime_dir, client_log_path=log_file, character_id="Witch")
    orch = ContinuousRuntimeOrchestrator(config)
    orch.initialize_startup()

    # Write corrupt binary bytes mixed with valid log lines
    garbage = b"\xff\xfe\x00\x00\x80\x99\xff corrupt binary garbage\n"
    valid_line = b"2026/09/23 12:00:01 123456 [INFO Client 1234] : Witch is now level 2\n"
    another_corrupt = b"Random non-timestamp line with no structure\n"
    valid_line2 = b"2026/09/23 12:00:02 123456 [INFO Client 1234] : Witch is now level 3\n"

    with open(log_file, "wb") as f:
        f.write(garbage + valid_line + another_corrupt + valid_line2)

    # Should not raise exception
    orch.poll_tick()

    # Reconciled valid lines successfully despite intervening corruption
    assert orch._active_character is not None
    assert orch._active_character.level.value == 3
    orch.shutdown()


def test_notification_sink_exception_does_not_crash_loop(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_path / "Client.txt"

    store = CharacterStateStore(runtime_dir)
    char = CharacterState.create_initial(character_id="Witch", character_name="Witch")
    store.save_character(char)
    store.set_active_character("Witch")

    config = RuntimeConfig(runtime_dir=runtime_dir, client_log_path=log_file, character_id="Witch")
    orch = ContinuousRuntimeOrchestrator(config)
    orch.initialize_startup()

    # Mock notification_manager.dispatch to raise an error
    orch.notification_manager.dispatch = MagicMock(side_effect=RuntimeError("Audio sink device lost"))

    valid_line = b"2026/09/23 12:00:01 123456 [INFO Client 1234] : Entered area \"Lioneye's Watch\"\n"
    with open(log_file, "wb") as f:
        f.write(valid_line)

    # Must catch or isolate the notification error so loop does not crash
    orch.poll_tick()

    assert orch._active_character is not None
    assert orch._active_character.current_zone.value == "Lioneye's Watch"
    orch.shutdown()


def test_missing_log_file_does_not_crash_loop(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_path / "NonExistentClient.txt"

    store = CharacterStateStore(runtime_dir)
    char = CharacterState.create_initial(character_id="Witch", character_name="Witch")
    store.save_character(char)
    store.set_active_character("Witch")

    config = RuntimeConfig(runtime_dir=runtime_dir, client_log_path=log_file, character_id="Witch")
    orch = ContinuousRuntimeOrchestrator(config)
    orch.initialize_startup()

    # Poll tick with missing log file
    orch.poll_tick()
    orch.shutdown()
