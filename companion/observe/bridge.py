"""Filesystem Hermes AI Review Bridge, request coverage, claim management, and ingress validation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel

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
from companion.observe.live_reviewer import HermesReviewStatusManager
from companion.observe.models import (
    ExistingFindingContext,
    FindingOperationModel,
    ObservationEnvelope,
    RequestPriorityState,
    ReviewClaimEnvelope,
    ReviewClaimStatusEnvelope,
    ReviewRequestEnvelope,
    ReviewResponseEnvelope,
)

# Targeted privacy and security patterns
RE_POE_CHAT = re.compile(
    r"(@From|@To|From:\s|To:\s|Guild:\s|Party:\s|Trade:\s|^[@#\$%&])",
    re.IGNORECASE,
)
RE_CREDENTIALS = re.compile(
    r"(sk-[a-zA-Z0-9_\-]{16,}|ghp_[a-zA-Z0-9]{20,}|Bearer\s+[a-zA-Z0-9_\-\.]+|ey[a-zA-Z0-9_\-]{20,})",
    re.IGNORECASE,
)
RE_PATH_TRAVERSAL = re.compile(r"(\.\.[/\\]|[/\\]\.\.|^\.\.$|\s\.\.[/\\]|[/\\]\.\.\s)")


def write_atomic_json(path: Path, model_or_dict: BaseModel | dict[str, Any]) -> None:
    """Write model or dictionary to JSON file via .tmp file, fsync, and atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    if isinstance(model_or_dict, BaseModel):
        raw_json = model_or_dict.model_dump_json(indent=2)
    else:
        raw_json = json.dumps(model_or_dict, indent=2)

    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(raw_json)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


class RequestCoverageManager:
    """Enforces non-overlapping sequence coverage for canonical review requests."""

    def __init__(self) -> None:
        # List of (start_seq, end_seq, batch_id)
        self._ranges: list[tuple[int, int, str]] = []

    @property
    def ranges(self) -> list[tuple[int, int, str]]:
        return list(self._ranges)

    def can_cover_range(self, start_seq: int, end_seq: int) -> bool:
        """Check if [start_seq, end_seq] is completely non-overlapping with existing ranges."""
        for s, e, _ in self._ranges:
            if not (end_seq < s or start_seq > e):
                return False
        return True

    def register_range(self, start_seq: int, end_seq: int, batch_id: str) -> None:
        """Register a new non-overlapping range."""
        if not self.can_cover_range(start_seq, end_seq):
            raise ValueError(f"Range [{start_seq}, {end_seq}] overlaps with existing request coverage")
        self._ranges.append((start_seq, end_seq, batch_id))
        self._ranges.sort(key=lambda x: x[0])

    def get_owning_batch(self, seq: int) -> str | None:
        """Return the review_batch_id covering this sequence, if any."""
        for s, e, batch_id in self._ranges:
            if s <= seq <= e:
                return batch_id
        return None

    def reconstruct_from_session(self, session_dir: Path) -> None:
        """Reconstruct request coverage from existing requests, batches, and cursor ahead ranges."""
        self._ranges.clear()
        live_dir = session_dir / "live_analysis"

        # 1. Scan review_requests/
        req_dir = live_dir / "review_requests"
        if req_dir.exists():
            for req_file in req_dir.glob("*.json"):
                try:
                    raw = req_file.read_text(encoding="utf-8")
                    req = ReviewRequestEnvelope.model_validate_json(raw)
                    if self.can_cover_range(req.sequence_start, req.sequence_end):
                        self.register_range(req.sequence_start, req.sequence_end, req.review_batch_id)
                except Exception:
                    continue

        # 2. Scan review_batches/
        batch_dir = live_dir / "review_batches"
        if batch_dir.exists():
            for b_file in batch_dir.glob("*.json"):
                try:
                    raw = b_file.read_text(encoding="utf-8")
                    b_dict = json.loads(raw)
                    s = b_dict.get("sequence_start")
                    e = b_dict.get("sequence_end")
                    b_id = b_dict.get("review_batch_id")
                    if s and e and b_id and self.can_cover_range(s, e):
                        self.register_range(s, e, b_id)
                except Exception:
                    continue


class ReviewClaimManager:
    """Manages immutable claim-specific artifacts and self-owned lease renewal."""

    def __init__(self, session_dir: Path) -> None:
        self.session_dir = session_dir
        self.claims_dir = self.session_dir / "live_analysis" / "review_claims"
        self.status_dir = self.session_dir / "live_analysis" / "review_claim_status"
        self.claims_dir.mkdir(parents=True, exist_ok=True)
        self.status_dir.mkdir(parents=True, exist_ok=True)

    def claim_request(
        self,
        review_batch_id: str,
        claim_id: str,
        review_run_id: str,
        lease_seconds: float = 180.0,
    ) -> ReviewClaimEnvelope:
        """Publish immutable claim-specific artifact review_claims/<batch_id>.<claim_id>.json."""
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=lease_seconds)).isoformat()
        claim = ReviewClaimEnvelope(
            review_batch_id=review_batch_id,
            claim_id=claim_id,
            review_run_id=review_run_id,
            claimed_at=now.isoformat(),
            lease_expires_at=expires_at,
        )
        claim_file = self.claims_dir / f"{review_batch_id}.{claim_id}.json"
        write_atomic_json(claim_file, claim)
        return claim

    def renew_lease(
        self,
        review_batch_id: str,
        claim_id: str,
        lease_seconds: float = 180.0,
    ) -> ReviewClaimStatusEnvelope:
        """Update self-owned lease renewal in review_claim_status/<batch_id>.<claim_id>.json."""
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=lease_seconds)).isoformat()
        status = ReviewClaimStatusEnvelope(
            review_batch_id=review_batch_id,
            claim_id=claim_id,
            last_heartbeat=now.isoformat(),
            lease_expires_at=expires_at,
        )
        status_file = self.status_dir / f"{review_batch_id}.{claim_id}.json"
        write_atomic_json(status_file, status)
        return status

    def load_claim(self, review_batch_id: str, claim_id: str) -> ReviewClaimEnvelope | None:
        """Load claim artifact for specific batch and claim_id."""
        claim_file = self.claims_dir / f"{review_batch_id}.{claim_id}.json"
        if not claim_file.exists():
            return None
        try:
            return ReviewClaimEnvelope.model_validate_json(claim_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    def get_lease_expiration(self, review_batch_id: str, claim_id: str) -> datetime | None:
        """Get the latest lease expiration date (from status if exists, else from claim)."""
        status_file = self.status_dir / f"{review_batch_id}.{claim_id}.json"
        if status_file.exists():
            try:
                status = ReviewClaimStatusEnvelope.model_validate_json(status_file.read_text(encoding="utf-8"))
                return datetime.fromisoformat(status.lease_expires_at)
            except Exception:
                pass

        claim = self.load_claim(review_batch_id, claim_id)
        if claim:
            try:
                return datetime.fromisoformat(claim.lease_expires_at)
            except Exception:
                return None
        return None

    def is_claim_active(self, review_batch_id: str, claim_id: str) -> bool:
        """Check if claim is valid and lease has not expired."""
        exp = self.get_lease_expiration(review_batch_id, claim_id)
        if not exp:
            return False
        return datetime.now(timezone.utc) < exp

    def get_active_claims(self, review_batch_id: str) -> list[ReviewClaimEnvelope]:
        """Return all unexpired claims for this batch."""
        active: list[ReviewClaimEnvelope] = []
        for claim_file in self.claims_dir.glob(f"{review_batch_id}.*.json"):
            parts = claim_file.stem.split(".", 1)
            if len(parts) == 2:
                cid = parts[1]
                if self.is_claim_active(review_batch_id, cid):
                    c = self.load_claim(review_batch_id, cid)
                    if c:
                        active.append(c)
        return active


def validate_ingress_response(
    response: ReviewResponseEnvelope,
    session_id: str,
    request: ReviewRequestEnvelope,
    claim: ReviewClaimEnvelope,
    active_finding_ids: set[str] | list[str],
) -> tuple[bool, str | None]:
    """Execute the 8-point companion ingress validation gate on candidate response."""
    # Rule 1: Matching request and claim provenance
    if claim.review_batch_id != request.review_batch_id:
        return False, f"claim review_batch_id mismatch: {claim.review_batch_id} != {request.review_batch_id}"
    if response.claim_id != claim.claim_id:
        return False, f"claim_id mismatch: {response.claim_id} != {claim.claim_id}"
    if response.review_run_id != claim.review_run_id:
        return False, f"review_run_id mismatch: {response.review_run_id} != {claim.review_run_id}"

    # Rule 2: Schema conformity (validated via Pydantic model type)
    if not isinstance(response, ReviewResponseEnvelope):
        return False, "response does not conform to ReviewResponseEnvelope"

    # Rule 3: Batch ID & session match
    if response.review_batch_id != request.review_batch_id:
        return False, f"review_batch_id mismatch: {response.review_batch_id} != {request.review_batch_id}"
    if response.session_id != session_id:
        return False, f"session_id mismatch: {response.session_id} != {session_id}"

    # Rule 4: Sequence bounds match
    if response.sequence_start != request.sequence_start or response.sequence_end != request.sequence_end:
        return (
            False,
            f"sequence bounds mismatch: [{response.sequence_start}, {response.sequence_end}] != [{request.sequence_start}, {request.sequence_end}]",
        )

    # Rule 5: Full evidence accounting
    req_ids = set(request.evidence_ids)
    acc_ids = response.accounted_evidence_ids

    # Check duplicates in accounted
    if len(acc_ids) != len(set(acc_ids)):
        return False, "duplicate accounted evidence IDs in response"

    if set(acc_ids) != req_ids:
        missing = req_ids - set(acc_ids)
        unknown = set(acc_ids) - req_ids
        if unknown:
            return False, f"unknown evidence IDs in response: {sorted(list(unknown))}"
        return False, f"evidence accounting mismatch: missing {len(missing)} of {len(req_ids)} requested evidence IDs"

    for op in response.operations:
        for ref in op.evidence_refs:
            if ref not in req_ids:
                return False, f"finding evidence_ref {ref} not in requested evidence IDs"

    # Rule 6: Finding identity integrity
    active_set = set(active_finding_ids)
    for op in response.operations:
        if op.op == "UPDATE_FINDING":
            if not op.target_finding_id:
                return False, "UPDATE_FINDING requires target_finding_id"
            if RE_PATH_TRAVERSAL.search(op.target_finding_id):
                return False, f"invalid target_finding_id characters / path traversal: {op.target_finding_id}"
            if op.target_finding_id not in active_set:
                return False, f"target_finding_id does not exist in active session findings: {op.target_finding_id}"
        elif op.op == "CREATE_FINDING":
            if not op.semantic_issue_key:
                return False, "CREATE_FINDING requires semantic_issue_key"

    # Rule 7: Operation & classification validity
    valid_ops = {"CREATE_FINDING", "UPDATE_FINDING", "NO_FINDING"}
    valid_classifications = {
        "WATCHING",
        "POSSIBLE_PATTERN",
        "CORROBORATED",
        "LIKELY_DEFECT",
        "USABILITY_SIGNAL",
        "DATA_GAP",
        "NOT_ENOUGH_EVIDENCE",
    }
    for op in response.operations:
        if op.op not in valid_ops:
            return False, f"invalid operation: {op.op}"
        if op.classification not in valid_classifications:
            return False, f"invalid classification: {op.classification}"

    # Rule 8: Targeted privacy & security validation
    for op in response.operations:
        # Length bounds
        if len(op.safe_summary) > 300:
            return False, f"safe_summary exceeds length limit (300): {len(op.safe_summary)}"
        if op.corroboration_note and len(op.corroboration_note) > 500:
            return False, f"corroboration_note exceeds length limit (500): {len(op.corroboration_note)}"
        if op.semantic_issue_key and len(op.semantic_issue_key) > 100:
            return False, f"semantic_issue_key exceeds length limit (100): {len(op.semantic_issue_key)}"

        text_to_check = f"{op.safe_summary} {op.corroboration_note or ''} {op.semantic_issue_key or ''}"

        # PoE chat / whisper
        if RE_POE_CHAT.search(text_to_check):
            return False, f"PoE chat / whisper pattern detected in response: {text_to_check[:50]}"

        # Credentials / secrets
        if RE_CREDENTIALS.search(text_to_check):
            return False, f"credential / secret pattern detected in response: {text_to_check[:50]}"

        # Path traversal
        if RE_PATH_TRAVERSAL.search(text_to_check):
            return False, f"directory traversal sequence detected in response text: {text_to_check[:50]}"

    return True, None


class ReviewBridgeCoordinator:
    """Coordinates immutable request emission, claim arbitration, and finding evolution."""

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
        self.run_id = run_id or f"coord_{os.urandom(6).hex()}"

        self.live_analysis_dir = self.session_dir / "live_analysis"
        self.requests_dir = self.live_analysis_dir / "review_requests"
        self.responses_dir = self.live_analysis_dir / "review_responses"
        self.batches_dir = self.live_analysis_dir / "review_batches"
        self.coordinator_state_file = self.live_analysis_dir / "coordinator_state.json"

        self.live_analysis_dir.mkdir(parents=True, exist_ok=True)
        self.requests_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        self.batches_dir.mkdir(parents=True, exist_ok=True)

        self.analyst = LocalLiveAnalyst(session_dir=self.session_dir, session_id=self.session_id)
        self.cursor_mgr = ReviewCursorManager(
            cursor_path=self.live_analysis_dir / "hermes_review_cursor.json",
            session_id=self.session_id,
        )
        self.journal = ReviewJournalManager(session_dir=self.session_dir, session_id=self.session_id)
        self.status_mgr = HermesReviewStatusManager(
            status_path=self.live_analysis_dir / "hermes_review_status.json"
        )
        self.claim_mgr = ReviewClaimManager(session_dir=self.session_dir)
        self.coverage_mgr = RequestCoverageManager()
        self.coverage_mgr.reconstruct_from_session(self.session_dir)

        # In-memory priority state cache: batch_id -> RequestPriorityState
        self._priority_states: dict[str, RequestPriorityState] = {}
        self._load_coordinator_state()

    def _load_coordinator_state(self) -> None:
        if not self.coordinator_state_file.exists():
            return
        try:
            raw = json.loads(self.coordinator_state_file.read_text(encoding="utf-8"))
            for p_dict in raw.get("priorities", []):
                p = RequestPriorityState.model_validate(p_dict)
                self._priority_states[p.review_batch_id] = p
        except Exception:
            pass

    def _save_coordinator_state(self) -> None:
        payload = {
            "schema_version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "priorities": [p.model_dump() for p in self._priority_states.values()],
        }
        write_atomic_json(self.coordinator_state_file, payload)

    def get_request_priority(self, review_batch_id: str) -> str:
        p = self._priority_states.get(review_batch_id)
        return p.priority if p else "NORMAL"

    def set_request_priority(self, review_batch_id: str, priority: str, reason: str = "") -> None:
        p = RequestPriorityState(
            review_batch_id=review_batch_id,
            priority=priority,
            priority_reason=reason,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._priority_states[review_batch_id] = p
        self._save_coordinator_state()
        prio_dir = self.live_analysis_dir / "review_priority"
        prio_dir.mkdir(parents=True, exist_ok=True)
        (prio_dir / f"{review_batch_id}.priority.json").write_text(p.model_dump_json(), encoding="utf-8")

    def elevate_priority(self, review_batch_id: str, priority: str, reason: str = "") -> bool:
        """Elevate scheduling priority of an existing request."""
        self.set_request_priority(review_batch_id, priority, reason)
        return True

    def _collect_existing_findings_context(self) -> list[ExistingFindingContext]:
        findings = self.journal.get_findings()
        ctx_list: list[ExistingFindingContext] = []
        for f in findings:
            ctx_list.append(
                ExistingFindingContext(
                    finding_id=f.finding_id,
                    category=f.category,
                    classification=f.status.value if hasattr(f.status, "value") else str(f.status),
                    safe_summary=f.summary or f.title,
                    relevant_subject_or_key=f.semantic_issue_key,
                    evidence_count=f.occurrence_count,
                    recent_evidence_refs=f.evidence_refs[-5:],
                )
            )
        return ctx_list

    def create_review_request(
        self,
        sequence_start: int,
        sequence_end: int,
        evidence_ids: list[str],
        high_priority_signals: list[dict[str, Any]] | None = None,
        priority: str = "NORMAL",
        priority_reason: str = "",
    ) -> ReviewRequestEnvelope:
        """Create an immutable review request artifact if not already covered."""
        batch_id = compute_review_batch_id(self.session_id, sequence_start, sequence_end, evidence_ids)
        req_file = self.requests_dir / f"{batch_id}.json"

        if req_file.exists():
            return ReviewRequestEnvelope.model_validate_json(req_file.read_text(encoding="utf-8"))

        if not self.coverage_mgr.can_cover_range(sequence_start, sequence_end):
            raise ValueError(f"Range [{sequence_start}, {sequence_end}] overlaps with existing request coverage")

        existing_findings = self._collect_existing_findings_context()
        req = ReviewRequestEnvelope(
            review_batch_id=batch_id,
            session_id=self.session_id,
            sequence_start=sequence_start,
            sequence_end=sequence_end,
            evidence_ids=evidence_ids,
            high_priority_signals=high_priority_signals or [],
            existing_findings=existing_findings,
        )

        write_atomic_json(req_file, req)
        self.coverage_mgr.register_range(sequence_start, sequence_end, batch_id)
        if priority != "NORMAL":
            self.set_request_priority(batch_id, priority, priority_reason)

        return req

    def handle_marker_arrival(self, marker_sequence: int, marker_id: str) -> str | None:
        """Handle high-priority marker: elevates existing pending request or forms next request."""
        owning = self.coverage_mgr.get_owning_batch(marker_sequence)
        if owning:
            self.set_request_priority(owning, "HIGH_MARKER", f"User marker {marker_id} at sequence {marker_sequence}")
            return owning
        return None

    def _collect_envelopes_in_range(self, start_seq: int, end_seq: int) -> list[ObservationEnvelope]:
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

    def emit_pending_requests(self) -> list[ReviewRequestEnvelope]:
        """Emit review requests for unreviewed sequences up to reader contiguous frontier."""
        reader_frontier = self.analyst.reader.contiguous_frontier
        review_frontier = self.cursor_mgr.review_contiguous_frontier

        if reader_frontier <= review_frontier:
            return []

        created: list[ReviewRequestEnvelope] = []
        curr = review_frontier + 1

        while curr <= reader_frontier:
            owning = self.coverage_mgr.get_owning_batch(curr)
            if owning:
                curr += 1
                continue

            end_seq = min(reader_frontier, curr + self.batch_size - 1)
            # Find next covered sequence if any
            for s, _, _ in self.coverage_mgr.ranges:
                if curr < s <= end_seq:
                    end_seq = s - 1
                    break

            if end_seq < curr:
                curr += 1
                continue

            batch_envs = self._collect_envelopes_in_range(curr, end_seq)
            evidence_ids = [e.event_id for e in batch_envs]

            # Check if any marker inside
            has_marker = any(e.event_type == "USER_MARKER" for e in batch_envs)
            prio = "HIGH_MARKER" if has_marker else "NORMAL"

            req = self.create_review_request(
                sequence_start=curr,
                sequence_end=end_seq,
                evidence_ids=evidence_ids,
                priority=prio,
                priority_reason="Marker present in batch" if has_marker else "",
            )
            created.append(req)
            curr = end_seq + 1

        return created

    def load_request(self, review_batch_id: str) -> ReviewRequestEnvelope | None:
        path = self.requests_dir / f"{review_batch_id}.json"
        if not path.exists():
            return None
        try:
            return ReviewRequestEnvelope.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def process_candidate_response(
        self,
        response: ReviewResponseEnvelope,
    ) -> tuple[bool, str | None]:
        """Validate candidate response and promote to canonical ReviewBatchResult if valid."""
        request = self.load_request(response.review_batch_id)
        if not request:
            return False, f"matching review request not found for {response.review_batch_id}"

        claim = self.claim_mgr.load_claim(response.review_batch_id, response.claim_id)
        if not claim:
            return False, f"matching claim artifact not found for {response.review_batch_id}.{response.claim_id}"

        active_findings = {f.finding_id for f in self.journal.get_findings()}

        # Ingress validation
        valid, err = validate_ingress_response(
            response=response,
            session_id=self.session_id,
            request=request,
            claim=claim,
            active_finding_ids=active_findings,
        )
        if not valid:
            return False, err

        # Concurrency arbitration: first valid promoted response wins
        existing_result = self.journal.load_batch_result(response.review_batch_id)
        if existing_result and existing_result.review_status == "COMPLETED":
            # Another candidate already promoted; safely reject/ignore without mutating canonical result
            return False, f"batch {response.review_batch_id} already has canonical result from claim {existing_result.claim_id}"

        # Transform response operations to Journal FindingOperations
        journal_ops: list[FindingOperation] = []
        for op in response.operations:
            classification_str = op.classification or "WATCHING"
            try:
                status_enum = FindingStatus(classification_str)
            except ValueError:
                if "DEFECT" in classification_str:
                    status_enum = FindingStatus.LIKELY_DEFECT
                elif "CORROBORATED" in classification_str:
                    status_enum = FindingStatus.CORROBORATED
                else:
                    status_enum = FindingStatus.WATCHING

            if op.op == "CREATE_FINDING":
                fid = compute_finding_id(self.session_id, op.category, op.semantic_issue_key or "unspecified")
                journal_ops.append(
                    FindingOperation(
                        op="CREATE",
                        finding_id=fid,
                        category=op.category,
                        semantic_issue_key=op.semantic_issue_key or "unspecified",
                        status=status_enum,
                        title=f"{op.category.capitalize()}: {op.semantic_issue_key}",
                        summary=op.safe_summary,
                        occurrence_count_delta=op.occurrence_count_delta,
                        new_evidence_ids=op.evidence_refs,
                        corroboration_note=op.corroboration_note,
                        uncertainty=op.uncertainty,
                        missing_evidence=op.missing_evidence,
                    )
                )
            elif op.op == "UPDATE_FINDING":
                journal_ops.append(
                    FindingOperation(
                        op="UPDATE",
                        finding_id=op.target_finding_id or "",
                        category=op.category,
                        semantic_issue_key=op.semantic_issue_key or "",
                        status=status_enum,
                        title=f"Updated finding {op.target_finding_id}",
                        summary=op.safe_summary,
                        occurrence_count_delta=op.occurrence_count_delta,
                        new_evidence_ids=op.evidence_refs,
                        corroboration_note=op.corroboration_note,
                        uncertainty=op.uncertainty,
                        missing_evidence=op.missing_evidence,
                    )
                )
            elif op.op == "NO_FINDING":
                journal_ops.append(
                    FindingOperation(
                        op="NO_FINDING",
                        finding_id=compute_finding_id(self.session_id, "routine", "clean"),
                        category="routine",
                        semantic_issue_key="clean",
                        status=FindingStatus.NOT_ENOUGH_EVIDENCE,
                        title="Routine sequence review",
                        summary=op.safe_summary or "Clean trace",
                    )
                )

        batch_result = ReviewBatchResult(
            review_batch_id=response.review_batch_id,
            session_id=self.session_id,
            sequence_start=response.sequence_start,
            sequence_end=response.sequence_end,
            reviewed_evidence_ids=response.accounted_evidence_ids,
            claim_id=response.claim_id,
            review_run_id=response.review_run_id,
            operations=journal_ops,
            review_status="COMPLETED",
        )

        # 1. Save canonical batch result
        self.journal.save_batch_result(batch_result)

        # 2. Apply findings idempotently
        self.journal.apply_batch_result(batch_result)

        # 3. Advance review cursor
        self.cursor_mgr.record_batch_reviewed(
            batch_result.review_batch_id, response.sequence_start, response.sequence_end
        )
        self.cursor_mgr.save_atomic()

        # 4. Update status heartbeat
        self.status_mgr.update_heartbeat(self.run_id, response.sequence_end, state="ACTIVE")

        return True, None

    def poll_and_process_responses(self) -> int:
        """Scan review_responses/ and process all pending candidates."""
        processed = 0
        for resp_file in self.responses_dir.glob("*.json"):
            try:
                raw = resp_file.read_text(encoding="utf-8")
                resp = ReviewResponseEnvelope.model_validate_json(raw)
                ok, _ = self.process_candidate_response(resp)
                if ok:
                    processed += 1
            except Exception:
                continue
        return processed

    def step_review(self) -> None:
        """Step local analyst, emit pending requests, and process any candidate responses."""
        self.analyst.step()
        self.emit_pending_requests()
        self.poll_and_process_responses()


class TestReviewResponder:
    """Offline test adapter simulating external Hermes for unit tests and CI."""

    __test__ = False

    def __init__(self, session_dir: Path, run_id: str = "run_test_01") -> None:
        self.session_dir = session_dir
        self.run_id = run_id
        self.claim_mgr = ReviewClaimManager(session_dir=self.session_dir)
        self.responses_dir = self.session_dir / "live_analysis" / "review_responses"
        self.requests_dir = self.session_dir / "live_analysis" / "review_requests"
        self.responses_dir.mkdir(parents=True, exist_ok=True)

    def discover_pending_requests(self) -> list[ReviewRequestEnvelope]:
        reqs: list[ReviewRequestEnvelope] = []
        for f in self.requests_dir.glob("*.json"):
            try:
                reqs.append(ReviewRequestEnvelope.model_validate_json(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return sorted(reqs, key=lambda r: r.sequence_start)

    def claim(
        self,
        request: ReviewRequestEnvelope,
        claim_id: str = "clm_test_01",
        lease_seconds: float = 180.0,
    ) -> ReviewClaimEnvelope:
        return self.claim_mgr.claim_request(
            review_batch_id=request.review_batch_id,
            claim_id=claim_id,
            review_run_id=self.run_id,
            lease_seconds=lease_seconds,
        )

    def respond(
        self,
        request: ReviewRequestEnvelope,
        claim: ReviewClaimEnvelope,
        operations: list[FindingOperationModel] | None = None,
        accounted_evidence_ids: list[str] | None = None,
    ) -> ReviewResponseEnvelope:
        if accounted_evidence_ids is None:
            accounted_evidence_ids = list(request.evidence_ids)

        if operations is None:
            operations = [
                FindingOperationModel(
                    op="NO_FINDING",
                    category="routine",
                    safe_summary="Clean trace",
                )
            ]

        resp = ReviewResponseEnvelope(
            review_batch_id=request.review_batch_id,
            session_id=request.session_id,
            sequence_start=request.sequence_start,
            sequence_end=request.sequence_end,
            accounted_evidence_ids=accounted_evidence_ids,
            claim_id=claim.claim_id,
            review_run_id=claim.review_run_id,
            operations=operations,
        )

        resp_file = self.responses_dir / f"{request.review_batch_id}.{claim.claim_id}.json"
        write_atomic_json(resp_file, resp)
        return resp
