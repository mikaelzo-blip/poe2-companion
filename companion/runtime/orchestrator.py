"""Continuous foreground runtime orchestrator coordinating sensing, state, and objectives."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import signal
import sys
import time
from types import FrameType
from typing import Any
import uuid

from companion.notifications.schema import (
    NotificationCategory,
    NotificationPayload,
    NotificationSeverity,
)
from companion.notifications.sinks import ConsoleSink
from companion.objectives.runner import (
    run_objective_pipeline,
    save_current_objective_artifact,
)
from companion.recap.generator import generate_session_recap
from companion.runtime.change_tracker import StateChangeTracker
from companion.runtime.checkpoint import (
    FileIdentityClassification,
    RuntimeCheckpointStore,
    classify_file_identity,
    generate_file_fingerprint,
)
from companion.runtime.lease import WriterLeaseManager
from companion.runtime.lifecycle import SessionLifecycleManager
from companion.runtime.models import (
    FileFingerprint,
    RuntimeCheckpoint,
    RuntimeConfig,
    RuntimeStatus,
    SessionLifecycleState,
)
from companion.runtime.normalizer import (
    build_observation_id,
    build_source_stream_id,
    normalize_log_event,
)
from companion.runtime.notifications import RuntimeNotificationManager
from companion.runtime.observability import RuntimeConsoleFormatter
from companion.sensing.client_log import parse_log_line
from companion.sensing.process_presence import ProcessMonitor, ProcessState
from companion.state.history import JourneyHistoryLogger
from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.reconciliation import reconcile_observation
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore

logger = logging.getLogger(__name__)


class ContinuousRuntimeOrchestrator:
    """Continuous foreground loop coordinating process, log streaming, state, and objectives."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.runtime_dir = Path(config.runtime_dir)
        self.run_id = uuid.uuid4().hex

        self.lease_manager = WriterLeaseManager(self.runtime_dir)
        self.checkpoint_store = RuntimeCheckpointStore(self.runtime_dir / "session_checkpoint.json")
        self.status_file = self.runtime_dir / "runtime_status.json"
        self.lifecycle_manager = SessionLifecycleManager()
        self.process_monitor = ProcessMonitor()
        self.change_tracker = StateChangeTracker()
        self.notification_manager = RuntimeNotificationManager(
            sinks=[ConsoleSink()],
            suppress_notifications=config.backfill,
        )
        self.history_logger = JourneyHistoryLogger(self.runtime_dir / "journey_history.jsonl")
        self.state_store = CharacterStateStore(self.runtime_dir)
        self.console = RuntimeConsoleFormatter(verbose=config.verbose)

        self.current_offset: int = 0
        self.stream_epoch: int = 1
        self.source_stream_id: str = ""
        self.is_crash_recovery: bool = False
        self.is_backfill_mode: bool = config.backfill
        self.startup_backfill_end_offset: int = 0
        self._shutdown_requested: bool = False
        self._active_character: CharacterState | None = None
        self._started_at_iso = datetime.now(timezone.utc).isoformat()

    @property
    def client_log_path(self) -> Path:
        return self.config.client_log_path or Path("Client.txt")

    def initialize_startup(self) -> None:
        """Resolve startup boundary, acquire lifetime writer lock, and persist dirty checkpoint."""
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

        # 1. Acquire lifetime writer lock
        self.lease_manager.acquire(self.run_id, self.config.character_id)

        # 2. Load active character
        if self.config.character_id:
            try:
                self._active_character = self.state_store.load_character(self.config.character_id)
            except Exception:
                self._active_character = None
        if self._active_character is None:
            self._active_character = self.state_store.get_active_character()
        if self._active_character is None:
            # Create synthetic default character state for observation tracking
            self._active_character = CharacterState.create_initial("UNKNOWN", "UNKNOWN")

        # 3. Load existing checkpoint
        existing_cp = self.checkpoint_store.load()
        log_path = self.client_log_path
        file_size = log_path.stat().st_size if log_path.exists() else 0

        # 4. Resolve boundary
        if self.config.backfill:
            self.is_backfill_mode = True
            self.startup_backfill_end_offset = file_size
            self.current_offset = 0
            self.stream_epoch = existing_cp.stream_epoch if existing_cp else 1
            self.notification_manager.suppress_notifications = True
            self.console.log(
                self.console.format_backfill(
                    f"Catching up historical log (0 -> {self.startup_backfill_end_offset} bytes)..."
                )
            )
        else:
            if existing_cp is not None and not existing_cp.clean_shutdown:
                # Crash recovery
                self.is_crash_recovery = True
                decision = classify_file_identity(log_path, existing_cp)
                self.current_offset = decision.read_offset
                self.stream_epoch = decision.stream_epoch
                self.console.log(
                    self.console.format_crash_recovery(
                        f"Unclean shutdown detected. Resuming from checkpoint offset {self.current_offset} (epoch {self.stream_epoch}) with at-least-once replay."
                    )
                )
            else:
                # Clean restart or initial start
                p_trans = self.process_monitor.poll()
                if p_trans.current_state == ProcessState.RUNNING:
                    self.current_offset = file_size
                    self.stream_epoch = existing_cp.stream_epoch if existing_cp else 1
                    gap = file_size - (existing_cp.last_offset if existing_cp else 0)
                    self.console.log(
                        self.console.format_session(
                            f"PoE2 already running after clean shutdown. Seeking to current EOF ({file_size}); {gap} bytes of offline backlog skipped to prevent alert storms."
                        )
                    )
                else:
                    self.current_offset = file_size
                    self.stream_epoch = existing_cp.stream_epoch if existing_cp else 1
                    self.console.log(
                        self.console.format_session(
                            f"Idle. Waiting for PoE2 process... (baseline log offset: {file_size}, epoch: {self.stream_epoch})"
                        )
                    )

        # 5. Establish source stream identity
        fp = generate_file_fingerprint(log_path)
        p_hash = fp.prefix_hash if fp else "init"
        self.source_stream_id = build_source_stream_id(p_hash, self.stream_epoch)

        # 6. Dirty-on-start persistence BEFORE any log consumption
        self.checkpoint_store.initialize_dirty_checkpoint(
            log_path,
            existing_checkpoint=existing_cp,
            run_id=self.run_id,
            start_offset=self.current_offset,
            stream_epoch=self.stream_epoch,
        )

        self._publish_status()

    def poll_tick(self) -> None:
        """Execute one complete poll cycle."""
        # 1. Update diagnostic telemetry
        self.lease_manager.heartbeat()
        self._publish_status()

        # 2. Process presence poll
        transition = self.process_monitor.poll()
        if transition.is_transition:
            self.lifecycle_manager.handle_process_transition(transition)
            if transition.current_state == ProcessState.RUNNING:
                proc_info = transition.process_info
                pid = proc_info.pid if proc_info else "?"
                self.console.log(self.console.format_session(f"PoE2 detected running (PID: {pid})"))
            elif transition.current_state == ProcessState.TERMINATED:
                self.console.log(
                    self.console.format_session(
                        "PoE2 process termination detected. Executing bounded final log drain..."
                    )
                )
                self._drain_and_finalize_session()
                return

        # 3. Read log batch
        self._consume_log_batch()

    def _consume_log_batch(self, max_lines: int = 500) -> int:
        """Read and process newly appended lines from Client.txt in strictly read-only mode."""
        log_path = self.client_log_path
        if not log_path.exists():
            return 0

        try:
            current_file_size = log_path.stat().st_size
        except OSError:
            return 0

        # Handle log file identity checks (e.g. truncation in-place)
        if current_file_size < self.current_offset:
            self.stream_epoch += 1
            fp = generate_file_fingerprint(log_path)
            p_hash = fp.prefix_hash if fp else "init"
            self.source_stream_id = build_source_stream_id(p_hash, self.stream_epoch)
            self.current_offset = 0

        if current_file_size <= self.current_offset:
            return 0

        lines_read = 0
        consumed_offset = self.current_offset
        previous_char_state = self._active_character.model_copy(deep=True) if self._active_character else None

        try:
            with open(log_path, "rb") as f:
                f.seek(self.current_offset)
                while lines_read < max_lines:
                    line_start = f.tell()
                    line_bytes = f.readline()
                    if not line_bytes:
                        break
                    if not line_bytes.endswith(b"\n"):
                        # Incomplete line; do not advance past start of line
                        f.seek(line_start)
                        break

                    line_end = f.tell()
                    consumed_offset = line_end
                    lines_read += 1

                    line_str = line_bytes.decode("utf-8", errors="replace")
                    parsed = parse_log_line(line_str)
                    if parsed is not None:
                        char_id = self._active_character.character_id if self._active_character else None
                        obs_event = normalize_log_event(
                            parsed_event=parsed,
                            source_stream_id=self.source_stream_id,
                            start_offset=line_start,
                            end_offset=line_end,
                            character_id=char_id,
                        )

                        # Check backfill transition boundary
                        if self.is_backfill_mode and line_end >= self.startup_backfill_end_offset:
                            self.is_backfill_mode = False
                            self.notification_manager.suppress_notifications = False
                            self.console.log(
                                self.console.format_backfill(
                                    f"Historical catch-up complete at offset {self.startup_backfill_end_offset}. Transitioning to LIVE mode."
                                )
                            )

                        # Update lifecycle
                        self.lifecycle_manager.handle_observation(obs_event)

                        # Reconcile character state
                        if self._active_character is not None:
                            self._active_character = reconcile_observation(self._active_character, obs_event)

                        # Deduplicated journey history append
                        self.history_logger.record_event(obs_event)

                        # Observability logging
                        if parsed.event_type.value == "level_up":
                            cname = parsed.payload.get("character_name", "Character")
                            lvl = parsed.payload.get("level", 1)
                            self.console.log(self.console.format_level(cname, lvl))
                        elif parsed.event_type.value in ("zone_enter", "zone_generate"):
                            zname = parsed.payload.get("zone", "Unknown")
                            is_safe = self.notification_manager._policy.is_safe_zone(zname)
                            self.console.log(self.console.format_zone(zname, is_safe=is_safe))
                            # Safe zone flush
                            if is_safe:
                                flushed = self.notification_manager.on_zone_entered(zname)
                                for alert in flushed:
                                    self.console.log(self.console.format_notify(f"[FLUSH] {alert.title}: {alert.message}"))

        except (OSError, PermissionError) as e:
            logger.warning(f"Transient log read error: {e}")
            return 0

        self.current_offset = consumed_offset

        # Consolidated state change derivation
        if lines_read > 0 and self._active_character is not None:
            self.change_tracker.compute_delta(previous_char_state, self._active_character)
            if self.change_tracker.should_reevaluate_objectives():
                try:
                    obj_result = run_objective_pipeline(self._active_character)
                    save_current_objective_artifact(
                        obj_result, self.runtime_dir / "CURRENT_OBJECTIVE.json"
                    )
                    top_obj = obj_result.primary_objective
                    if top_obj is not None:
                        self.console.log(self.console.format_objective(top_obj.title))
                        payload = NotificationPayload.create(
                            title=top_obj.title,
                            message=top_obj.action or top_obj.rationale,
                            severity=NotificationSeverity.INFO,
                            category=NotificationCategory.OPTIMIZATION,
                            dedupe_key=f"objective:{top_obj.id}",
                        )
                        current_zone = (
                            self._active_character.current_zone.value
                            if self._active_character.current_zone
                            else None
                        )
                        dispatch_status = self.notification_manager.dispatch(payload, current_zone)
                        if dispatch_status == "DELIVERED":
                            self.console.log(self.console.format_notify(f"{payload.title}: {payload.message}"))
                except Exception as e:
                    logger.warning(f"Objective evaluation error: {e}")

            # PERSISTENCE SEQUENCING:
            # 1. State Store
            self.state_store.save_character(self._active_character)

            # 2. Checkpoint Store
            fp = generate_file_fingerprint(log_path)
            if fp is None:
                fp = FileFingerprint(
                    path=str(log_path.resolve()),
                    created_at=0.0,
                    prefix_hash="",
                    file_size_at_fingerprint=0,
                )
            cp = RuntimeCheckpoint(
                schema_version="1.0",
                file_fingerprint=fp,
                stream_epoch=self.stream_epoch,
                last_offset=self.current_offset,
                last_file_size=current_file_size,
                updated_at=datetime.now(timezone.utc).isoformat(),
                clean_shutdown=False,
                clean_shutdown_at=None,
                run_id=self.run_id,
            )
            self.checkpoint_store.save(cp)
            self.change_tracker.clear()

        return lines_read

    def _drain_and_finalize_session(self) -> None:
        """Execute bounded final drain, produce session recap, and return lifecycle to IDLE."""
        # Bounded drain: read remaining complete lines
        self._consume_log_batch(max_lines=500)

        # Session recap callback
        def _produce_recap(session_id: str, started_at: datetime | None) -> None:
            entries = self.history_logger.read_history()
            try:
                generate_session_recap(entries, session_id=session_id)
                self.console.log(self.console.format_session(f"Session {session_id} finalized."))
            except Exception:
                pass

        self.lifecycle_manager.finalize_session(recap_callback=_produce_recap)

        # Durable flush
        if self._active_character is not None:
            self.state_store.save_character(self._active_character)

        fp = generate_file_fingerprint(self.client_log_path)
        if fp is None:
            fp = FileFingerprint(
                path=str(self.client_log_path.resolve()),
                created_at=0.0,
                prefix_hash="",
                file_size_at_fingerprint=0,
            )
        cp = RuntimeCheckpoint(
            file_fingerprint=fp,
            stream_epoch=self.stream_epoch,
            last_offset=self.current_offset,
            last_file_size=fp.file_size_at_fingerprint,
            updated_at=datetime.now(timezone.utc).isoformat(),
            clean_shutdown=False,
            run_id=self.run_id,
        )
        self.checkpoint_store.save(cp)

    def shutdown(self) -> None:
        """Graceful shutdown: drain, flush state/history, save clean checkpoint, release lock."""
        self._shutdown_requested = True
        self.console.log(self.console.format_session("Graceful shutdown requested. Finalizing..."))

        # Bounded drain
        self._consume_log_batch(max_lines=500)

        # Persist character state
        if self._active_character is not None:
            try:
                self.state_store.save_character(self._active_character)
            except Exception as e:
                logger.error(f"Error persisting state on shutdown: {e}")

        # Checkpoint clean shutdown
        log_path = self.client_log_path
        fp = generate_file_fingerprint(log_path)
        if fp is None:
            fp = FileFingerprint(
                path=str(log_path.resolve()),
                created_at=0.0,
                prefix_hash="",
                file_size_at_fingerprint=0,
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        cp = RuntimeCheckpoint(
            file_fingerprint=fp,
            stream_epoch=self.stream_epoch,
            last_offset=self.current_offset,
            last_file_size=fp.file_size_at_fingerprint,
            updated_at=now_iso,
            clean_shutdown=True,
            clean_shutdown_at=now_iso,
            run_id=self.run_id,
        )
        self.checkpoint_store.save(cp)

        # Release lifetime OS writer lock
        self.lease_manager.release()
        self._publish_status(exited=True)
        self.console.log(self.console.format_session("Shutdown complete. Writer lock released."))

    def _publish_status(self, exited: bool = False) -> None:
        """Write atomic status file for cross-process inspection."""
        state = SessionLifecycleState.IDLE if exited else self.lifecycle_manager.state
        char_id = self._active_character.character_id if self._active_character else None
        proc = self.process_monitor.active_process

        status = RuntimeStatus(
            runtime_pid=os.getpid(),
            lifecycle_state=state,
            session_id=self.lifecycle_manager.session_id,
            game_process_running=(proc is not None),
            game_pid=proc.pid if proc else None,
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
            last_consumed_offset=self.current_offset,
            active_character_id=char_id,
            started_at=self._started_at_iso,
        )
        try:
            self.status_file.write_text(status.model_dump_json(indent=2), encoding="utf-8")
        except OSError:
            pass

    def run_forever(self) -> None:
        """Run continuous foreground loop until interrupted."""
        self.initialize_startup()

        # Signal handlers
        def _handle_signal(signum: int, frame: FrameType | None) -> None:
            self._shutdown_requested = True

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        try:
            while not self._shutdown_requested:
                self.poll_tick()
                interval = self.config.poll_interval
                # Backoff slightly if idle
                if self.lifecycle_manager.state == SessionLifecycleState.IDLE:
                    interval = max(interval, 2.0)
                time.sleep(interval)
        finally:
            self.shutdown()
