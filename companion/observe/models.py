"""Domain models, fact taxonomy, and evidence envelopes for Development Observation Mode."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


class FactKind(str, Enum):
    """Fact taxonomy reflecting evidence and epistemic certainty."""

    OBSERVED_FACT = "OBSERVED_FACT"
    DERIVED_FACT = "DERIVED_FACT"
    INFERENCE = "INFERENCE"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


class HealthState(str, Enum):
    """Operational health state of the observer subsystem."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class EvidencePriority(str, Enum):
    """Deterministic priority tiers for bounded queue shedding under backpressure."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ManifestStatus(str, Enum):
    """Lifecycle status of an observation session manifest."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    INCOMPLETE = "INCOMPLETE"
    ABORTED = "ABORTED"


class ObserverHealth(BaseModel):
    """Health status and error tracking for DevelopmentObserver."""

    model_config = ConfigDict(frozen=True)

    state: HealthState = HealthState.HEALTHY
    last_error: str | None = None
    error_count: int = 0
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StateDeltaRecord(BaseModel):
    """Compact before/after delta for a single mutated field in CharacterState."""

    model_config = ConfigDict(frozen=True)

    field: str
    before: Any
    after: Any
    source: str
    verification_status: str
    evidence_refs: list[str] = Field(default_factory=list)


class ObjectiveDecisionTrace(BaseModel):
    """Detailed objective evaluation trace."""

    model_config = ConfigDict(frozen=True)

    triggers: list[str] = Field(default_factory=list)
    state_delta_refs: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    selected_objective_id: str | None = None
    selection_reasons: list[str] = Field(default_factory=list)
    suppressed_candidates: dict[str, str] = Field(default_factory=dict)
    objective_changed: bool = False


class NotificationTraceRecord(BaseModel):
    """Record of notification disposition and delivery decision."""

    model_config = ConfigDict(frozen=True)

    notification_id: str
    category: str
    severity: str
    safe_zone: bool
    dispatch_status: str  # DELIVERED, QUEUED, DEDUPED, SUPPRESSED
    queue_depth: int = 0
    suppression_reason: str | None = None
    cooldown_key: str | None = None


class AnomalySignatureRecord(BaseModel):
    """Grouped unknown log anomaly signature and privacy-bounded samples."""

    model_config = ConfigDict(frozen=True)

    pattern_hash: str
    classification: str
    occurrence_count: int
    first_seen_at: str
    last_seen_at: str
    privacy_sample_withheld: bool = False
    sanitized_samples: list[str] = Field(default_factory=list)


class OperationalTelemetryRecord(BaseModel):
    """Lightweight operational performance metrics using monotonic timers."""

    model_config = ConfigDict(frozen=True)

    loop_duration_ms: float = 0.0
    log_poll_latency_ms: float = 0.0
    enqueue_latency_ms: float = 0.0
    observer_queue_depth: int = 0
    queue_high_watermark: int = 0
    dropped_event_count: int = 0
    dropped_high_priority_count: int = 0
    writer_latency_ms: float = 0.0
    screenshot_capture_latency_ms: float = 0.0
    worker_error_count: int = 0
    storage_bytes: int = 0


class UserMarkerRecord(BaseModel):
    """Manual development marker recorded by player or engineer."""

    model_config = ConfigDict(frozen=True)

    marker_id: str
    created_at: str
    note: str
    character_id: str | None = None
    zone: str | None = None
    top_objective_id: str | None = None
    correlated_sequence_number: int | None = None


class ScreenshotRecord(BaseModel):
    """Structured result of an event-triggered screenshot capture attempt."""

    model_config = ConfigDict(frozen=True)

    screenshot_id: str
    trigger_event: str
    capture_result: str  # CAPTURED, SKIPPED_BUDGET, SKIPPED_COOLDOWN, SKIPPED_SHUTDOWN, CAPTURE_FAILED
    relative_path: str | None = None
    sha256: str | None = None
    width: int | None = None
    height: int | None = None
    error_message: str | None = None


class ObservationEnvelope(BaseModel):
    """Canonical envelope wrapping all development observation evidence items."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    observation_session_id: str
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex}")
    sequence_number: int = Field(ge=1)
    taxonomy: FactKind
    recorded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_timestamp: str | None = None
    event_type: str
    source_ref: str | None = None
    correlation_refs: list[str] = Field(default_factory=list)
    correlation_missing_due_to_backpressure: bool = False
    priority: EvidencePriority = EvidencePriority.MEDIUM
    payload: dict[str, Any] = Field(default_factory=dict)


class ExistingFindingContext(BaseModel):
    """Sanitized context of an existing finding passed to Hermes review requests."""

    model_config = ConfigDict(frozen=True)

    finding_id: str
    category: str
    classification: str
    safe_summary: str
    relevant_subject_or_key: str
    evidence_count: int
    recent_evidence_refs: list[str] = Field(default_factory=list)


class ReviewRequestEnvelope(BaseModel):
    """Immutable review request envelope published to the filesystem bridge."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    review_batch_id: str
    session_id: str
    sequence_start: int
    sequence_end: int
    evidence_ids: list[str]
    high_priority_signals: list[dict[str, Any]] = Field(default_factory=list)
    marker_refs: list[dict[str, Any]] = Field(default_factory=list)
    objective_refs: list[dict[str, Any]] = Field(default_factory=list)
    notification_refs: list[dict[str, Any]] = Field(default_factory=list)
    unknown_stale_refs: list[dict[str, Any]] = Field(default_factory=list)
    anomaly_refs: list[dict[str, Any]] = Field(default_factory=list)
    existing_findings: list[ExistingFindingContext] = Field(default_factory=list)
    evidence_locations: dict[str, Any] = Field(default_factory=dict)
    privacy_instructions: str = (
        "Do NOT reproduce private player chat, whispers, credentials, or session tokens. "
        "Cite only event IDs and sanitized signature hashes. Paraphrase user marker notes."
    )
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ReviewClaimEnvelope(BaseModel):
    """Claim artifact authored by a Hermes review run to claim a review request."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    review_batch_id: str
    claim_id: str
    review_run_id: str
    claimed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    lease_expires_at: str


class ReviewClaimStatusEnvelope(BaseModel):
    """Self-owned lease renewal and heartbeat status authored by the active claimant."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    review_batch_id: str
    claim_id: str
    last_heartbeat: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    lease_expires_at: str


class RequestPriorityState(BaseModel):
    """Coordinator-owned mutable scheduling priority metadata for a review batch."""

    model_config = ConfigDict(frozen=True)

    review_batch_id: str
    priority: str = "NORMAL"  # NORMAL, HIGH_MARKER, HIGH_ERROR
    priority_reason: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FindingOperationModel(BaseModel):
    """Single finding operation emitted by external Hermes in review response."""

    model_config = ConfigDict(frozen=True)

    op: str  # CREATE_FINDING, UPDATE_FINDING, NO_FINDING
    target_finding_id: str | None = None
    category: str = "routine"
    semantic_issue_key: str | None = None
    classification: str = "NOT_ENOUGH_EVIDENCE"
    safe_summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    occurrence_count_delta: int = 1
    corroboration_note: str | None = None
    uncertainty: str | None = None
    missing_evidence: list[str] | str | None = None


class ReviewResponseEnvelope(BaseModel):
    """Claim-specific structured review response published by external Hermes."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    review_batch_id: str
    session_id: str
    sequence_start: int
    sequence_end: int
    accounted_evidence_ids: list[str]
    claim_id: str
    review_run_id: str
    reviewed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    operations: list[FindingOperationModel] = Field(default_factory=list)

