"""Tests for companion observe CLI subcommands."""

import json
from pathlib import Path
import pytest

from companion.cli import build_parser, main
from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.models import ManifestStatus


def test_cli_parser_observe_mark():
    parser = build_parser()
    args = parser.parse_args([
        "observe",
        "mark",
        "Found interesting boss pattern",
        "--runtime", "my_runtime",
    ])
    assert args.subcommand == "observe"
    assert args.observe_action == "mark"
    assert args.note == "Found interesting boss pattern"
    assert args.runtime == "my_runtime"


def test_cli_observe_mark_unattached(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True)

    rc = main(["observe", "mark", "Test note", "--runtime", str(runtime_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No active observation session" in out

    # Verify marker was saved in inbox
    inbox = runtime_dir / "observations" / "marker_inbox"
    assert len(list(inbox.glob("*.json"))) == 1


def test_cli_observe_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    runtime_dir = tmp_path / "runtime"
    obs_dir = runtime_dir / "observations" / "obs_test_session"
    obs_dir.mkdir(parents=True)

    mgr = ManifestManager(obs_dir / "session_manifest.json")
    manifest = SessionManifest(
        session_id="obs_test_session",
        runtime_run_id="run_1",
        started_at="2026-09-23T14:00:00Z",
        status=ManifestStatus.OPEN,
        sequence_high_watermark=42,
        persisted_event_count=40,
        dropped_event_count=2,
    )
    mgr.save_atomic(manifest)

    # Human status
    rc = main(["observe", "status", "--runtime", str(runtime_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "obs_test_session" in out
    assert "OPEN" in out

    # JSON status
    rc_json = main(["observe", "status", "--runtime", str(runtime_dir), "--json"])
    assert rc_json == 0
    out_json = capsys.readouterr().out
    data = json.loads(out_json)
    assert data["session_id"] == "obs_test_session"
    assert data["sequence_high_watermark"] == 42


def test_cli_observe_cleanup(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    runtime_dir = tmp_path / "runtime"
    obs_dir = runtime_dir / "observations" / "obs_old"
    obs_dir.mkdir(parents=True)
    mgr = ManifestManager(obs_dir / "session_manifest.json")
    manifest = SessionManifest(
        session_id="obs_old",
        runtime_run_id="run_1",
        started_at="2026-09-23T10:00:00Z",
        status=ManifestStatus.CLOSED,
        sequence_high_watermark=5,
        persisted_event_count=5,
    )
    mgr.save_atomic(manifest)
    (obs_dir / "events.jsonl").write_bytes(b"0" * 50_000)

    rc = main(["observe", "cleanup", "--runtime", str(runtime_dir), "--prune", "--quota-bytes", "1000"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Cleaned up" in out or "Evicted" in out or "obs_old" in out
