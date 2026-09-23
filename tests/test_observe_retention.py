"""Tests for global boundary retention manager."""

from pathlib import Path
import pytest

from companion.observe.models import ManifestStatus
from companion.observe.manifest import SessionManifest, ManifestManager
from companion.observe.retention import RetentionManager


def _create_fake_session(base_dir: Path, session_id: str, size_bytes: int, started_at: str, pinned: bool = False):
    sdir = base_dir / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    mgr = ManifestManager(manifest_path=sdir / "session_manifest.json")
    manifest = SessionManifest(
        session_id=session_id,
        runtime_run_id="run_1",
        started_at=started_at,
        status=ManifestStatus.CLOSED,
        sequence_high_watermark=10,
        persisted_event_count=10,
    )
    mgr.save_atomic(manifest)
    if pinned:
        (sdir / ".pinned").touch()
    # Write payload file to occupy size
    (sdir / "events.jsonl").write_bytes(b"0" * size_bytes)


def test_retention_protects_active_finalizing_pinned_and_reports(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    reports_dir = tmp_path / "docs" / "audits"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "audit_report.md"
    report_file.write_text("Permanent audit report", encoding="utf-8")

    # Create 3 sessions, each 100 KB
    _create_fake_session(base_dir, "obs_old_1", 100_000, "2026-09-23T10:00:00Z")
    _create_fake_session(base_dir, "obs_pinned", 100_000, "2026-09-23T11:00:00Z", pinned=True)
    _create_fake_session(base_dir, "obs_active", 100_000, "2026-09-23T12:00:00Z")
    _create_fake_session(base_dir, "obs_new_closed", 100_000, "2026-09-23T13:00:00Z")

    # Set quota to 250 KB (total is ~400 KB, so oldest unpinned unactive must be evicted)
    retention = RetentionManager(
        base_dir=base_dir,
        quota_bytes=250_000,
    )

    evicted = retention.clean_storage(
        protected_session_ids={"obs_active", "obs_new_closed"}
    )

    assert "obs_old_1" in evicted
    assert "obs_pinned" not in evicted
    assert "obs_active" not in evicted
    assert "obs_new_closed" not in evicted

    # Verify obs_old_1 was removed
    assert not (base_dir / "obs_old_1").exists()
    # Verify report was never touched
    assert report_file.exists()
    assert report_file.read_text(encoding="utf-8") == "Permanent audit report"

    # Verify retention log was written
    log_file = base_dir / "retention_log.jsonl"
    assert log_file.exists()
    assert "obs_old_1" in log_file.read_text(encoding="utf-8")
