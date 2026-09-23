"""Tests for wiring ObservationTap into ContinuousRuntimeOrchestrator."""

from pathlib import Path
import pytest

from companion.runtime.models import RuntimeConfig
from companion.runtime.orchestrator import ContinuousRuntimeOrchestrator


def test_observer_disabled_by_default_zero_worker_threads_and_zero_io(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    log_file = tmp_path / "Client.txt"
    log_file.write_text("", encoding="utf-8")

    config = RuntimeConfig(
        runtime_dir=runtime_dir,
        client_log_path=log_file,
        observe_dev=False,
    )
    orchestrator = ContinuousRuntimeOrchestrator(config)
    orchestrator.initialize_startup()

    assert orchestrator.observer is None
    obs_dir = runtime_dir / "observations"
    assert not obs_dir.exists()

    orchestrator.shutdown()
    assert not obs_dir.exists()


def test_observer_enabled_records_runtime_events_and_shuts_down_cleanly(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    log_file = tmp_path / "Client.txt"
    log_file.write_text("", encoding="utf-8")

    config = RuntimeConfig(
        runtime_dir=runtime_dir,
        client_log_path=log_file,
        observe_dev=True,
    )
    orchestrator = ContinuousRuntimeOrchestrator(config)
    orchestrator.initialize_startup()

    assert orchestrator.observer is not None
    assert orchestrator.observer.health.state.value == "HEALTHY"

    # Append a log line
    log_file.write_text("2026/09/23 14:00:00 12345678 abc [ENGINE] Entered area \"The Riverbank\"\n", encoding="utf-8")
    orchestrator.poll_tick()

    assert orchestrator.observer.sequence_high_watermark > 0

    orchestrator.shutdown()
    assert orchestrator.observer.is_stopped is True
