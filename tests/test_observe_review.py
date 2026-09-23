"""Tests for companion observe review report generation."""

import json
from pathlib import Path
import pytest

from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.models import ManifestStatus
from companion.observe.review import generate_development_observation_report


def test_generate_development_observation_report_structure(tmp_path: Path):
    sdir = tmp_path / "runtime" / "observations" / "obs_review_session"
    sdir.mkdir(parents=True, exist_ok=True)

    manifest = SessionManifest(
        session_id="obs_review_session",
        runtime_run_id="run_review_123",
        started_at="2026-09-23T10:00:00Z",
        ended_at="2026-09-23T10:20:00Z",
        status=ManifestStatus.CLOSED,
        persisted_event_count=5,
    )
    ManifestManager(sdir / "session_manifest.json").save_atomic(manifest)

    # Add an anomaly
    anomalies = {
        "anom_hash_1": {
            "signature": "anom_hash_1",
            "first_seen_event_id": "evt_anom_1",
            "last_seen_event_id": "evt_anom_2",
            "first_seen_timestamp": "2026-09-23T10:05:00Z",
            "last_seen_timestamp": "2026-09-23T10:06:00Z",
            "occurrence_count": 2,
            "sample_message": "Failed to parse unknown area transition",
        }
    }
    (sdir / "anomalies.json").write_text(json.dumps(anomalies), encoding="utf-8")

    # Add single weak anomaly (count = 1)
    anomalies["anom_hash_weak"] = {
        "signature": "anom_hash_weak",
        "first_seen_event_id": "evt_weak_1",
        "last_seen_event_id": "evt_weak_1",
        "first_seen_timestamp": "2026-09-23T10:07:00Z",
        "last_seen_timestamp": "2026-09-23T10:07:00Z",
        "occurrence_count": 1,
        "sample_message": "Transient network jitter",
    }
    (sdir / "anomalies.json").write_text(json.dumps(anomalies), encoding="utf-8")

    # Add a marker
    (sdir / "markers.jsonl").write_text(
        '{"event_id": "evt_m_1", "sequence_number": 3, "timestamp": "2026-09-23T10:10:00Z", "payload": {"note": "Boss health bar didn\'t update"}}\n',
        encoding="utf-8",
    )

    out_file = tmp_path / "DEVELOPMENT_OBSERVATION_REPORT.md"
    res_path = generate_development_observation_report(sdir, out_file)

    assert res_path.exists()
    content = res_path.read_text(encoding="utf-8")

    # Verify 6-section taxonomy
    assert "## 1. Observed Facts" in content
    assert "## 2. Likely Defects" in content
    assert "## 3. Usability Findings" in content
    assert "## 4. Data Gaps" in content
    assert "## 5. Feature Opportunities" in content
    assert "## 6. Not Enough Evidence / Missing Evidence" in content

    # Check evidence citations and weak anomaly handling
    assert "evt_anom_1" in content
    assert "Transient network jitter" in content
    # Weak anomaly must be under section 6
    sec6 = content.split("## 6. Not Enough Evidence / Missing Evidence")[1]
    assert "Transient network jitter" in sec6
