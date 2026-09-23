"""Tests for atomic marker inbox writer and consumer."""

from pathlib import Path
import threading
import pytest

from companion.observe.markers import (
    MarkerInboxManager,
    is_session_active,
    write_marker,
)


def test_atomic_marker_write_and_consume(tmp_path: Path):
    inbox_dir = tmp_path / "runtime" / "observations" / "marker_inbox"

    # Write marker
    marker_path, marker_id = write_marker(
        note="Test marker note",
        inbox_dir=inbox_dir,
    )
    assert marker_path.exists()
    assert marker_path.name.endswith(".json")

    # Incomplete .tmp file should be ignored
    fake_tmp = inbox_dir / "incomplete_marker.tmp"
    fake_tmp.write_text("incomplete", encoding="utf-8")

    mgr = MarkerInboxManager(inbox_dir)
    markers = mgr.consume_markers()

    assert len(markers) == 1
    assert markers[0].marker_id == marker_id
    assert markers[0].note == "Test marker note"

    # Confirmed consumed file is deleted
    assert not marker_path.exists()
    # Incomplete .tmp still exists (untouched)
    assert fake_tmp.exists()


def test_concurrent_marker_writes_no_collision(tmp_path: Path):
    inbox_dir = tmp_path / "runtime" / "observations" / "marker_inbox"
    mgr = MarkerInboxManager(inbox_dir)

    def _worker(idx: int):
        write_marker(f"Concurrent note {idx}", inbox_dir=inbox_dir)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    consumed = mgr.consume_markers()
    assert len(consumed) == 20
    notes = {m.note for m in consumed}
    assert len(notes) == 20


def test_is_session_active_reports_honestly(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True)
    # No status file -> False
    assert is_session_active(runtime_dir) is False

    # Status file with IDLE -> False
    status_file = runtime_dir / "runtime_status.json"
    status_file.write_text('{"lifecycle_state": "IDLE"}', encoding="utf-8")
    assert is_session_active(runtime_dir) is False

    # Status file with SESSION_ACTIVE -> True
    status_file.write_text('{"lifecycle_state": "SESSION_ACTIVE"}', encoding="utf-8")
    assert is_session_active(runtime_dir) is True
