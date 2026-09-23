"""Storage manager for observation streams and directory lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
from typing import Protocol, TextIO, runtime_checkable

from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.models import ManifestStatus, ObservationEnvelope


@runtime_checkable
class ObservationStorage(Protocol):
    """Storage contract for observation streams."""

    def append_envelope(self, stream_name: str, envelope: ObservationEnvelope) -> None:
        """Append an observation envelope to the specified stream."""
        ...

    def close_streams(self) -> None:
        """Flush and close all stream writers."""
        ...

    def get_artifact_counts(self) -> dict[str, int]:
        """Return counts of persisted records per stream."""
        ...


class ObservationStorageManager:
    """Manages session directories, stream rotation, and crash recovery."""

    DEFAULT_MAX_STREAM_BYTES = 10 * 1024 * 1024  # 10 MB
    DEFAULT_MAX_SEGMENTS = 5

    KNOWN_STREAMS = (
        "events",
        "state_deltas",
        "objective_traces",
        "notification_traces",
        "telemetry",
        "markers",
    )

    def __init__(
        self,
        base_dir: Path,
        session_id: str,
        max_stream_bytes: int = DEFAULT_MAX_STREAM_BYTES,
        max_segments: int = DEFAULT_MAX_SEGMENTS,
    ) -> None:
        self.base_dir = base_dir
        self.session_id = session_id
        self.session_dir = self.base_dir / self.session_id
        self.max_stream_bytes = max_stream_bytes
        self.max_segments = max_segments

        self._writers: dict[str, TextIO] = {}
        self._current_segment: dict[str, int] = {}
        self._current_size: dict[str, int] = {}

        self._init_layout()

    def _init_layout(self) -> None:
        """Create session directories and ensure gitignore protection."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        (self.session_dir / "screenshots").mkdir(parents=True, exist_ok=True)

        # Defense-in-depth: gitignore the observations directory
        gitignore = self.base_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")

    def _get_stream_path(self, stream_name: str, segment: int) -> Path:
        """Determine path for a given stream and segment index."""
        if segment == 0:
            return self.session_dir / f"{stream_name}.jsonl"
        return self.session_dir / f"{stream_name}.{segment}.jsonl"

    def _open_stream_writer(self, stream_name: str) -> TextIO:
        """Open or rotate writer for the named stream."""
        seg = self._current_segment.get(stream_name, 0)
        path = self._get_stream_path(stream_name, seg)
        cur_size = path.stat().st_size if path.exists() else 0

        if cur_size >= self.max_stream_bytes and seg < self.max_segments:
            seg += 1
            self._current_segment[stream_name] = seg
            path = self._get_stream_path(stream_name, seg)
            cur_size = path.stat().st_size if path.exists() else 0

        writer = open(path, "a", encoding="utf-8")
        self._writers[stream_name] = writer
        self._current_size[stream_name] = cur_size
        return writer

    def append_envelope(self, stream_name: str, envelope: ObservationEnvelope) -> None:
        """Append an observation envelope to the specified stream, rotating if needed."""
        line = envelope.model_dump_json() + "\n"
        encoded_bytes = len(line.encode("utf-8"))

        writer = self._writers.get(stream_name)
        cur_size = self._current_size.get(stream_name, 0)
        cur_seg = self._current_segment.get(stream_name, 0)

        if writer is None or (cur_size + encoded_bytes > self.max_stream_bytes and cur_seg < self.max_segments):
            if writer is not None:
                writer.flush()
                writer.close()
                cur_seg += 1
                self._current_segment[stream_name] = cur_seg

            path = self._get_stream_path(stream_name, cur_seg)
            cur_size = path.stat().st_size if path.exists() else 0
            writer = open(path, "a", encoding="utf-8")
            self._writers[stream_name] = writer
            self._current_size[stream_name] = cur_size

        writer.write(line)
        writer.flush()
        self._current_size[stream_name] += encoded_bytes

    def close_streams(self) -> None:
        """Flush and close all stream writers."""
        for writer in self._writers.values():
            try:
                writer.flush()
                writer.close()
            except Exception:
                pass
        self._writers.clear()

    def get_artifact_counts(self) -> dict[str, int]:
        """Return counts of persisted records per stream across all segment files."""
        counts = {stream: 0 for stream in self.KNOWN_STREAMS}
        if not self.session_dir.exists():
            return counts

        for stream in self.KNOWN_STREAMS:
            total = 0
            base_file = self.session_dir / f"{stream}.jsonl"
            if base_file.exists():
                try:
                    total += sum(1 for line in base_file.read_text(encoding="utf-8").splitlines() if line.strip())
                except Exception:
                    pass
            for seg_file in self.session_dir.glob(f"{stream}.*.jsonl"):
                try:
                    total += sum(1 for line in seg_file.read_text(encoding="utf-8").splitlines() if line.strip())
                except Exception:
                    pass
            counts[stream] = total
        return counts

    @classmethod
    def recover_unfinalized_sessions(cls, base_dir: Path) -> list[str]:
        """Scan session directories and transition unfinalized OPEN manifests."""
        if not base_dir.exists():
            return []

        recovered: list[str] = []
        for entry in base_dir.iterdir():
            if not entry.is_dir():
                continue
            manifest_path = entry / "session_manifest.json"
            if not manifest_path.exists():
                continue

            mgr = ManifestManager(manifest_path)
            manifest = mgr.load()
            if manifest and manifest.status == ManifestStatus.OPEN:
                now_iso = datetime.now(timezone.utc).isoformat()
                updated = SessionManifest(
                    schema_version=manifest.schema_version,
                    session_id=manifest.session_id,
                    runtime_run_id=manifest.runtime_run_id,
                    started_at=manifest.started_at,
                    ended_at=now_iso,
                    status=ManifestStatus.INCOMPLETE,
                    aborted_reason="UNEXPECTED_TERMINATION",
                    sequence_high_watermark=manifest.sequence_high_watermark,
                    persisted_event_count=manifest.persisted_event_count,
                    dropped_event_count=manifest.dropped_event_count,
                    dropped_high_priority_count=manifest.dropped_high_priority_count,
                    pending_event_count=manifest.pending_event_count,
                    dropped_sequence_ranges=manifest.dropped_sequence_ranges,
                    health_state=manifest.health_state,
                    worker_error_count=manifest.worker_error_count,
                    artifact_counts=manifest.artifact_counts,
                )
                mgr.save_atomic(updated)
                recovered.append(manifest.session_id)

        return recovered
