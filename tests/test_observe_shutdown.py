"""Tests for DevelopmentObserver orderly bounded shutdown and queue drain."""

from pathlib import Path
import time
import pytest

from companion.observe.models import (
    EvidencePriority,
    FactKind,
    ManifestStatus,
)
from companion.observe.observer import DevelopmentObserver


def test_clean_shutdown_drains_queue_and_marks_closed(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    observer = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_clean_shutdown",
        runtime_run_id="run_1",
        queue_size=50,
    )
    observer.start()

    # Emit multiple events
    for i in range(10):
        observer.emit_event(
            event_type=f"TICK_{i}",
            taxonomy=FactKind.OBSERVED_FACT,
            priority=EvidencePriority.MEDIUM,
        )

    # Clean shutdown
    manifest = observer.stop(timeout=5.0)

    assert manifest.status == ManifestStatus.CLOSED
    assert manifest.pending_event_count == 0
    assert manifest.persisted_event_count + manifest.dropped_event_count == manifest.sequence_high_watermark
    assert manifest.sequence_high_watermark == 10
    assert observer.is_stopped is True


def test_shutdown_timeout_aborts_drain_and_marks_incomplete(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    observer = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_timeout_shutdown",
        runtime_run_id="run_1",
        queue_size=100,
    )

    # Simulate a stuck / very slow writer
    def _slow_append(*args, **kwargs):
        time.sleep(2.0)

    observer.storage_manager.append_envelope = _slow_append
    observer.start()

    # Enqueue multiple events
    for i in range(5):
        observer.emit_event(
            event_type=f"SLOW_TICK_{i}",
            taxonomy=FactKind.OBSERVED_FACT,
            priority=EvidencePriority.HIGH,
        )

    # Shutdown with a very short timeout (0.3s)
    t0 = time.perf_counter()
    manifest = observer.stop(timeout=0.3)
    elapsed = time.perf_counter() - t0

    # Ensure shutdown did not hang indefinitely
    assert elapsed < 1.5
    assert manifest.status == ManifestStatus.INCOMPLETE
    assert manifest.aborted_reason == "OBSERVER_DRAIN_TIMEOUT"
    assert manifest.pending_event_count > 0
    assert (
        manifest.persisted_event_count
        + manifest.dropped_event_count
        + manifest.pending_event_count
        == manifest.sequence_high_watermark
    )
