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


def test_cli_live_status_review_queue_metrics(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session_id = "obs_cli_queue_stat"
    sdir = _setup_session(tmp_path, session_id)
    runtime_dir = str(tmp_path / "runtime")
    live_dir = sdir / "live_analysis"

    # Setup reader at 150
    reader = IncrementalStreamReader(session_dir=sdir, session_id=session_id)
    reader.save_state()

    # Cursor at 100 with reviewed_ahead_ranges [[126, 150]]
    cursor_mgr = ReviewCursorManager(
        cursor_path=live_dir / "hermes_review_cursor.json",
        session_id=session_id,
    )
    cursor_mgr.record_batch_reviewed("rb_1", 1, 100)
    cursor_mgr.record_batch_reviewed("rb_3", 126, 150)
    cursor_mgr.save_atomic()

    # Requests:
    # batch_1 (1..100) - completed
    # batch_2 (101..125) - claimed
    # batch_3 (126..150) - completed ahead
    # batch_4 (151..175) - pending
    req_dir = live_dir / "review_requests"
    claims_dir = live_dir / "review_claims"
    batches_dir = live_dir / "review_batches"
    req_dir.mkdir(parents=True, exist_ok=True)
    claims_dir.mkdir(parents=True, exist_ok=True)
    batches_dir.mkdir(parents=True, exist_ok=True)

    for b_id, s, e in [("rb_1", 1, 100), ("rb_2", 101, 125), ("rb_3", 126, 150), ("rb_4", 151, 175)]:
        (req_dir / f"{b_id}.json").write_text(
            json.dumps({"review_batch_id": b_id, "sequence_start": s, "sequence_end": e, "evidence_ids": []}),
            encoding="utf-8",
        )

    # Completed batches
    (batches_dir / "rb_1.json").write_text(json.dumps({"review_batch_id": "rb_1"}), encoding="utf-8")
    (batches_dir / "rb_3.json").write_text(json.dumps({"review_batch_id": "rb_3"}), encoding="utf-8")

    # Claim for rb_2
    now = datetime.now(timezone.utc)
    future = (now + datetime.resolution * 1000000).isoformat()  # valid future
    from datetime import timedelta
    future_str = (now + timedelta(seconds=180)).isoformat()
    (claims_dir / "rb_2.clm_01.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "review_batch_id": "rb_2",
            "claim_id": "clm_01",
            "review_run_id": "run_01",
            "claimed_at": now.isoformat(),
            "lease_expires_at": future_str,
        }),
        encoding="utf-8",
    )

    ret = main(["observe", "live-status", "--json", "--runtime", runtime_dir, "--session-id", session_id])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    hr = data["hermes_review"]
    assert hr["pending_requests"] == 1  # rb_4
    assert hr["claimed_requests"] == 1  # rb_2
    assert hr["completed_responses"] == 2  # rb_1, rb_3
    assert hr["reviewed_ahead_ranges"] == [[126, 150]]

    # Text format
    ret2 = main(["observe", "live-status", "--runtime", runtime_dir, "--session-id", session_id])
    assert ret2 == 0
    captured2 = capsys.readouterr()
    assert "Pending Requests: 1" in captured2.out
    assert "Claimed Requests: 1" in captured2.out
    assert "Completed Responses: 2" in captured2.out

