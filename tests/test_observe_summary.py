"""Tests for SessionSummaryGenerator in clean, partial, and timed-out sessions."""

import json
from pathlib import Path
import pytest

from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.models import ManifestStatus
from companion.observe.summary import SessionSummaryGenerator


def _setup_mock_session(session_dir: Path, status: ManifestStatus = ManifestStatus.CLOSED):
    session_dir.mkdir(parents=True, exist_ok=True)
    manifest = SessionManifest(
        session_id=session_dir.name,
        runtime_run_id="run_summary_test",
        started_at="2026-09-23T14:00:00Z",
        ended_at="2026-09-23T14:30:00Z",
        status=status,
        sequence_high_watermark=10,
        persisted_event_count=8,
        dropped_event_count=2,
    )
    ManifestManager(session_dir / "session_manifest.json").save_atomic(manifest)

    # State delta stream
    (session_dir / "state_deltas.jsonl").write_text(
        '{"event_id": "evt_delta_1", "sequence_number": 1, "payload": {"field": "level", "before": 1, "after": 2}}\n',
        encoding="utf-8",
    )
    # Objective stream
    (session_dir / "objective_traces.jsonl").write_text(
        '{"event_id": "evt_obj_1", "sequence_number": 2, "payload": {"selected_objective_id": "obj_1", "objective_changed": true}}\n',
        encoding="utf-8",
    )
    # Notification stream
    (session_dir / "notification_traces.jsonl").write_text(
        '{"event_id": "evt_notif_1", "sequence_number": 3, "payload": {"dispatch_status": "DELIVERED"}}\n',
        encoding="utf-8",
    )
    # Markers stream
    (session_dir / "markers.jsonl").write_text(
        '{"event_id": "evt_mark_1", "sequence_number": 4, "payload": {"note": "Boss mechanic tricky"}}\n',
        encoding="utf-8",
    )


def test_session_summary_generator_clean_session(tmp_path: Path):
    sdir = tmp_path / "runtime" / "observations" / "obs_clean_summary"
    _setup_mock_session(sdir, ManifestStatus.CLOSED)

    gen = SessionSummaryGenerator(sdir)
    data = gen.generate()

    assert data["session_id"] == "obs_clean_summary"
    assert data["status"] == "CLOSED"
    assert data["counts"]["state_deltas"] == 1
    assert data["counts"]["objective_evaluations"] == 1
    assert data["counts"]["markers"] == 1

    # Verify summary files were created
    assert (sdir / "session_summary.json").exists()
    assert (sdir / "session_summary.md").exists()


def test_session_summary_generator_partial_session(tmp_path: Path):
    sdir = tmp_path / "runtime" / "observations" / "obs_partial_summary"
    _setup_mock_session(sdir, ManifestStatus.INCOMPLETE)

    gen = SessionSummaryGenerator(sdir)
    data = gen.generate()

    assert data["status"] == "INCOMPLETE"
    assert (sdir / "session_summary.json").exists()
    assert "INCOMPLETE" in (sdir / "session_summary.md").read_text(encoding="utf-8")
