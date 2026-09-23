"""Hermes review batch results, finding lifecycle models, and journal persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FindingStatus(str, Enum):
    """Lifecycle stages reflecting evidence strength and corroboration."""

    WATCHING = "WATCHING"
    POSSIBLE_PATTERN = "POSSIBLE_PATTERN"
    CORROBORATED = "CORROBORATED"
    LIKELY_DEFECT = "LIKELY_DEFECT"
    USABILITY_SIGNAL = "USABILITY_SIGNAL"
    DATA_GAP = "DATA_GAP"
    NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"


def compute_finding_id(session_id: str, category: str, semantic_issue_key: str) -> str:
    """Derive stable logical finding identifier from session, category, and canonical semantic key."""
    return f"find:{session_id}:{category}:{semantic_issue_key}"


def compute_review_batch_id(
    session_id: str, sequence_start: int, sequence_end: int, evidence_ids: list[str]
) -> str:
    """Compute strictly deterministic review batch ID from structured batch boundaries."""
    ordered_ids = ",".join(sorted(evidence_ids))
    content = f"{session_id}:{sequence_start}:{sequence_end}:{ordered_ids}"
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"rb_{h}"


class FindingOperation(BaseModel):
    """Atomic finding operation contained in a durable review batch result."""

    model_config = ConfigDict(frozen=True)

    op: str  # CREATE, UPDATE, NO_FINDING
    finding_id: str
    category: str
    semantic_issue_key: str
    status: FindingStatus
    title: str
    summary: str
    occurrence_count_delta: int = 1
    new_evidence_ids: list[str] = Field(default_factory=list)
    corroboration_note: str | None = None


class ReviewBatchResult(BaseModel):
    """Durable structured outcome of a single contiguous Hermes review cycle."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    review_batch_id: str
    session_id: str
    sequence_start: int
    sequence_end: int
    reviewed_evidence_ids: list[str] = Field(default_factory=list)
    operations: list[FindingOperation] = Field(default_factory=list)
    review_status: str = "COMPLETED"  # COMPLETED, FAILED
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HermesFinding(BaseModel):
    """Durable finding model tracked across review batches in hermes_findings.jsonl."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    finding_id: str
    session_id: str
    category: str
    semantic_issue_key: str
    status: FindingStatus
    title: str
    summary: str
    occurrence_count: int = 1
    first_observed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_observed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence_refs: list[str] = Field(default_factory=list)
    corroboration_notes: list[str] = Field(default_factory=list)
    applied_review_batch_ids: list[str] = Field(default_factory=list)
    revision: int = 1


class ReviewJournalManager:
    """Manages atomic batch results and hermes_findings.jsonl lifecycle."""

    def __init__(self, session_dir: Path, session_id: str) -> None:
        self.session_dir = session_dir
        self.session_id = session_id
        self.live_analysis_dir = self.session_dir / "live_analysis"
        self.batches_dir = self.live_analysis_dir / "review_batches"
        self.findings_path = self.live_analysis_dir / "hermes_findings.jsonl"

        self.batches_dir.mkdir(parents=True, exist_ok=True)

    def save_batch_result(self, result: ReviewBatchResult) -> None:
        """Atomically persist a review batch result to review_batches/<batch_id>.json."""
        target_path = self.batches_dir / f"{result.review_batch_id}.json"
        tmp_path = target_path.with_name(f"{target_path.name}.tmp")
        raw_json = result.model_dump_json(indent=2)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(raw_json)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target_path)

    def load_batch_result(self, batch_id: str) -> ReviewBatchResult | None:
        """Load an existing review batch result by batch ID."""
        target_path = self.batches_dir / f"{batch_id}.json"
        if not target_path.exists():
            return None
        try:
            raw = target_path.read_text(encoding="utf-8")
            return ReviewBatchResult.model_validate_json(raw)
        except Exception:
            return None

    def get_findings(self) -> list[HermesFinding]:
        """Read all current findings from hermes_findings.jsonl."""
        if not self.findings_path.exists():
            return []
        findings: list[HermesFinding] = []
        try:
            with open(self.findings_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    findings.append(HermesFinding.model_validate_json(line))
        except Exception:
            pass
        return findings

    def _save_findings_atomic(self, findings: list[HermesFinding]) -> None:
        """Atomically overwrite hermes_findings.jsonl with updated findings."""
        tmp_path = self.findings_path.with_name(f"{self.findings_path.name}.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            for f_item in findings:
                f.write(f_item.model_dump_json() + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.findings_path)

    def apply_batch_result(self, result: ReviewBatchResult) -> list[HermesFinding]:
        """Idempotently apply operations from a ReviewBatchResult to findings."""
        existing_findings = {f.finding_id: f for f in self.get_findings()}
        batch_id = result.review_batch_id

        for op in result.operations:
            if op.op == "NO_FINDING":
                continue

            current = existing_findings.get(op.finding_id)
            if current is not None:
                # Idempotency check: if this batch was already applied, do nothing
                if batch_id in current.applied_review_batch_ids:
                    continue

                # Add only new evidence refs
                new_refs = [r for r in op.new_evidence_ids if r not in current.evidence_refs]
                updated_notes = list(current.corroboration_notes)
                if op.corroboration_note and op.corroboration_note not in updated_notes:
                    updated_notes.append(op.corroboration_note)

                updated = HermesFinding(
                    finding_id=current.finding_id,
                    session_id=current.session_id,
                    category=current.category,
                    semantic_issue_key=current.semantic_issue_key,
                    status=op.status,
                    title=op.title or current.title,
                    summary=op.summary or current.summary,
                    occurrence_count=current.occurrence_count + op.occurrence_count_delta,
                    first_observed_at=current.first_observed_at,
                    last_observed_at=result.timestamp,
                    evidence_refs=current.evidence_refs + new_refs,
                    corroboration_notes=updated_notes,
                    applied_review_batch_ids=current.applied_review_batch_ids + [batch_id],
                    revision=current.revision + 1,
                )
                existing_findings[op.finding_id] = updated
            else:
                # Create brand new finding
                notes = [op.corroboration_note] if op.corroboration_note else []
                created = HermesFinding(
                    finding_id=op.finding_id,
                    session_id=result.session_id,
                    category=op.category,
                    semantic_issue_key=op.semantic_issue_key,
                    status=op.status,
                    title=op.title,
                    summary=op.summary,
                    occurrence_count=op.occurrence_count_delta,
                    first_observed_at=result.timestamp,
                    last_observed_at=result.timestamp,
                    evidence_refs=list(op.new_evidence_ids),
                    corroboration_notes=notes,
                    applied_review_batch_ids=[batch_id],
                    revision=1,
                )
                existing_findings[op.finding_id] = created

        findings_list = list(existing_findings.values())
        self._save_findings_atomic(findings_list)
        return findings_list
