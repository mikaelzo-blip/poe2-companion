"""Tests for companion observe live-status and analyze-live CLI subcommands."""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import pytest

from companion.cli import main
from companion.observe.cursor import ReviewCursorManager
from companion.observe.journal import (
    FindingOperation,
    FindingStatus,
    ReviewBatchResult,
    ReviewJournalManager,
    compute_finding_id,
    compute_review_batch_id,
)
from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.models import (
    EvidencePriority,
    FactKind,
    HealthState,
    ManifestStatus,
    ObservationEnvelope,
)
from companion.observe.reader import IncrementalStreamReader


def _setup_session(base_dir: Path, session_id: str) -> Path:
    obs_dir = base_dir / "runtime" / "observations"
    sdir = obs_dir / session_id
    sdir.mkdir(parents=True)

    # Manifest with high watermark 100
    manifest = SessionManifest(
        session_id=session_id,
        runtime_run_id="run_1",
        started_at="2026-09-23T14:00:00Z",
        status=ManifestStatus.OPEN,
        sequence_high_watermark=100,
        persisted_event_count=100,
        health_state=HealthState.HEALTHY,
    )
    ManifestManager(sdir / "session_manifest.json").save_atomic(manifest)

    # Write events and markers
    events_file = sdir / "events.jsonl"
    for seq in range(1, 101):
        env = ObservationEnvelope(
            observation_session_id=session_id,
            sequence_number=seq,
            taxonomy=FactKind.OBSERVED_FACT,
            event_type="TEST_EVENT",
            priority=EvidencePriority.MEDIUM,
            payload={"seq": seq},
        )
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(env.model_dump_json() + "\n")

    return sdir


def test_cli_analyze_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    session_id = "obs_cli_analyze"
    sdir = _setup_session(tmp_path, session_id)
    runtime_dir = str(tmp_path / "runtime")

    ret = main(["observe", "analyze-live", "--runtime", runtime_dir, "--session-id", session_id])
    assert ret == 0
    captured = capsys.readouterr()
    assert f"Analysis step complete for session {session_id}" in captured.out or "Analyzed" in captured.out

    # Verify reader_state.json created
    assert (sdir / "live_analysis" / "reader_state.json").exists()


def test_cli_live_status_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session_id = "obs_cli_live_stat"
    sdir = _setup_session(tmp_path, session_id)
    runtime_dir = str(tmp_path / "runtime")

    # Run step to generate reader state (frontier = 100)
    reader = IncrementalStreamReader(session_dir=sdir, session_id=session_id)
    reader.read_new_envelopes()
    reader.save_state()

    # Create review cursor with frontier = 80
    review_cursor_mgr = ReviewCursorManager(
        cursor_path=sdir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )
    review_cursor_mgr.record_batch_reviewed("rb_1", 1, 80)
    review_cursor_mgr.save_atomic()

    # Create active heartbeat in hermes_review_status.json
    status_file = sdir / "live_analysis" / "hermes_review_status.json"
    now_iso = datetime.now(timezone.utc).isoformat()
    status_file.write_text(
        json.dumps({
            "review_run_id": "rev_1",
            "started_at": now_iso,
            "last_heartbeat": now_iso,
            "last_reviewed_sequence": 80,
            "state": "ACTIVE",
        }),
        encoding="utf-8",
    )

    ret = main(["observe", "live-status", "--runtime", runtime_dir, "--session-id", session_id])
    assert ret == 0
    captured = capsys.readouterr()

    # Multi-tier check
    assert "[OBSERVATION]" in captured.out
    assert "[LOCAL ANALYSIS]" in captured.out
    assert "[HERMES REVIEW]" in captured.out

    # Lag checks
    assert "Reader Lag: 0" in captured.out  # 100 - 100 = 0
    assert "Review Lag: 20" in captured.out  # 100 - 80 = 20
    assert "ACTIVE" in captured.out


def test_cli_live_status_hermes_offline_honest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session_id = "obs_cli_offline"
    sdir = _setup_session(tmp_path, session_id)
    runtime_dir = str(tmp_path / "runtime")

    # Review cursor exists, but no heartbeat file!
    review_cursor_mgr = ReviewCursorManager(
        cursor_path=sdir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )
    review_cursor_mgr.record_batch_reviewed("rb_1", 1, 50)
    review_cursor_mgr.save_atomic()

    ret = main(["observe", "status", "--live", "--runtime", runtime_dir, "--session-id", session_id])
    assert ret == 0
    captured = capsys.readouterr()

    # Cursor existence alone must NEVER imply active review
    assert "OFFLINE" in captured.out or "STALE" in captured.out or "INACTIVE" in captured.out
    assert "Status: ACTIVE" not in captured.out


def test_cli_live_status_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session_id = "obs_cli_json"
    sdir = _setup_session(tmp_path, session_id)
    runtime_dir = str(tmp_path / "runtime")

    ret = main(["observe", "live-status", "--json", "--runtime", runtime_dir, "--session-id", session_id])
    assert ret == 0
    captured = capsys.readouterr()

    data = json.loads(captured.out)
    assert data["session_id"] == session_id
    assert "observation" in data
    assert "local_analysis" in data
    assert "hermes_review" in data
    assert "reader_lag" in data["local_analysis"]
    assert "review_lag" in data["hermes_review"]
