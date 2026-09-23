"""Session manifest models and atomic manifest persistence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from companion.observe.models import HealthState, ManifestStatus


class SessionManifest(BaseModel):
    """Metadata and reconciliation counters for an observation session."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    session_id: str
    runtime_run_id: str
    started_at: str
    ended_at: str | None = None
    status: ManifestStatus = ManifestStatus.OPEN
    aborted_reason: str | None = None
    sequence_high_watermark: int = 0
    persisted_event_count: int = 0
    dropped_event_count: int = 0
    dropped_high_priority_count: int = 0
    pending_event_count: int = 0
    dropped_sequence_ranges: list[list[int]] = Field(default_factory=list)
    health_state: HealthState = HealthState.HEALTHY
    worker_error_count: int = 0
    artifact_counts: dict[str, int] = Field(default_factory=dict)

    @property
    def stream_counts(self) -> dict[str, int]:
        """Alias for artifact_counts representing line counts of stream files."""
        return self.artifact_counts

    def is_reconciled(self) -> bool:
        """Check sequence accounting invariant."""
        if self.status == ManifestStatus.CLOSED:
            return (
                self.persisted_event_count + self.dropped_event_count
                == self.sequence_high_watermark
                and self.pending_event_count == 0
            )
        return (
            self.persisted_event_count
            + self.dropped_event_count
            + self.pending_event_count
            == self.sequence_high_watermark
        )


class ManifestManager:
    """Atomic filesystem reader and writer for session_manifest.json."""

    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path

    def save_atomic(self, manifest: SessionManifest) -> None:
        """Write manifest atomically via temporary file and rename."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.manifest_path.with_name(f"{self.manifest_path.name}.tmp")
        raw_json = manifest.model_dump_json(indent=2)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(raw_json)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.manifest_path)

    def load(self) -> SessionManifest | None:
        """Load manifest from disk if it exists."""
        if not self.manifest_path.exists():
            return None
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            content = f.read()
        return SessionManifest.model_validate_json(content)
