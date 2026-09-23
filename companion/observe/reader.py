"""Incremental multi-stream reader and crash-safe cursor tracking."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.models import ObservationEnvelope


def ranges_from_set(seqs: set[int]) -> list[list[int]]:
    """Convert an arbitrary set of sequence numbers into compact inclusive ranges."""
    if not seqs:
        return []
    sorted_seqs = sorted(seqs)
    ranges: list[list[int]] = []
    start = sorted_seqs[0]
    end = start

    for seq in sorted_seqs[1:]:
        if seq == end + 1:
            end = seq
        else:
            ranges.append([start, end])
            start = seq
            end = seq
    ranges.append([start, end])
    return ranges


def set_from_ranges(ranges: list[list[int]]) -> set[int]:
    """Expand compact inclusive ranges [[start, end], ...] into a set of sequence numbers."""
    result: set[int] = set()
    for r in ranges:
        if len(r) == 2:
            result.update(range(r[0], r[1] + 1))
        elif len(r) == 1:
            result.add(r[0])
    return result


class StreamReadPosition(BaseModel):
    """Tracks physical read location for a single typed observation stream."""

    model_config = ConfigDict(frozen=True)

    stream_name: str
    current_segment: str
    byte_offset: int = 0
    last_processed_sequence: int = 0
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ReaderState(BaseModel):
    """Durable state of the incremental stream reader stored in reader_state.json."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    session_id: str
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    contiguous_frontier: int = 0
    read_ahead_saturated: bool = False
    accounted_ahead_ranges: list[list[int]] = Field(default_factory=list)
    streams: dict[str, StreamReadPosition] = Field(default_factory=dict)
    gap_detected: bool = False
    gap_reason: str | None = None
    pending_marker_ids: list[str] = Field(default_factory=list)


class IncrementalStreamReader:
    """Incrementally reads structured observation evidence across rotated streams."""

    DEFAULT_KNOWN_STREAMS = (
        "events",
        "state_deltas",
        "objective_traces",
        "notification_traces",
        "telemetry",
        "markers",
    )

    def __init__(
        self,
        session_dir: Path,
        session_id: str,
        state_path: Path | None = None,
        max_seen_ahead: int = 1000,
        known_streams: tuple[str, ...] = DEFAULT_KNOWN_STREAMS,
    ) -> None:
        self.session_dir = session_dir
        self.session_id = session_id
        self.state_path = state_path or (self.session_dir / "live_analysis" / "reader_state.json")
        self.manifest_path = self.session_dir / "session_manifest.json"
        self.max_seen_ahead = max_seen_ahead
        self.known_streams = known_streams

        self.contiguous_frontier: int = 0
        self.seen_ahead: set[int] = set()
        self.read_ahead_saturated: bool = False
        self.gap_detected: bool = False
        self.gap_reason: str | None = None
        self.pending_marker_ids: list[str] = []
        self._stream_positions: dict[str, StreamReadPosition] = {}

        self.load_state()

    @property
    def state(self) -> ReaderState:
        """Construct the current ReaderState model."""
        return ReaderState(
            session_id=self.session_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
            contiguous_frontier=self.contiguous_frontier,
            read_ahead_saturated=self.read_ahead_saturated,
            accounted_ahead_ranges=ranges_from_set(self.seen_ahead),
            streams=dict(self._stream_positions),
            gap_detected=self.gap_detected,
            gap_reason=self.gap_reason,
            pending_marker_ids=list(self.pending_marker_ids),
        )

    def load_state(self) -> ReaderState | None:
        """Load durable state from disk if it exists."""
        if not self.state_path.exists():
            return None
        try:
            raw = self.state_path.read_text(encoding="utf-8")
            state = ReaderState.model_validate_json(raw)
            self.contiguous_frontier = state.contiguous_frontier
            self.read_ahead_saturated = state.read_ahead_saturated
            self.seen_ahead = set_from_ranges(state.accounted_ahead_ranges)
            self.gap_detected = state.gap_detected
            self.gap_reason = state.gap_reason
            self.pending_marker_ids = list(state.pending_marker_ids)
            self._stream_positions = dict(state.streams)
            return state
        except Exception:
            return None

    def save_state(self) -> None:
        """Atomically persist current ReaderState to disk via .tmp rename."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_path.with_name(f"{self.state_path.name}.tmp")
        raw_json = self.state.model_dump_json(indent=2)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(raw_json)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.state_path)

    def _get_dropped_sequences(self) -> set[int]:
        """Load dropped sequence numbers from session manifest if available."""
        if not self.manifest_path.exists():
            return set()
        manifest = ManifestManager(self.manifest_path).load()
        if not manifest or not manifest.dropped_sequence_ranges:
            return set()
        return set_from_ranges(manifest.dropped_sequence_ranges)

    def _discover_stream_segments(self, stream_name: str) -> list[tuple[int, str]]:
        """List and sort existing segment files for a given stream name."""
        pattern = re.compile(rf"^{re.escape(stream_name)}(?:\.(\d+))?\.jsonl$")
        segments: list[tuple[int, str]] = []

        if not self.session_dir.exists():
            return segments

        for p in self.session_dir.iterdir():
            if not p.is_file():
                continue
            m = pattern.match(p.name)
            if m:
                seg_idx = int(m.group(1)) if m.group(1) is not None else 0
                segments.append((seg_idx, p.name))

        segments.sort(key=lambda x: x[0])
        return segments

    def _advance_frontier_if_possible(self, dropped_seqs: set[int]) -> None:
        """Advance contiguous_frontier as far as seen_ahead or dropped_seqs allow."""
        while True:
            next_seq = self.contiguous_frontier + 1
            if next_seq in self.seen_ahead:
                self.contiguous_frontier = next_seq
                self.seen_ahead.discard(next_seq)
            elif next_seq in dropped_seqs:
                self.contiguous_frontier = next_seq
            else:
                break

        if len(self.seen_ahead) < self.max_seen_ahead:
            self.read_ahead_saturated = False

    def read_new_envelopes(self) -> list[ObservationEnvelope]:
        """Read and parse new complete envelopes across all typed streams."""
        dropped_seqs = self._get_dropped_sequences()
        self._advance_frontier_if_possible(dropped_seqs)

        envelopes: list[ObservationEnvelope] = []

        while True:
            progress_made = False

            for stream_name in self.known_streams:
                segments = self._discover_stream_segments(stream_name)
                if not segments:
                    continue

                # Validate segment continuity
                has_gap = False
                seg_indices = [idx for idx, _ in segments]
                for i in range(len(seg_indices) - 1):
                    if seg_indices[i + 1] != seg_indices[i] + 1:
                        self.gap_detected = True
                        self.gap_reason = (
                            f"ANALYST_STREAM_GAP: missing segment between {seg_indices[i]} "
                            f"and {seg_indices[i + 1]} in stream {stream_name}"
                        )
                        has_gap = True
                        # Only allow segments up to the first gap
                        segments = segments[: i + 1]
                        break

                # Current position for this stream
                pos = self._stream_positions.get(stream_name)
                if pos is None:
                    cur_seg_idx = segments[0][0]
                    cur_seg_name = segments[0][1]
                    pos = StreamReadPosition(
                        stream_name=stream_name,
                        current_segment=cur_seg_name,
                        byte_offset=0,
                        last_processed_sequence=0,
                    )
                    self._stream_positions[stream_name] = pos

                # Traverse through available segments starting from current_segment
                seg_dict = {name: idx for idx, name in segments}
                cur_seg_idx = seg_dict.get(pos.current_segment, segments[0][0])

                for seg_idx, seg_filename in segments:
                    if seg_idx < cur_seg_idx:
                        continue

                    seg_path = self.session_dir / seg_filename
                    if not seg_path.exists():
                        continue

                    file_size = seg_path.stat().st_size
                    byte_offset = pos.byte_offset if seg_filename == pos.current_segment else 0

                    # Check if this segment is at EOF and a higher segment exists
                    higher_segs = [s for s, _ in segments if s > seg_idx]
                    if byte_offset >= file_size and higher_segs:
                        # Switch to next segment
                        next_seg_name = next(name for s, name in segments if s == higher_segs[0])
                        pos = StreamReadPosition(
                            stream_name=stream_name,
                            current_segment=next_seg_name,
                            byte_offset=0,
                            last_processed_sequence=pos.last_processed_sequence,
                        )
                        self._stream_positions[stream_name] = pos
                        progress_made = True
                        continue

                    if byte_offset >= file_size:
                        continue

                    # Read available complete lines
                    with open(seg_path, "rb") as f:
                        f.seek(byte_offset)
                        raw_data = f.read()

                    last_nl = raw_data.rfind(b"\n")
                    if last_nl == -1:
                        # No complete line yet
                        continue

                    data_to_parse = raw_data[: last_nl + 1]
                    lines = data_to_parse.split(b"\n")
                    stream_saturated = False
                    segment_bytes_processed = 0

                    for raw_line in lines:
                        line_len = len(raw_line) + 1  # include newline
                        if not raw_line.strip():
                            segment_bytes_processed += line_len
                            continue

                        try:
                            record_dict = json.loads(raw_line.decode("utf-8"))
                            envelope = ObservationEnvelope.model_validate(record_dict)
                        except Exception:
                            # Skip or break on unparseable lines; retain offset before line
                            break

                        seq = envelope.sequence_number

                        if seq <= self.contiguous_frontier or seq in self.seen_ahead:
                            # Duplicate or already seen: update stream offset, do not re-emit envelope
                            pos = StreamReadPosition(
                                stream_name=stream_name,
                                current_segment=seg_filename,
                                byte_offset=byte_offset + segment_bytes_processed + line_len,
                                last_processed_sequence=max(pos.last_processed_sequence, seq),
                            )
                            self._stream_positions[stream_name] = pos
                            segment_bytes_processed += line_len
                            progress_made = True
                            continue

                        if seq == self.contiguous_frontier + 1:
                            self.contiguous_frontier = seq
                            self._advance_frontier_if_possible(dropped_seqs)
                            envelopes.append(envelope)
                            pos = StreamReadPosition(
                                stream_name=stream_name,
                                current_segment=seg_filename,
                                byte_offset=byte_offset + segment_bytes_processed + line_len,
                                last_processed_sequence=max(pos.last_processed_sequence, seq),
                            )
                            self._stream_positions[stream_name] = pos
                            segment_bytes_processed += line_len
                            progress_made = True
                        elif seq > self.contiguous_frontier + 1:
                            if len(self.seen_ahead) >= self.max_seen_ahead:
                                # Saturated! Stop reading this stream further
                                self.read_ahead_saturated = True
                                stream_saturated = True
                                break
                            else:
                                self.seen_ahead.add(seq)
                                envelopes.append(envelope)
                                pos = StreamReadPosition(
                                    stream_name=stream_name,
                                    current_segment=seg_filename,
                                    byte_offset=byte_offset + segment_bytes_processed + line_len,
                                    last_processed_sequence=max(pos.last_processed_sequence, seq),
                                )
                                self._stream_positions[stream_name] = pos
                                segment_bytes_processed += line_len
                                progress_made = True

                    if stream_saturated:
                        break

            self._advance_frontier_if_possible(dropped_seqs)

            if not progress_made:
                break

        # Track markers for offline queuing
        for env in envelopes:
            if env.event_type == "USER_MARKER":
                marker_id = env.payload.get("marker_id")
                if marker_id and marker_id not in self.pending_marker_ids:
                    self.pending_marker_ids.append(marker_id)

        return envelopes
