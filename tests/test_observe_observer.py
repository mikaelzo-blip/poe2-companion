"""Tests for DevelopmentObserver core, backpressure, health, and trace recording."""

from pathlib import Path
import time
import pytest

from companion.observe.models import (
    EvidencePriority,
    FactKind,
    HealthState,
    ObservationEnvelope,
    StateDeltaRecord,
)
from companion.observe.observer import DevelopmentObserver
from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.schema import CharacterState


def test_observer_bounded_queue_non_blocking_and_writer_lag(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    # Small queue of 5 items
    observer = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_lag_test",
        runtime_run_id="run_1",
        queue_size=5,
    )
    observer.start()

    # Enqueue should be fast and non-blocking
    t0 = time.perf_counter()
    for i in range(10):
        observer.emit_event(
            event_type="TEST_TICK",
            taxonomy=FactKind.OBSERVED_FACT,
            priority=EvidencePriority.LOW,
            payload={"i": i},
        )
    elapsed = time.perf_counter() - t0
    # Must be sub-second (typically < 10ms)
    assert elapsed < 0.5

    observer.stop(timeout=2.0)
    assert observer.sequence_high_watermark == 10
    # Because capacity was 5 and writer was processing, some might be persisted and some dropped
    total = observer.persisted_event_count + observer.dropped_event_count
    assert total == observer.sequence_high_watermark


def test_backpressure_priority_drop_policy(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    # Do not start background worker thread so queue stays full
    observer = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_drop_test",
        runtime_run_id="run_1",
        queue_size=3,
        auto_start=False,
    )

    # 1. Fill queue with 1 LOW, 1 MEDIUM, 1 HIGH
    observer.emit_event("LOW_1", FactKind.OBSERVED_FACT, EvidencePriority.LOW)
    observer.emit_event("MED_1", FactKind.OBSERVED_FACT, EvidencePriority.MEDIUM)
    observer.emit_event("HIGH_1", FactKind.OBSERVED_FACT, EvidencePriority.HIGH)
    assert observer.queue_depth == 3
    assert observer.dropped_event_count == 0

    # 2. Enqueue another HIGH item -> should evict the oldest LOW item
    observer.emit_event("HIGH_2", FactKind.OBSERVED_FACT, EvidencePriority.HIGH)
    assert observer.queue_depth == 3
    assert observer.dropped_event_count == 1
    assert observer.dropped_high_priority_count == 0
    # Verify remaining in queue are MED_1, HIGH_1, HIGH_2
    queued_types = [env.event_type for env in observer._queue_snapshot()]
    assert "LOW_1" not in queued_types
    assert "MED_1" in queued_types
    assert "HIGH_2" in queued_types

    # 3. Enqueue another HIGH item -> should evict MED_1
    observer.emit_event("HIGH_3", FactKind.OBSERVED_FACT, EvidencePriority.HIGH)
    assert observer.queue_depth == 3
    assert observer.dropped_event_count == 2
    assert observer.dropped_high_priority_count == 0
    queued_types = [env.event_type for env in observer._queue_snapshot()]
    assert "MED_1" not in queued_types

    # 4. Now queue has only HIGH items. Enqueue a new LOW -> dropped at boundary
    observer.emit_event("LOW_2", FactKind.OBSERVED_FACT, EvidencePriority.LOW)
    assert observer.dropped_event_count == 3
    assert observer.dropped_high_priority_count == 0

    # 5. Enqueue a new HIGH into all-HIGH queue -> sheds oldest HIGH and increments dropped_high_priority_count
    observer.emit_event("HIGH_4", FactKind.OBSERVED_FACT, EvidencePriority.HIGH)
    assert observer.dropped_event_count == 4
    assert observer.dropped_high_priority_count == 1


def test_backpressure_surviving_child_marked_with_missing_correlation(tmp_path: Path):
    """Surviving children referencing dropped parent are marked with missing-correlation evidence."""
    base_dir = tmp_path / "runtime" / "observations"
    observer = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_corr_test",
        runtime_run_id="run_1",
        queue_size=2,
        auto_start=False,
    )

    # 1. Enqueue parent LOW event
    parent = observer.emit_event("PARENT_LOW", FactKind.OBSERVED_FACT, EvidencePriority.LOW)
    assert parent is not None

    # 2. Enqueue two HIGH events to force parent out of queue
    observer.emit_event("HIGH_A", FactKind.OBSERVED_FACT, EvidencePriority.HIGH)
    observer.emit_event("HIGH_B", FactKind.OBSERVED_FACT, EvidencePriority.HIGH)

    assert observer.dropped_event_count == 1
    assert parent.event_id in observer.dropped_event_ids

    # 3. Emit downstream child referencing the dropped parent
    child = observer.emit_event(
        "CHILD_EVENT",
        FactKind.DERIVED_FACT,
        EvidencePriority.HIGH,
        correlation_refs=[parent.event_id],
    )
    assert child is not None
    assert child.correlation_missing_due_to_backpressure is True
    assert parent.event_id in child.correlation_refs


def test_worker_failure_transitions_to_failed_without_crashing_runtime(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    observer = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_fail_test",
        runtime_run_id="run_1",
        queue_size=10,
    )
    # Sabotage storage manager to simulate disk failure
    def _exploding_append(*args, **kwargs):
        raise OSError("Disk full / I/O error")

    observer.storage_manager.append_envelope = _exploding_append
    observer.start()

    # Emit event that worker will fail to write
    observer.emit_event("CRASH_TRIGGER", FactKind.OBSERVED_FACT, EvidencePriority.HIGH)

    # Allow worker thread to catch exception
    time.sleep(0.2)

    assert observer.health.state == HealthState.FAILED
    assert observer.health.error_count >= 1

    # Emitting further events when FAILED does not raise or crash
    observer.emit_event("POST_FAILURE", FactKind.OBSERVED_FACT, EvidencePriority.HIGH)

    observer.stop(timeout=1.0)


def test_compact_state_delta_emits_only_on_actual_change(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    observer = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_delta_test",
        runtime_run_id="run_1",
        auto_start=False,
    )

    state1 = CharacterState.create_initial("Char1", "Witch")
    state2 = state1.model_copy(deep=True)

    # Identical states -> 0 state delta emitted
    deltas = observer.record_state_change(state1, state2, source="poll_tick")
    assert len(deltas) == 0
    assert observer.sequence_high_watermark == 0

    # Mutate level from 1 to 2
    state3 = state2.model_copy(
        update={
            "level": ProvenancedField.create(
                2, source="client_log:level_up", verification_state=VerificationState.VERIFIED
            )
        }
    )
    deltas = observer.record_state_change(state2, state3, source="client_log:level_up")
    assert len(deltas) == 1
    assert deltas[0].field == "level"
    assert deltas[0].before == 1
    assert deltas[0].after == 2
    assert observer.sequence_high_watermark == 1


def test_objective_decision_tracing(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    observer = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_obj_test",
        runtime_run_id="run_1",
        auto_start=False,
    )

    trace = observer.record_objective_evaluation(
        triggers=["level_up"],
        state_delta_refs=["evt_delta_1"],
        candidate_ids=["obj_opt_1", "obj_opt_2"],
        selected_objective_id="obj_opt_1",
        selection_reasons=["Highest priority"],
        suppressed_candidates={"obj_opt_2": "STALE_SOURCE"},
    )
    assert trace.selected_objective_id == "obj_opt_1"
    assert trace.objective_changed is True
    assert observer.sequence_high_watermark == 1


def test_objective_trace_distinguishes_reevaluation_from_selection_change(tmp_path: Path):
    observer = DevelopmentObserver(
        base_dir=tmp_path / "observations",
        session_id="obs_obj_transitions",
        runtime_run_id="run_1",
        auto_start=False,
    )

    def evaluate(selected, candidates, reason):
        return observer.record_objective_evaluation(
            triggers=["zone_enter"],
            state_delta_refs=[],
            candidate_ids=candidates,
            selected_objective_id=selected,
            selection_reasons=[reason],
            suppressed_candidates={},
        )

    assert evaluate(None, [], "no choice").objective_changed is False
    assert evaluate("obj_a", ["obj_a"], "initial").objective_changed is True
    assert evaluate("obj_a", ["obj_a"], "new evidence").objective_changed is False
    assert evaluate("obj_a", ["obj_a", "obj_b"], "candidate changed").objective_changed is False
    assert evaluate("obj_b", ["obj_a", "obj_b"], "new top").objective_changed is True
    assert evaluate(None, [], "no eligible choice").objective_changed is True
    assert observer.sequence_high_watermark == 6


def test_notification_outcome_tracing(tmp_path: Path):
    base_dir = tmp_path / "runtime" / "observations"
    observer = DevelopmentObserver(
        base_dir=base_dir,
        session_id="obs_notif_test",
        runtime_run_id="run_1",
        auto_start=False,
    )

    notif_record = observer.record_notification(
        notification_id="notif_100",
        category="GEAR_UPGRADE",
        severity="INFO",
        safe_zone=True,
        dispatch_status="DELIVERED",
        queue_depth=0,
    )
    assert notif_record.dispatch_status == "DELIVERED"
    assert notif_record.safe_zone is True
    assert observer.sequence_high_watermark == 1
