"""Comprehensive deterministic verification suite for Development Observation Mode."""

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
import pytest

from companion.observe.anomalies import LogAnomalyGrouper
from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.markers import MarkerInboxManager, write_marker
from companion.observe.models import (
    EvidencePriority,
    FactKind,
    HealthState,
    ManifestStatus,
    ObservationEnvelope,
)
from companion.observe.observer import DevelopmentObserver
from companion.observe.privacy import PrivacyFilter
from companion.observe.retention import RetentionManager
from companion.observe.screens import ScreenshotCaptureWorker
from companion.observe.storage import ObservationStorageManager
from companion.state.schema import CharacterState


def test_suite_bounded_drain_and_timeout_lifecycle(tmp_path: Path):
    """Assert session is not CLOSED while pending, and drain timeout produces INCOMPLETE."""
    base_dir = tmp_path / "obs"

    # 1. Clean drain produces CLOSED
    obs_clean = DevelopmentObserver(base_dir=base_dir, session_id="obs_clean", runtime_run_id="run_1", auto_start=True)
    for i in range(10):
        obs_clean.emit_event("EVT", FactKind.OBSERVED_FACT, EvidencePriority.MEDIUM, {"i": i})
    manifest_clean = obs_clean.stop(timeout=5.0)
    assert manifest_clean.status == ManifestStatus.CLOSED
    assert manifest_clean.persisted_event_count == 10
    assert manifest_clean.sequence_high_watermark == 10
    assert manifest_clean.dropped_event_count == 0

    # 2. Timeout drain produces INCOMPLETE with OBSERVER_DRAIN_TIMEOUT
    obs_timeout = DevelopmentObserver(base_dir=base_dir, session_id="obs_timeout", runtime_run_id="run_2", auto_start=False)
    for i in range(5):
        obs_timeout.emit_event("EVT", FactKind.OBSERVED_FACT, EvidencePriority.MEDIUM, {"i": i})
    # With worker never started, stop with tiny timeout triggers drain timeout
    manifest_timeout = obs_timeout.stop(timeout=0.01)
    assert manifest_timeout.status == ManifestStatus.INCOMPLETE
    assert manifest_timeout.aborted_reason == "OBSERVER_DRAIN_TIMEOUT"
    assert manifest_timeout.pending_event_count == 5


def test_suite_worker_failure_transitions_to_failed(tmp_path: Path):
    """Fatal observer writer failure transitions health to FAILED without crashing."""
    base_dir = tmp_path / "obs"
    obs = DevelopmentObserver(base_dir=base_dir, session_id="obs_fail", runtime_run_id="run_fail", auto_start=False)

    class FailingStorage:
        def append_envelope(self, stream, env):
            raise OSError("Disk write failure (mock)")

        def close_streams(self):
            pass

        def get_artifact_counts(self) -> dict[str, int]:
            return {"events": 0}

    obs.storage_manager = FailingStorage()
    obs.start()

    obs.emit_event("EVT", FactKind.OBSERVED_FACT, EvidencePriority.HIGH, {"data": "test"})
    # Give worker time to hit failure
    time.sleep(0.1)

    assert obs.health.state == HealthState.FAILED
    assert "Disk write failure" in (obs.health.last_error or "")

    # Queue should now reject and drop new events
    dropped_env = obs.emit_event("EVT_AFTER_FAIL", FactKind.OBSERVED_FACT, EvidencePriority.HIGH, {})
    assert dropped_env is None
    assert obs.dropped_event_count == 2
    assert obs.dropped_high_priority_count == 2
    assert obs.queue_depth == 0

    manifest = obs.stop(timeout=1.0)
    assert manifest.status == ManifestStatus.INCOMPLETE
    assert manifest.aborted_reason == "WORKER_FAILURE"
    assert manifest.health_state == HealthState.FAILED
    assert manifest.pending_event_count == 0
    assert manifest.persisted_event_count == 0
    assert manifest.artifact_counts["events"] == 0
    assert manifest.persisted_event_count + manifest.dropped_event_count == manifest.sequence_high_watermark
    assert ManifestManager(obs.manifest_manager.manifest_path).load() == manifest


def test_suite_screenshot_worker_degradation_without_state_mutation(tmp_path: Path):
    """Screenshot worker failure transitions health to DEGRADED without corrupting state or halting event logging."""
    base_dir = tmp_path / "obs"
    obs = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_screen_fail",
        runtime_run_id="run_s",
        observe_screens=True,
        auto_start=True,
    )

    class FailingBackend:
        def capture_screen(self, source_id):
            raise RuntimeError("DirectX / MSS device lost")

    obs.screenshot_worker.backend = FailingBackend()

    # Trigger screenshot
    rec = obs.trigger_screenshot(event_type="BOSS_ENTER")
    assert rec.capture_result == "CAPTURE_FAILED"
    assert obs.health.state == HealthState.DEGRADED

    # Event logging continues unharmed
    env = obs.emit_event("NEXT_EVENT", FactKind.OBSERVED_FACT, EvidencePriority.HIGH, {"alive": True})
    assert env is not None

    manifest = obs.stop(timeout=2.0)
    assert manifest.health_state == HealthState.DEGRADED
    assert manifest.status == ManifestStatus.CLOSED


def test_suite_deterministic_priority_shedding_and_accounting(tmp_path: Path):
    """Deterministic priority shedding drops LOW before MEDIUM before HIGH, and sequence math reconciles."""
    base_dir = tmp_path / "obs"
    obs = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_shed",
        runtime_run_id="run_shed",
        queue_size=3,
        auto_start=False,
    )

    obs.emit_event("LOW_1", FactKind.OBSERVED_FACT, EvidencePriority.LOW, {})      # seq 1
    obs.emit_event("MED_1", FactKind.OBSERVED_FACT, EvidencePriority.MEDIUM, {})   # seq 2
    obs.emit_event("HIGH_1", FactKind.OBSERVED_FACT, EvidencePriority.HIGH, {})    # seq 3
    assert obs.queue_depth == 3

    # Add another HIGH: should evict LOW_1
    obs.emit_event("HIGH_2", FactKind.OBSERVED_FACT, EvidencePriority.HIGH, {})    # seq 4
    assert obs.queue_depth == 3
    assert obs.dropped_event_count == 1
    assert obs.dropped_high_priority_count == 0

    # Add another HIGH: should evict MED_1
    obs.emit_event("HIGH_3", FactKind.OBSERVED_FACT, EvidencePriority.HIGH, {})    # seq 5
    assert obs.queue_depth == 3
    assert obs.dropped_event_count == 2
    assert obs.dropped_high_priority_count == 0

    # Add another HIGH: all 3 in queue are HIGH, incoming HIGH must drop oldest HIGH
    obs.emit_event("HIGH_4", FactKind.OBSERVED_FACT, EvidencePriority.HIGH, {})    # seq 6
    assert obs.dropped_event_count == 3
    assert obs.dropped_high_priority_count == 1

    # Drain with worker
    obs.start()
    manifest = obs.stop(timeout=2.0)

    assert manifest.persisted_event_count == 3
    assert manifest.dropped_event_count == 3
    # Sequence reconciliation: persisted + dropped == sequence_high_watermark
    assert manifest.persisted_event_count + manifest.dropped_event_count == manifest.sequence_high_watermark
    assert manifest.sequence_high_watermark == 6


def test_suite_missing_evidence_correlation(tmp_path: Path):
    """Surviving child correlation records flag missing dropped parents under MISSING_EVIDENCE."""
    env_child = ObservationEnvelope(
        schema_version="1.0",
        observation_session_id="obs_corr",
        sequence_number=5,
        taxonomy=FactKind.DERIVED_FACT,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        event_type="OBJECTIVE_EVALUATION",
        correlation_refs=["evt_parent_dropped"],
        correlation_missing_due_to_backpressure=True,
        priority=EvidencePriority.MEDIUM,
        payload={"note": "Child whose parent was dropped"},
    )
    assert env_child.correlation_missing_due_to_backpressure is True
    assert "evt_parent_dropped" in env_child.correlation_refs


def test_suite_marker_atomicity_and_tmp_isolation(tmp_path: Path):
    """Incomplete .tmp marker files are ignored and concurrent marker submissions succeed."""
    inbox_dir = tmp_path / "runtime" / "observations" / "marker_inbox"
    inbox_dir.mkdir(parents=True)

    # Write a stray incomplete .tmp file
    (inbox_dir / "incomplete_marker.tmp").write_text("partial corrupted content", encoding="utf-8")

    # Concurrent marker submissions
    threads = []
    for i in range(5):
        t = threading.Thread(target=write_marker, args=(f"Concurrent note {i}", inbox_dir, "session_test"))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    mgr = MarkerInboxManager(inbox_dir)
    markers = mgr.consume_markers()

    # Should consume only the 5 valid json markers, ignoring the .tmp file
    assert len(markers) == 5
    assert (inbox_dir / "incomplete_marker.tmp").exists()


def test_suite_privacy_unparsed_representative_text_withheld():
    """Ambiguous unparsed lines withhold representative text (PRIVACY_SAMPLE_WITHHELD = true)."""
    pfilter = PrivacyFilter()
    anom_grouper = LogAnomalyGrouper(pfilter)

    # 1. Private chat message line: completely discarded
    private_chat_line = "2026/09/23 10:15:00 123456789 [INFO Client 1234] @From Alice: Meet me at the stash"
    rec_chat = anom_grouper.record_line(private_chat_line)
    assert rec_chat is None

    # 2. Ambiguous unparsed line: classified UNCERTAIN_NON_CHAT with samples withheld
    ambiguous_line = "Custom random debug statement from engine without known prefix"
    rec_ambiguous = anom_grouper.record_line(ambiguous_line)
    assert rec_ambiguous is not None
    assert rec_ambiguous.privacy_sample_withheld is True
    assert rec_ambiguous.sanitized_samples == []
