"""Subordinate development observer coordinating bounded evidence collection and graceful drain."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
import time
from typing import Any, Sequence

from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.models import (
    EvidencePriority,
    FactKind,
    HealthState,
    ManifestStatus,
    NotificationTraceRecord,
    ObjectiveDecisionTrace,
    ObservationEnvelope,
    ObserverHealth,
    OperationalTelemetryRecord,
    ScreenshotRecord,
    StateDeltaRecord,
    UserMarkerRecord,
)
from companion.observe.storage import ObservationStorage, ObservationStorageManager
from companion.state.schema import CharacterState

logger = logging.getLogger(__name__)


class DevelopmentObserver:
    """Subordinate, non-blocking development observation tap attached to continuous runtime."""

    DEFAULT_QUEUE_SIZE = 1000
    DEFAULT_SHUTDOWN_TIMEOUT = 5.0

    def __init__(
        self,
        base_dir: Path,
        session_id: str,
        runtime_run_id: str,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        observe_screens: bool = False,
        observe_display: int = 1,
        auto_start: bool = True,
        storage_manager: ObservationStorage | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.session_id = session_id
        self.session_dir = self.base_dir / self.session_id
        self.runtime_run_id = runtime_run_id
        self.queue_size = queue_size
        self.observe_screens = observe_screens
        self.observe_display = observe_display

        self.storage_manager: ObservationStorage = (
            storage_manager or ObservationStorageManager(self.base_dir, self.session_id)
        )
        self.manifest_manager = ManifestManager(self.session_dir / "session_manifest.json")

        self.screenshot_worker: Any | None = None
        if self.observe_screens:
            from companion.observe.screens import ScreenshotCaptureWorker
            self.screenshot_worker = ScreenshotCaptureWorker(
                output_dir=self.session_dir / "screenshots",
                monitor_index=self.observe_display,
            )

        self.health = ObserverHealth()
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._queue: list[ObservationEnvelope] = []
        self._in_flight_env: ObservationEnvelope | None = None

        self.sequence_high_watermark: int = 0
        self._queue_high_watermark: int = 0
        self.persisted_event_count: int = 0
        self.dropped_event_count: int = 0
        self.dropped_high_priority_count: int = 0
        self.dropped_sequence_ranges: list[list[int]] = []
        self.dropped_event_ids: set[str] = set()
        self._last_state_delta_ids: list[str] = []
        self._last_objective_eval_id: str | None = None

        self._accepting_events: bool = True
        self._worker_thread: threading.Thread | None = None
        self._is_stopped: bool = False
        self._started_at = datetime.now(timezone.utc).isoformat()

        # Ensure inbox directory exists
        (self.base_dir / "marker_inbox").mkdir(parents=True, exist_ok=True)

        from companion.observe.anomalies import LogAnomalyGrouper
        self.anomaly_grouper = LogAnomalyGrouper()

        # Initialize initial manifest
        self._init_manifest()

        if auto_start:
            self.start()

    def _init_manifest(self) -> None:
        """Atomically initialize manifest with status OPEN."""
        manifest = SessionManifest(
            session_id=self.session_id,
            runtime_run_id=self.runtime_run_id,
            started_at=self._started_at,
            status=ManifestStatus.OPEN,
            sequence_high_watermark=0,
            persisted_event_count=0,
            dropped_event_count=0,
            dropped_high_priority_count=0,
            pending_event_count=0,
        )
        self.manifest_manager.save_atomic(manifest)

    @property
    def queue_depth(self) -> int:
        with self._lock:
            return len(self._queue) + (1 if self._in_flight_env is not None else 0)

    @property
    def queue_high_watermark(self) -> int:
        with self._lock:
            return self._queue_high_watermark

    @property
    def is_stopped(self) -> bool:
        return self._is_stopped

    @property
    def last_state_delta_ids(self) -> list[str]:
        with self._lock:
            return list(self._last_state_delta_ids)

    @property
    def last_objective_eval_id(self) -> str | None:
        with self._lock:
            return self._last_objective_eval_id

    def _queue_snapshot(self) -> list[ObservationEnvelope]:
        with self._lock:
            return list(self._queue)

    def start(self) -> None:
        """Start background persistence worker thread."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name=f"DevObserverWorker-{self.session_id}",
                daemon=True,
            )
            self._worker_thread.start()

    def _worker_loop(self) -> None:
        """Background thread dequeuing envelopes and appending to JSONL streams."""
        while True:
            with self._lock:
                while not self._queue and self._accepting_events:
                    self._cv.wait(timeout=0.1)

                if not self._queue and not self._accepting_events:
                    break

                env = self._queue.pop(0)
                self._in_flight_env = env

            stream_name = "events"
            if env.event_type == "STATE_DELTA":
                stream_name = "state_deltas"
            elif env.event_type == "OBJECTIVE_EVALUATION":
                stream_name = "objective_traces"
            elif env.event_type == "NOTIFICATION":
                stream_name = "notification_traces"
            elif env.event_type == "TELEMETRY":
                stream_name = "telemetry"
            elif env.event_type == "USER_MARKER":
                stream_name = "markers"

            try:
                self.storage_manager.append_envelope(stream_name, env)
                with self._lock:
                    self.persisted_event_count += 1
                    self._in_flight_env = None
            except Exception as e:
                logger.error(f"Observer worker storage failure: {e}")
                with self._lock:
                    self._record_drop(
                        env.sequence_number,
                        is_high=(env.priority == EvidencePriority.HIGH),
                        event_id=env.event_id,
                    )
                    self._in_flight_env = None
                    self.health = ObserverHealth(
                        state=HealthState.FAILED,
                        last_error=str(e),
                        error_count=self.health.error_count + 1,
                    )
                    self._accepting_events = False
                return

    def _record_drop(self, seq_num: int, is_high: bool, event_id: str | None = None) -> None:
        """Record dropped event accounting."""
        self.dropped_event_count += 1
        if is_high:
            self.dropped_high_priority_count += 1
        if event_id:
            self.dropped_event_ids.add(event_id)
        if self.dropped_sequence_ranges and self.dropped_sequence_ranges[-1][1] == seq_num - 1:
            self.dropped_sequence_ranges[-1][1] = seq_num
        else:
            self.dropped_sequence_ranges.append([seq_num, seq_num])

    def _enqueue_with_priority_shedding(self, envelope: ObservationEnvelope) -> bool:
        """Enforce 3-tier priority shedding when queue capacity is saturated."""
        if len(self._queue) < self.queue_size:
            self._queue.append(envelope)
            self._queue_high_watermark = max(self._queue_high_watermark, len(self._queue))
            self._cv.notify()
            return True

        # Queue is full: find lowest priority item to shed
        # 1. Look for oldest LOW
        low_idx = next(
            (i for i, item in enumerate(self._queue) if item.priority == EvidencePriority.LOW),
            None,
        )
        if low_idx is not None:
            evicted = self._queue.pop(low_idx)
            self._record_drop(evicted.sequence_number, is_high=False, event_id=evicted.event_id)
            for i, q_item in enumerate(self._queue):
                if evicted.event_id in q_item.correlation_refs:
                    self._queue[i] = q_item.model_copy(update={"correlation_missing_due_to_backpressure": True})
            self._queue.append(envelope)
            self._queue_high_watermark = max(self._queue_high_watermark, len(self._queue))
            self._cv.notify()
            return True

        # 2. Look for oldest MEDIUM
        med_idx = next(
            (i for i, item in enumerate(self._queue) if item.priority == EvidencePriority.MEDIUM),
            None,
        )
        if med_idx is not None:
            evicted = self._queue.pop(med_idx)
            self._record_drop(evicted.sequence_number, is_high=False, event_id=evicted.event_id)
            for i, q_item in enumerate(self._queue):
                if evicted.event_id in q_item.correlation_refs:
                    self._queue[i] = q_item.model_copy(update={"correlation_missing_due_to_backpressure": True})
            self._queue.append(envelope)
            self._queue_high_watermark = max(self._queue_high_watermark, len(self._queue))
            self._cv.notify()
            return True

        # 3. All items in queue are HIGH
        if envelope.priority in (EvidencePriority.LOW, EvidencePriority.MEDIUM):
            # Incoming low/med dropped at boundary
            self._record_drop(envelope.sequence_number, is_high=False, event_id=envelope.event_id)
            return False

        # Incoming is HIGH: shed oldest HIGH
        evicted = self._queue.pop(0)
        self._record_drop(evicted.sequence_number, is_high=True, event_id=evicted.event_id)
        for i, q_item in enumerate(self._queue):
            if evicted.event_id in q_item.correlation_refs:
                self._queue[i] = q_item.model_copy(update={"correlation_missing_due_to_backpressure": True})
        self._queue.append(envelope)
        self._cv.notify()
        return True

    def emit_event(
        self,
        event_type: str,
        taxonomy: FactKind,
        priority: EvidencePriority = EvidencePriority.MEDIUM,
        payload: dict[str, Any] | None = None,
        correlation_refs: list[str] | None = None,
        source_ref: str | None = None,
        source_timestamp: str | None = None,
    ) -> ObservationEnvelope | None:
        """Enqueue an observation item wrapped in canonical envelope."""
        with self._lock:
            if self.health.state == HealthState.FAILED:
                self.sequence_high_watermark += 1
                self._record_drop(self.sequence_high_watermark, is_high=(priority == EvidencePriority.HIGH))
                return None

            if not self._accepting_events:
                return None

            self.sequence_high_watermark += 1
            seq = self.sequence_high_watermark

            has_dropped_parent = bool(
                correlation_refs and any(ref in self.dropped_event_ids for ref in correlation_refs)
            )

            env = ObservationEnvelope(
                schema_version="1.0",
                observation_session_id=self.session_id,
                sequence_number=seq,
                taxonomy=taxonomy,
                recorded_at=datetime.now(timezone.utc).isoformat(),
                source_timestamp=source_timestamp,
                event_type=event_type,
                source_ref=source_ref,
                correlation_refs=correlation_refs or [],
                correlation_missing_due_to_backpressure=has_dropped_parent,
                priority=priority,
                payload=payload or {},
            )

            self._enqueue_with_priority_shedding(env)
            return env

    def record_state_change(
        self,
        prev_state: CharacterState | None,
        curr_state: CharacterState,
        source: str = "state_reconciliation",
        correlation_refs: list[str] | None = None,
    ) -> list[StateDeltaRecord]:
        """Derive and record compact state deltas only when state fields actually change."""
        if prev_state is None:
            return []

        deltas: list[StateDeltaRecord] = []
        with self._lock:
            self._last_state_delta_ids = []

        fields_to_check = [
            "level",
            "character_class",
            "ascendancy",
            "current_zone",
            "current_act",
            "death_count",
            "equipped_weapon_set",
        ]

        for field_name in fields_to_check:
            curr_field = getattr(curr_state, field_name, None)
            prev_field = getattr(prev_state, field_name, None)

            curr_val = curr_field.value if hasattr(curr_field, "value") else curr_field
            prev_val = prev_field.value if hasattr(prev_field, "value") else prev_field

            if curr_val != prev_val:
                ver_status = (
                    curr_field.verification_state.value
                    if hasattr(curr_field, "verification_state")
                    else "UNKNOWN"
                )
                delta = StateDeltaRecord(
                    field=field_name,
                    before=prev_val,
                    after=curr_val,
                    source=source,
                    verification_status=ver_status,
                    evidence_refs=list(curr_field.evidence_refs) if hasattr(curr_field, "evidence_refs") else [],
                )
                deltas.append(delta)
                env = self.emit_event(
                    event_type="STATE_DELTA",
                    taxonomy=FactKind.DERIVED_FACT,
                    priority=EvidencePriority.HIGH,
                    payload=delta.model_dump(),
                    source_ref=source,
                    correlation_refs=correlation_refs,
                )
                if env:
                    with self._lock:
                        self._last_state_delta_ids.append(env.event_id)

        return deltas

    def record_objective_evaluation(
        self,
        triggers: list[str],
        state_delta_refs: list[str],
        candidate_ids: list[str],
        selected_objective_id: str | None,
        selection_reasons: list[str],
        suppressed_candidates: dict[str, str],
        objective_changed: bool,
    ) -> ObjectiveDecisionTrace:
        """Record objective decision trace without altering priority logic."""
        trace = ObjectiveDecisionTrace(
            triggers=triggers,
            state_delta_refs=state_delta_refs,
            candidate_ids=candidate_ids,
            selected_objective_id=selected_objective_id,
            selection_reasons=selection_reasons,
            suppressed_candidates=suppressed_candidates,
            objective_changed=objective_changed,
        )
        priority = EvidencePriority.HIGH if objective_changed else EvidencePriority.MEDIUM
        env = self.emit_event(
            event_type="OBJECTIVE_EVALUATION",
            taxonomy=FactKind.DERIVED_FACT,
            priority=priority,
            payload=trace.model_dump(),
            correlation_refs=state_delta_refs,
        )
        if env:
            with self._lock:
                self._last_objective_eval_id = env.event_id
        return trace

    def record_notification(
        self,
        notification_id: str,
        category: str,
        severity: str,
        safe_zone: bool,
        dispatch_status: str,
        queue_depth: int = 0,
        suppression_reason: str | None = None,
        cooldown_key: str | None = None,
        correlation_refs: list[str] | None = None,
    ) -> NotificationTraceRecord:
        """Record notification disposition outcome."""
        rec = NotificationTraceRecord(
            notification_id=notification_id,
            category=category,
            severity=severity,
            safe_zone=safe_zone,
            dispatch_status=dispatch_status,
            queue_depth=queue_depth,
            suppression_reason=suppression_reason,
            cooldown_key=cooldown_key,
        )
        self.emit_event(
            event_type="NOTIFICATION",
            taxonomy=FactKind.DERIVED_FACT,
            priority=EvidencePriority.MEDIUM,
            payload=rec.model_dump(),
            correlation_refs=correlation_refs,
        )
        return rec

    def trigger_screenshot(
        self,
        event_type: str,
        correlation_ref: str | None = None,
        is_shutdown: bool = False,
    ) -> ScreenshotRecord | None:
        """Trigger asynchronous screenshot capture if opt-in mode is active."""
        if self.screenshot_worker is None:
            return None

        rec = self.screenshot_worker.request_capture(
            trigger_event=event_type,
            correlation_ref=correlation_ref,
            is_shutdown=is_shutdown,
        )
        if self.screenshot_worker.degraded and self.health.state != HealthState.FAILED:
            self.health = ObserverHealth(
                state=HealthState.DEGRADED,
                last_error=rec.error_message or "Screenshot capture failure",
                error_count=self.health.error_count,
            )

        self.emit_event(
            event_type="SCREENSHOT",
            taxonomy=FactKind.OBSERVED_FACT,
            priority=EvidencePriority.LOW,
            payload=rec.model_dump(),
            correlation_refs=[correlation_ref] if correlation_ref else [],
        )
        return rec

    def record_telemetry(
        self,
        loop_duration_ms: float = 0.0,
        log_poll_latency_ms: float = 0.0,
        enqueue_latency_ms: float = 0.0,
        observer_queue_depth: int = 0,
        queue_high_watermark: int = 0,
        writer_latency_ms: float = 0.0,
        screenshot_capture_latency_ms: float = 0.0,
        storage_bytes: int = 0,
    ) -> OperationalTelemetryRecord:
        """Record periodic operational metrics."""
        rec = OperationalTelemetryRecord(
            loop_duration_ms=loop_duration_ms,
            log_poll_latency_ms=log_poll_latency_ms,
            enqueue_latency_ms=enqueue_latency_ms,
            observer_queue_depth=observer_queue_depth,
            queue_high_watermark=queue_high_watermark,
            dropped_event_count=self.dropped_event_count,
            dropped_high_priority_count=self.dropped_high_priority_count,
            writer_latency_ms=writer_latency_ms,
            screenshot_capture_latency_ms=screenshot_capture_latency_ms,
            worker_error_count=self.health.error_count,
            storage_bytes=storage_bytes,
        )
        self.emit_event(
            event_type="TELEMETRY",
            taxonomy=FactKind.DERIVED_FACT,
            priority=EvidencePriority.LOW,
            payload=rec.model_dump(),
        )
        return rec

    def record_unparsed_line(self, line: str) -> None:
        """Inspect and group an unrecognized log line under strict privacy bounds."""
        self.anomaly_grouper.record_line(line)

    def stop(self, timeout: float = DEFAULT_SHUTDOWN_TIMEOUT) -> SessionManifest:
        """Execute 9-step orderly bounded shutdown sequence and return final manifest."""
        self._is_stopped = True

        # Step 1 & 2: stop accepting new ordinary events and signal worker
        with self._lock:
            self._accepting_events = False
            self._cv.notify_all()

        # Step 3: Drain bounded queue within timeout
        start_wait = time.perf_counter()
        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

        elapsed = time.perf_counter() - start_wait
        timed_out = elapsed >= timeout and (self._worker_thread is not None and self._worker_thread.is_alive())

        # Step 4: Close streams
        self.storage_manager.close_streams()

        # Step 4.5: Persist anomalies
        try:
            import json
            anom_path = self.session_dir / "anomalies.json"
            anom_dict = {
                sig.pattern_hash: sig.model_dump()
                for sig in self.anomaly_grouper.get_signatures()
            }
            anom_path.write_text(json.dumps(anom_dict, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to persist anomalies on shutdown: {e}")

        # Step 5: Generate session summary
        try:
            from companion.observe.summary import SessionSummaryGenerator
            SessionSummaryGenerator(self.session_dir).generate()
        except Exception as e:
            logger.error(f"Failed to generate session summary on shutdown: {e}")

        # Step 6: Determine status and reconcile counters
        now_iso = datetime.now(timezone.utc).isoformat()

        # Calculate artifact / stream counts via public storage contract
        artifact_counts = self.storage_manager.get_artifact_counts()

        with self._lock:
            pending_count = len(self._queue) + (1 if self._in_flight_env is not None else 0)
            if timed_out or pending_count > 0:
                final_status = ManifestStatus.INCOMPLETE
                aborted_reason = "OBSERVER_DRAIN_TIMEOUT"
            elif self.health.state == HealthState.FAILED:
                final_status = ManifestStatus.INCOMPLETE
                aborted_reason = "WORKER_FAILURE"
            else:
                final_status = ManifestStatus.CLOSED
                aborted_reason = None

            manifest = SessionManifest(
                session_id=self.session_id,
                runtime_run_id=self.runtime_run_id,
                started_at=self._started_at,
                ended_at=now_iso,
                status=final_status,
                aborted_reason=aborted_reason,
                sequence_high_watermark=self.sequence_high_watermark,
                persisted_event_count=self.persisted_event_count,
                dropped_event_count=self.dropped_event_count,
                dropped_high_priority_count=self.dropped_high_priority_count,
                pending_event_count=pending_count,
                dropped_sequence_ranges=self.dropped_sequence_ranges,
                health_state=self.health.state,
                worker_error_count=self.health.error_count,
                artifact_counts=artifact_counts,
            )

        # Step 7 & 8: Atomically update manifest
        self.manifest_manager.save_atomic(manifest)
        return manifest
