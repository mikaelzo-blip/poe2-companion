"""Tests for session manifest and crash recovery."""

from pathlib import Path
import pytest

from companion.observe.models import ManifestStatus, HealthState
from companion.observe.manifest import SessionManifest, ManifestManager
from companion.observe.storage import ObservationStorageManager


def test_manifest_reconciliation_invariant():
    # Successful clean session: persisted + dropped == watermark
    clean_manifest = SessionManifest(
        session_id="obs_clean",
        runtime_run_id="run_1",
        started_at="2026-09-23T14:00:00Z",
        ended_at="2026-09-23T14:10:00Z",
        status=ManifestStatus.CLOSED,
        sequence_high_watermark=100,
        persisted_event_count=90,
        dropped_event_count=10,
        pending_event_count=0,
    )
    assert clean_manifest.is_reconciled() is True

    # Incomplete session with pending: persisted + dropped + pending == watermark
    incomplete_manifest = SessionManifest(
        session_id="obs_inc",
        runtime_run_id="run_1",
        started_at="2026-09-23T14:00:00Z",
        status=ManifestStatus.INCOMPLETE,
        sequence_high_watermark=100,
        persisted_event_count=80,
        dropped_event_count=10,
        pending_event_count=10,
    )
    assert incomplete_manifest.is_reconciled() is True

    # Broken accounting
    broken_manifest = SessionManifest(
        session_id="obs_broken",
        runtime_run_id="run_1",
        started_at="2026-09-23T14:00:00Z",
        status=ManifestStatus.CLOSED,
        sequence_high_watermark=100,
        persisted_event_count=80,
        dropped_event_count=10,  # 80 + 10 != 100
        pending_event_count=0,
    )
    assert broken_manifest.is_reconciled() is False


def test_manifest_manager_atomic_save_and_load(tmp_path: Path):
    manifest_path = tmp_path / "session_manifest.json"
    mgr = ManifestManager(manifest_path=manifest_path)

    manifest = SessionManifest(
        session_id="obs_mgr_test",
        runtime_run_id="run_1",
        started_at="2026-09-23T14:00:00Z",
        status=ManifestStatus.OPEN,
        sequence_high_watermark=1,
        persisted_event_count=1,
    )
    mgr.save_atomic(manifest)

    # File exists and matches
    assert manifest_path.exists()
    loaded = mgr.load()
    assert loaded is not None
    assert loaded.session_id == "obs_mgr_test"
    assert loaded.status == ManifestStatus.OPEN


def test_startup_recovery_of_unfinalized_sessions(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    dead_session_dir = base_dir / "obs_dead"
    dead_session_dir.mkdir(parents=True)

    manifest_mgr = ManifestManager(manifest_path=dead_session_dir / "session_manifest.json")
    dead_manifest = SessionManifest(
        session_id="obs_dead",
        runtime_run_id="run_dead",
        started_at="2026-09-23T14:00:00Z",
        status=ManifestStatus.OPEN,
        sequence_high_watermark=50,
        persisted_event_count=45,
        dropped_event_count=5,
    )
    manifest_mgr.save_atomic(dead_manifest)

    # Also put a dummy event file to check raw files are preserved
    raw_file = dead_session_dir / "events.jsonl"
    raw_file.write_text('{"event_id": "test"}\n', encoding="utf-8")

    # Run recovery
    recovered = ObservationStorageManager.recover_unfinalized_sessions(base_dir)
    assert "obs_dead" in recovered

    updated_manifest = manifest_mgr.load()
    assert updated_manifest.status in (ManifestStatus.INCOMPLETE, ManifestStatus.ABORTED)
    assert updated_manifest.aborted_reason == "UNEXPECTED_TERMINATION"
    assert updated_manifest.ended_at is not None

    # Raw file remains intact
    assert raw_file.exists()
    assert "test" in raw_file.read_text(encoding="utf-8")
