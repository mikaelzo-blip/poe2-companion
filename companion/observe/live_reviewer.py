"""Interactive Hermes live review engine and review liveness telemetry."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from pydantic import BaseModel, ConfigDict, Field

from companion.observe.analyst import LocalLiveAnalyst
from companion.observe.cursor import ReviewCursorManager
from companion.observe.journal import (
    FindingOperation,
    FindingStatus,
    ReviewBatchResult,
    ReviewJournalManager,
    compute_finding_id,
    compute_review_batch_id,
)
from companion.observe.models import ObservationEnvelope


class HermesReviewStatus(BaseModel):
    """Liveness and review execution telemetry persisted in hermes_review_status.json."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    review_run_id: str
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_heartbeat: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_reviewed_sequence: int = 0
    state: str = "ACTIVE"  # ACTIVE, IDLE, STOPPED, FAILED


class HermesReviewStatusManager:
    """Manages atomic reads and updates of hermes_review_status.json."""

    def __init__(self, status_path: Path) -> None:
        self.status_path = status_path

    def load(self) -> HermesReviewStatus | None:
        if not self.status_path.exists():
            return None
        try:
            raw = self.status_path.read_text(encoding="utf-8")
            return HermesReviewStatus.model_validate_json(raw)
        except Exception:
            return None

    def save_atomic(self, status: HermesReviewStatus) -> None:
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.status_path.with_name(f"{self.status_path.name}.tmp")
        raw_json = status.model_dump_json(indent=2)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(raw_json)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.status_path)

    def update_heartbeat(
        self,
        run_id: str,
        last_seq: int,
        state: str = "ACTIVE",
    ) -> HermesReviewStatus:
        existing = self.load()
        started_at = existing.started_at if existing else datetime.now(timezone.utc).isoformat()
        status = HermesReviewStatus(
            review_run_id=run_id,
            started_at=started_at,
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
            last_reviewed_sequence=last_seq,
            state=state,
        )
        self.save_atomic(status)
        return status


class LiveReviewEngine:
    """Coordinates local analysis, deterministic review batch formation, and finding evolution."""

    def __init__(
        self,
        session_dir: Path,
        session_id: str,
        batch_size: int = 100,
        run_id: str | None = None,
    ) -> None:
        self.session_dir = session_dir
        self.session_id = session_id
        self.batch_size = batch_size
        self.run_id = run_id or f"rev_{uuid.uuid4().hex[:12]}"

        self.live_analysis_dir = self.session_dir / "live_analysis"
        self.live_analysis_dir.mkdir(parents=True, exist_ok=True)

        self.analyst = LocalLiveAnalyst(session_dir=self.session_dir, session_id=self.session_id)
        self.cursor_mgr = ReviewCursorManager(
            cursor_path=self.live_analysis_dir / "hermes_review_cursor.json",
            session_id=self.session_id,
        )
        self.journal = ReviewJournalManager(session_dir=self.session_dir, session_id=self.session_id)
        self.status_mgr = HermesReviewStatusManager(
            status_path=self.live_analysis_dir / "hermes_review_status.json"
        )

    def _collect_envelopes_in_range(self, start_seq: int, end_seq: int) -> list[ObservationEnvelope]:
        """Scan session stream files for complete envelopes within the sequence range."""
        matched: list[ObservationEnvelope] = []
        for file in self.session_dir.glob("*.jsonl"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        env_dict = json.loads(line)
                        seq = env_dict.get("sequence_number")
                        if seq and start_seq <= seq <= end_seq:
                            matched.append(ObservationEnvelope.model_validate(env_dict))
            except Exception:
                continue

        matched.sort(key=lambda e: e.sequence_number)
        return matched

    def step_review(self) -> ReviewBatchResult | None:
        """Execute one bounded review cycle."""
        # 1. Step local analyst data plane
        self.analyst.step()

        # 2. Check contiguous frontiers
        reader_frontier = self.analyst.reader.contiguous_frontier
        review_frontier = self.cursor_mgr.review_contiguous_frontier

        if reader_frontier <= review_frontier:
            return None

        # 3. Determine pending contiguous sequence range
        start_seq = review_frontier + 1
        end_seq = min(reader_frontier, start_seq + self.batch_size - 1)

        # 4. Collect structured envelopes
        batch_envs = self._collect_envelopes_in_range(start_seq, end_seq)
        evidence_ids = [e.event_id for e in batch_envs]

        # 5. Deterministic review_batch_id
        batch_id = compute_review_batch_id(self.session_id, start_seq, end_seq, evidence_ids)

        # 6. Check existing completed batch result (Case B recovery)
        existing = self.journal.load_batch_result(batch_id)
        if existing and existing.review_status == "COMPLETED":
            batch_result = existing
        else:
            operations: list[FindingOperation] = []

            # Prioritize user markers and high-severity signals
            for env in batch_envs:
                if env.event_type == "USER_MARKER":
                    marker_id = env.payload.get("marker_id", "unknown")
                    note = env.payload.get("note", "")
                    finding_id = compute_finding_id(self.session_id, "marker", marker_id)
                    operations.append(
                        FindingOperation(
                            op="CREATE",
                            finding_id=finding_id,
                            category="marker",
                            semantic_issue_key=marker_id,
                            status=FindingStatus.CORROBORATED,
                            title=f"User Marker: {note}",
                            summary=f"Observed at sequence {env.sequence_number}",
                            occurrence_count_delta=1,
                            new_evidence_ids=[env.event_id],
                            corroboration_note=f"Corroborated by user marker {marker_id}",
                        )
                    )

            if not operations:
                operations.append(
                    FindingOperation(
                        op="NO_FINDING",
                        finding_id=compute_finding_id(self.session_id, "routine", "clean"),
                        category="routine",
                        semantic_issue_key="clean",
                        status=FindingStatus.NOT_ENOUGH_EVIDENCE,
                        title="Routine sequence review",
                        summary="No candidate finding identified in this range",
                    )
                )

            batch_result = ReviewBatchResult(
                review_batch_id=batch_id,
                session_id=self.session_id,
                sequence_start=start_seq,
                sequence_end=end_seq,
                reviewed_evidence_ids=evidence_ids,
                operations=operations,
                review_status="COMPLETED",
            )
            # Persist durable batch result BEFORE advancing cursor
            self.journal.save_batch_result(batch_result)

        # 7. Apply operations idempotently
        self.journal.apply_batch_result(batch_result)

        # 8. Advance review cursor
        self.cursor_mgr.record_batch_reviewed(batch_result.review_batch_id, start_seq, end_seq)
        self.cursor_mgr.save_atomic()

        # 9. Update review heartbeat
        self.status_mgr.update_heartbeat(self.run_id, end_seq, state="ACTIVE")

        return batch_result
