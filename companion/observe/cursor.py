"""Decoupled dual-cursor managers and contiguous lag calculation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from companion.observe.reader import (
    ReaderState,
    ranges_from_set,
    set_from_ranges,
)


def compute_reader_lag(observer_sequence: int, reader_contiguous_frontier: int) -> int:
    """Calculate contiguous reader lag: observer_latest_sequence - reader_contiguous_frontier."""
    return max(0, int(observer_sequence) - int(reader_contiguous_frontier))


def compute_review_lag(reader_contiguous_frontier: int, review_contiguous_frontier: int) -> int:
    """Calculate contiguous review lag: reader_contiguous_frontier - review_contiguous_frontier."""
    return max(0, int(reader_contiguous_frontier) - int(review_contiguous_frontier))


class ReviewCursor(BaseModel):
    """Durable review state persisted in hermes_review_cursor.json."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    session_id: str
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    review_contiguous_frontier: int = 0
    accounted_reviewed_ranges: list[list[int]] = Field(default_factory=list)
    completed_review_batches: list[str] = Field(default_factory=list)
    pending_review_batches: list[str] = Field(default_factory=list)

    @property
    def reviewed_ahead_ranges(self) -> list[list[int]]:
        """Alias for accounted_reviewed_ranges matching design specification."""
        return self.accounted_reviewed_ranges


class ReaderCursorManager:
    """Manages durable reader_state.json access and updates."""

    def __init__(self, state_path: Path, session_id: str) -> None:
        self.state_path = state_path
        self.session_id = session_id
        self._state: ReaderState | None = None
        self.load()

    @property
    def contiguous_frontier(self) -> int:
        return self._state.contiguous_frontier if self._state else 0

    @property
    def accounted_ahead_ranges(self) -> list[list[int]]:
        return self._state.accounted_ahead_ranges if self._state else []

    @property
    def read_ahead_saturated(self) -> bool:
        return self._state.read_ahead_saturated if self._state else False

    def load(self) -> ReaderState | None:
        if not self.state_path.exists():
            self._state = ReaderState(session_id=self.session_id)
            return self._state
        try:
            raw = self.state_path.read_text(encoding="utf-8")
            self._state = ReaderState.model_validate_json(raw)
            return self._state
        except Exception:
            self._state = ReaderState(session_id=self.session_id)
            return self._state

    def update_frontier(
        self,
        frontier: int,
        accounted_ahead_ranges: list[list[int]] | None = None,
        read_ahead_saturated: bool = False,
    ) -> None:
        ranges = accounted_ahead_ranges if accounted_ahead_ranges is not None else self.accounted_ahead_ranges
        streams = dict(self._state.streams) if self._state else {}
        self._state = ReaderState(
            session_id=self.session_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
            contiguous_frontier=frontier,
            read_ahead_saturated=read_ahead_saturated,
            accounted_ahead_ranges=ranges,
            streams=streams,
        )

    def save_atomic(self) -> None:
        if not self._state:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_path.with_name(f"{self.state_path.name}.tmp")
        raw_json = self._state.model_dump_json(indent=2)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(raw_json)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.state_path)


class ReviewCursorManager:
    """Manages durable hermes_review_cursor.json access and contiguous frontier progression."""

    def __init__(self, cursor_path: Path, session_id: str) -> None:
        self.cursor_path = cursor_path
        self.session_id = session_id
        self._cursor: ReviewCursor = ReviewCursor(session_id=self.session_id)
        self.load()

    @property
    def review_contiguous_frontier(self) -> int:
        return self._cursor.review_contiguous_frontier

    @property
    def accounted_reviewed_ranges(self) -> list[list[int]]:
        return self._cursor.accounted_reviewed_ranges

    @property
    def reviewed_ahead_ranges(self) -> list[list[int]]:
        return self._cursor.reviewed_ahead_ranges

    @property
    def completed_review_batches(self) -> list[str]:
        return self._cursor.completed_review_batches

    @property
    def pending_review_batches(self) -> list[str]:
        return self._cursor.pending_review_batches

    def load(self) -> ReviewCursor:
        if not self.cursor_path.exists():
            self._cursor = ReviewCursor(session_id=self.session_id)
            return self._cursor
        try:
            raw = self.cursor_path.read_text(encoding="utf-8")
            self._cursor = ReviewCursor.model_validate_json(raw)
            return self._cursor
        except Exception:
            self._cursor = ReviewCursor(session_id=self.session_id)
            return self._cursor

    def record_batch_reviewed(
        self,
        batch_id: str,
        sequence_start: int,
        sequence_end: int,
    ) -> None:
        """Record that a review batch has completed review and advance contiguous frontier if possible."""
        completed = list(self._cursor.completed_review_batches)
        if batch_id not in completed:
            completed.append(batch_id)

        pending = [b for b in self._cursor.pending_review_batches if b != batch_id]

        reviewed_set = set_from_ranges(self._cursor.accounted_reviewed_ranges)
        reviewed_set.update(range(sequence_start, sequence_end + 1))

        frontier = self._cursor.review_contiguous_frontier

        # Advance contiguous frontier
        while frontier + 1 in reviewed_set:
            frontier += 1
            reviewed_set.discard(frontier)

        compact_ranges = ranges_from_set(reviewed_set)

        self._cursor = ReviewCursor(
            session_id=self.session_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
            review_contiguous_frontier=frontier,
            accounted_reviewed_ranges=compact_ranges,
            completed_review_batches=completed,
            pending_review_batches=pending,
        )

    def save_atomic(self) -> None:
        self.cursor_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.cursor_path.with_name(f"{self.cursor_path.name}.tmp")
        raw_json = self._cursor.model_dump_json(indent=2)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(raw_json)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.cursor_path)
