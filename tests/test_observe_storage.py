"""Tests for observation storage manager and stream rotation."""

from pathlib import Path
import pytest

from companion.observe.models import ObservationEnvelope, FactKind
from companion.observe.storage import ObservationStorage, ObservationStorageManager


def test_observation_storage_protocol_compliance():
    """Verify ObservationStorageManager satisfies the ObservationStorage protocol."""
    assert issubclass(ObservationStorageManager, ObservationStorage)


def test_storage_manager_initializes_directory_and_gitignore(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    mgr = ObservationStorageManager(base_dir=base_dir, session_id="obs_test_01")
    session_dir = mgr.session_dir

    assert session_dir.exists()
    assert (session_dir / "screenshots").exists()

    gitignore_path = base_dir / ".gitignore"
    assert gitignore_path.exists()
    content = gitignore_path.read_text(encoding="utf-8")
    assert "*" in content


def test_storage_manager_stream_rotation(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    # Set rotation threshold low (500 bytes) for testing
    mgr = ObservationStorageManager(
        base_dir=base_dir,
        session_id="obs_test_rot",
        max_stream_bytes=500,
        max_segments=3,
    )

    # Write multiple envelopes to trigger rotation
    for seq in range(1, 20):
        env = ObservationEnvelope(
            schema_version="1.0",
            observation_session_id="obs_test_rot",
            event_id=f"evt_{seq}",
            sequence_number=seq,
            taxonomy=FactKind.OBSERVED_FACT,
            recorded_at="2026-09-23T14:00:00Z",
            event_type="TEST_EVENT",
            payload={"data": "x" * 100},
        )
        mgr.append_envelope("events", env)

    mgr.close_streams()

    # Verify segments were created
    files = list(mgr.session_dir.glob("events*.jsonl"))
    assert len(files) > 1
    assert any(f.name == "events.1.jsonl" or f.name == "events.jsonl" for f in files)

    # Verify get_artifact_counts accurately sums across all segments
    counts = mgr.get_artifact_counts()
    assert counts["events"] == 19
    assert counts["state_deltas"] == 0
    assert counts["markers"] == 0
