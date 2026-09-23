"""Tests for development observation models and evidence envelopes."""

import uuid
import pytest
from pydantic import ValidationError

from companion.observe.models import (
    FactKind,
    HealthState,
    ObserverHealth,
    EvidencePriority,
    ManifestStatus,
    ObservationEnvelope,
    StateDeltaRecord,
    ObjectiveDecisionTrace,
    NotificationTraceRecord,
    AnomalySignatureRecord,
    OperationalTelemetryRecord,
    UserMarkerRecord,
    ScreenshotRecord,
)


def test_fact_kind_taxonomy_values():
    assert FactKind.OBSERVED_FACT.value == "OBSERVED_FACT"
    assert FactKind.DERIVED_FACT.value == "DERIVED_FACT"
    assert FactKind.INFERENCE.value == "INFERENCE"
    assert FactKind.UNKNOWN.value == "UNKNOWN"
    assert FactKind.ERROR.value == "ERROR"


def test_health_state_values():
    assert HealthState.HEALTHY.value == "HEALTHY"
    assert HealthState.DEGRADED.value == "DEGRADED"
    assert HealthState.FAILED.value == "FAILED"


def test_evidence_priority_tiers():
    assert EvidencePriority.HIGH.value == "HIGH"
    assert EvidencePriority.MEDIUM.value == "MEDIUM"
    assert EvidencePriority.LOW.value == "LOW"


def test_manifest_status_values():
    assert ManifestStatus.OPEN.value == "OPEN"
    assert ManifestStatus.CLOSED.value == "CLOSED"
    assert ManifestStatus.INCOMPLETE.value == "INCOMPLETE"
    assert ManifestStatus.ABORTED.value == "ABORTED"


def test_observation_envelope_serialization_and_fields():
    envelope = ObservationEnvelope(
        schema_version="1.0",
        observation_session_id="obs_test_123",
        event_id="evt_01",
        sequence_number=1,
        taxonomy=FactKind.OBSERVED_FACT,
        recorded_at="2026-09-23T14:00:00Z",
        source_timestamp="2026/09/23 13:59:59",
        event_type="LOG_LINE",
        source_ref="client_log:100",
        correlation_refs=["evt_prev"],
        correlation_missing_due_to_backpressure=False,
        priority=EvidencePriority.MEDIUM,
        payload={"raw": "test"},
    )
    assert envelope.schema_version == "1.0"
    assert envelope.sequence_number == 1
    assert envelope.recorded_at != envelope.source_timestamp
    data = envelope.model_dump()
    assert data["taxonomy"] == "OBSERVED_FACT"
    assert data["priority"] == "MEDIUM"
    assert data["sequence_number"] == 1


def test_observation_envelope_validation():
    # Sequence number must be strictly >= 1
    with pytest.raises(ValidationError):
        ObservationEnvelope(
            schema_version="1.0",
            observation_session_id="obs_test_123",
            event_id="evt_01",
            sequence_number=0,  # Invalid: must be >= 1
            taxonomy=FactKind.DERIVED_FACT,
            recorded_at="2026-09-23T14:00:00Z",
            event_type="TEST",
        )


def test_structured_domain_models_instantiation():
    delta = StateDeltaRecord(
        field="level",
        before=10,
        after=11,
        source="client_log:level_up",
        verification_status="VERIFIED",
    )
    assert delta.field == "level"
    assert delta.before == 10
    assert delta.after == 11

    obj_trace = ObjectiveDecisionTrace(
        triggers=["level_up"],
        state_delta_refs=["evt_delta_1"],
        candidate_ids=["obj_1", "obj_2"],
        selected_objective_id="obj_1",
        selection_reasons=["Highest priority"],
        suppressed_candidates={"obj_2": "STALE_PREREQUISITE"},
        objective_changed=True,
    )
    assert obj_trace.selected_objective_id == "obj_1"
    assert obj_trace.objective_changed is True

    notif_trace = NotificationTraceRecord(
        notification_id="notif_1",
        category="LEVEL_UP",
        severity="INFO",
        safe_zone=True,
        dispatch_status="DELIVERED",
        queue_depth=0,
    )
    assert notif_trace.dispatch_status == "DELIVERED"

    anomaly = AnomalySignatureRecord(
        pattern_hash="hash123",
        classification="UNKNOWN_DEBUG",
        occurrence_count=5,
        first_seen_at="2026-09-23T14:00:00Z",
        last_seen_at="2026-09-23T14:05:00Z",
        privacy_sample_withheld=True,
        sanitized_samples=[],
    )
    assert anomaly.privacy_sample_withheld is True

    telemetry = OperationalTelemetryRecord(
        enqueue_latency_ms=0.15,
        observer_queue_depth=12,
        queue_high_watermark=25,
        dropped_event_count=0,
        dropped_high_priority_count=0,
    )
    assert telemetry.enqueue_latency_ms == 0.15
    assert telemetry.queue_high_watermark == 25

    marker = UserMarkerRecord(
        marker_id="m_1",
        created_at="2026-09-23T14:00:00Z",
        note="Interesting zone transition",
        zone="The Riverbank",
    )
    assert marker.note == "Interesting zone transition"

    screen = ScreenshotRecord(
        screenshot_id="s_1",
        trigger_event="OBJECTIVE_CHANGED",
        capture_result="CAPTURED",
        relative_path="screenshots/s_1.png",
        sha256="abcd",
        width=1920,
        height=1080,
    )
    assert screen.capture_result == "CAPTURED"
