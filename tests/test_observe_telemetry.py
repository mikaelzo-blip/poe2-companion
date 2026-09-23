"""Tests for periodic operational telemetry flushes."""

from pathlib import Path
import time
import pytest

from companion.observe.observer import DevelopmentObserver
from companion.runtime.models import RuntimeConfig
from companion.runtime.orchestrator import ContinuousRuntimeOrchestrator


def test_development_observer_records_operational_telemetry(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    observer = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_telem_test",
        runtime_run_id="run_1",
        auto_start=False,
    )

    telem = observer.record_telemetry(
        loop_duration_ms=15.2,
        log_poll_latency_ms=2.1,
        enqueue_latency_ms=0.3,
        observer_queue_depth=5,
        queue_high_watermark=10,
        writer_latency_ms=4.0,
        screenshot_capture_latency_ms=0.0,
        storage_bytes=1024,
    )
    assert telem.loop_duration_ms == 15.2
    assert telem.queue_high_watermark == 10
    assert observer.sequence_high_watermark == 1


def test_continuous_runtime_periodic_telemetry_flush(tmp_path: Path):
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

    # Simulate poll tick with telemetry
    orchestrator.poll_tick()
    # Telemetry should be emitted periodically or during poll_tick
    assert orchestrator.observer.sequence_high_watermark >= 1

    orchestrator.shutdown()
