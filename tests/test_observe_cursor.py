"""Tests for decoupled dual cursor managers in companion.observe.cursor."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from companion.observe.cursor import (
    ReaderCursorManager,
    ReviewCursor,
    ReviewCursorManager,
    compute_reader_lag,
    compute_review_lag,
)
from companion.observe.reader import ReaderState


def test_lag_computation_strictly_uses_contiguous_frontiers() -> None:
    # Example from design doc:
    # observer_latest_sequence = 8000
    # reader_contiguous_frontier = 7995
    # review_contiguous_frontier = 7600
    reader_lag = compute_reader_lag(observer_sequence=8000, reader_contiguous_frontier=7995)
    review_lag = compute_review_lag(reader_contiguous_frontier=7995, review_contiguous_frontier=7600)

    assert reader_lag == 5
    assert review_lag == 395

    # Clamping tests
    assert compute_reader_lag(observer_sequence=10, reader_contiguous_frontier=20) == 0
    assert compute_review_lag(reader_contiguous_frontier=10, review_contiguous_frontier=20) == 0


def test_reader_cursor_manager_atomic_save_load(tmp_path: Path) -> None:
    state_file = tmp_path / "reader_state.json"
    mgr = ReaderCursorManager(state_path=state_file, session_id="obs_test_1")

    # Initial state
    assert mgr.contiguous_frontier == 0
    assert mgr.read_ahead_saturated is False

    mgr.update_frontier(10, accounted_ahead_ranges=[[12, 15]], read_ahead_saturated=True)
    mgr.save_atomic()

    assert state_file.exists()
    raw = json.loads(state_file.read_text(encoding="utf-8"))
    assert raw["contiguous_frontier"] == 10
    assert raw["accounted_ahead_ranges"] == [[12, 15]]
    assert raw["read_ahead_saturated"] is True

    # Reload from disk
    mgr_loaded = ReaderCursorManager(state_path=state_file, session_id="obs_test_1")
    mgr_loaded.load()
    assert mgr_loaded.contiguous_frontier == 10
    assert mgr_loaded.accounted_ahead_ranges == [[12, 15]]
    assert mgr_loaded.read_ahead_saturated is True


def test_review_cursor_manager_contiguous_frontier_advancement(tmp_path: Path) -> None:
    cursor_file = tmp_path / "hermes_review_cursor.json"
    mgr = ReviewCursorManager(cursor_path=cursor_file, session_id="obs_test_2")

    # Initial state
    assert mgr.review_contiguous_frontier == 0

    # Advance 1..100
    mgr.record_batch_reviewed(
        batch_id="rb_1",
        sequence_start=1,
        sequence_end=100,
    )
    assert mgr.review_contiguous_frontier == 100
    assert mgr.accounted_reviewed_ranges == []

    # Batch 102..120 reviewed while 101 is pending!
    mgr.record_batch_reviewed(
        batch_id="rb_2",
        sequence_start=102,
        sequence_end=120,
    )
    # Frontier MUST remain 100 because 101 is missing/pending
    assert mgr.review_contiguous_frontier == 100
    assert mgr.accounted_reviewed_ranges == [[102, 120]]

    # Now batch for 101..101 arrives/completes
    mgr.record_batch_reviewed(
        batch_id="rb_3",
        sequence_start=101,
        sequence_end=101,
    )
    # Frontier advances through 120!
    assert mgr.review_contiguous_frontier == 120
    assert mgr.accounted_reviewed_ranges == []


def test_review_cursor_manager_crash_recovery(tmp_path: Path) -> None:
    cursor_file = tmp_path / "hermes_review_cursor.json"
    mgr = ReviewCursorManager(cursor_path=cursor_file, session_id="obs_test_crash")

    mgr.record_batch_reviewed("rb_1", 1, 50)
    mgr.record_batch_reviewed("rb_2", 55, 60)
    mgr.save_atomic()

    assert mgr.review_contiguous_frontier == 50
    assert mgr.accounted_reviewed_ranges == [[55, 60]]

    # Simulate restart
    restarted = ReviewCursorManager(cursor_path=cursor_file, session_id="obs_test_crash")
    assert restarted.review_contiguous_frontier == 50
    assert restarted.accounted_reviewed_ranges == [[55, 60]]
    assert "rb_1" in restarted.completed_review_batches
    assert "rb_2" in restarted.completed_review_batches

    # Now resolve 51..54
    restarted.record_batch_reviewed("rb_3", 51, 54)
    restarted.save_atomic()

    assert restarted.review_contiguous_frontier == 60
    assert restarted.accounted_reviewed_ranges == []
