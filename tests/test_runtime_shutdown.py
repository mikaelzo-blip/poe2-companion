"""Unit tests for runtime graceful shutdown and signal handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from companion.runtime.models import RuntimeConfig
from companion.runtime.orchestrator import ContinuousRuntimeOrchestrator
from companion.sensing.process_presence import ProcessInfo, ProcessState, ProcessTransition
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


def test_graceful_shutdown_marks_clean_and_releases_lock(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_path / "Client.txt"
    log_file.write_bytes(b"Header line 1\nHeader line 2\n" + b"x" * 600)

    store = CharacterStateStore(runtime_dir)
    char = CharacterState.create_initial(character_id="Witch", character_name="Witch")
    store.save_character(char)
    store.set_active_character("Witch")

    config = RuntimeConfig(
        runtime_dir=runtime_dir,
        client_log_path=log_file,
        character_id="Witch",
        poll_interval=0.01,
    )

    orchestrator = ContinuousRuntimeOrchestrator(config)
    orchestrator.initialize_startup()

    # Verify lock held before shutdown
    assert orchestrator.lease_manager.is_lock_actively_held() is True
    cp_initial = orchestrator.checkpoint_store.load()
    assert cp_initial is not None
    assert cp_initial.clean_shutdown is False

    # Execute graceful shutdown
    orchestrator.shutdown()

    # Lock must be released
    assert orchestrator.lease_manager.is_lock_actively_held() is False

    # Checkpoint must now be marked clean_shutdown = True with timestamp
    cp_final = orchestrator.checkpoint_store.load()
    assert cp_final is not None
    assert cp_final.clean_shutdown is True
    assert cp_final.clean_shutdown_at is not None
