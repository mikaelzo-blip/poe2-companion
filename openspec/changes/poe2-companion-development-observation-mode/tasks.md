# Tasks: Development Observation Mode

## 1. Domain Models, Evidence Envelope & Taxonomy

- [x] 1.1 Implement canonical `ObservationEnvelope` in `companion/observe/models.py` with `schema_version`, strictly monotonic uint64 `sequence_number`, unique UUID `event_id`, fact taxonomy, distinct `source_timestamp` and `recorded_at`, explicit `correlation_refs`, `correlation_missing_due_to_backpressure`, and structured payload, verified with serialization and monotonicity unit tests in `tests/test_observe_models.py`.
- [x] 1.2 Implement fact taxonomy (`FactKind`), health models (`ObserverHealth`, `HealthState` [HEALTHY, DEGRADED, FAILED]), evidence priority tiers (`EvidencePriority` [HIGH, MEDIUM, LOW]), and structured domain models (`StateDeltaRecord`, `ObjectiveDecisionTrace`, `NotificationTraceRecord`, `AnomalySignatureRecord`, `OperationalTelemetryRecord`, `UserMarkerRecord`, `ScreenshotRecord`, `ManifestStatus` [OPEN, CLOSED, INCOMPLETE, ABORTED]) in `companion/observe/models.py`, verified with validation tests in `tests/test_observe_models.py`.

## 2. Fail-Closed Privacy Filter & Anomaly Sanitizer

- [x] 2.1 Implement multi-stage `PrivacyFilter` in `companion/observe/privacy.py` enforcing chat channel rejection (`@From`, `@To`, `#`, `$`, `%`, `&`, `!`), credential/token stripping, approved debug envelope validation, and dynamic value sanitization, verified with test cases asserting zero chat or sensitive token leakage in `tests/test_observe_privacy.py`.
- [x] 2.2 Implement fail-closed withholding in `LogAnomalyGrouper` (`companion/observe/anomalies.py`) such that unparsed lines with uncertain safety classification withhold representative text, set `PRIVACY_SAMPLE_WITHHELD = true`, and persist only pattern hashes, counts, and timestamps, verified with ambiguous log tests in `tests/test_observe_privacy.py`.
- [x] 2.3 Implement signature cap (max 100 unique patterns) and sample cap (max 3 sanitized samples for approved envelopes) in `companion/observe/anomalies.py`, verified with unit tests asserting cap enforcement under high anomaly volumes.

## 3. Storage Architecture, Atomic Manifests & Global Boundary Retention

- [x] 3.1 Implement `ObservationStorageManager` in `companion/observe/storage.py` managing `runtime/observations/<session_id>/` layout, defense-in-depth `.gitignore` verification, and append-safe JSONL file rotation at 10 MB (max 5 segments per stream), verified with rotation unit tests in `tests/test_observe_storage.py`.
- [x] 3.2 Implement atomic `session_manifest.json` updates via `.tmp` rename in `companion/observe/manifest.py`, tracking `schema_version`, lifecycle status (`OPEN`, `CLOSED`, `INCOMPLETE`, `ABORTED`), high-watermark sequences, dropped event counts, dropped high-priority counts, and enforcing counter reconciliation (`persisted_event_count + dropped_event_count == sequence_high_watermark`), verified with reconciliation tests in `tests/test_observe_manifest.py`.
- [x] 3.3 Implement partial session recovery on startup in `ObservationStorageManager`, detecting unfinalized `OPEN` sessions, marking them `INCOMPLETE / ABORTED` with reason `UNEXPECTED_TERMINATION`, and preserving raw trace files for partial review, verified with crash simulation tests in `tests/test_observe_manifest.py`.
- [x] 3.4 Implement deterministic global retention manager in `companion/observe/retention.py` enforcing global storage quota at session start, session close, and CLI cleanup (never mid-tick), evicting oldest sessions while protecting active sessions, finalizing sessions, newly closed sessions, pinned sessions, and `docs/audits/` reports, verified with retention tests in `tests/test_observe_retention.py`.

## 4. Subordinate Core Observer, Backpressure & Tap Integration

- [x] 4.1 Implement `DevelopmentObserver` in `companion/observe/observer.py` with a small bounded queue (max 1000 items) and non-blocking enqueue, verifying that slow background writer lag never blocks runtime callbacks in `tests/test_observe_observer.py`.
- [x] 4.2 Implement deterministic 3-tier backpressure priority drop policy in `DevelopmentObserver`, shedding LOW evidence before MEDIUM before HIGH under queue saturation, incrementing `dropped_event_count` and `dropped_high_priority_count`, logging `OBSERVATION_BACKPRESSURE` metadata, and flagging downstream surviving records with `correlation_missing_due_to_backpressure`, verified in `tests/test_observe_observer.py`.
- [x] 4.3 Implement worker failure and degradation handling in `DevelopmentObserver`, verifying that fatal persistence worker exceptions transition health to `FAILED`, reject or discard incoming enqueues to prevent unbounded queue growth, and keep continuous runtime executing normally without infinite restart loops, verified in `tests/test_observe_observer.py`.
- [x] 4.4 Implement compact state delta derivation in `DevelopmentObserver`, verifying that no trace records are emitted on unchanged ticks and provenance/verification status is preserved, verified in `tests/test_observe_observer.py`.
- [x] 4.5 Implement objective decision tracing in `DevelopmentObserver`, capturing candidate evaluation, top objective selection, suppression rationales for UNKNOWN/STALE state, and stability comparison without changing priority logic, verified in `tests/test_observe_observer.py`.
- [x] 4.6 Implement notification outcome tracing in `DevelopmentObserver`, logging dispatches, severity, safe-zone context, and queue depth, verified in `tests/test_observe_observer.py`.
- [x] 4.7 Wire optional `ObservationTap` into `ContinuousRuntimeOrchestrator` (`companion/runtime/orchestrator.py`), verifying that when disabled, zero worker threads and zero storage I/O are created with only negligible branch check overhead, and when enabled, runtime correctness is unmodified, verified in `tests/test_observe_runtime_tap.py`.

## 5. Orderly Bounded Shutdown & Queue Drain

- [x] 5.1 Implement 9-step shutdown pipeline in `DevelopmentObserver` ensuring session is not marked `CLOSED` while queue has pending events: stop accepting new events, drain bounded queue, finalize/skip pending screenshots, flush/close JSONL streams, reconcile counters, write summaries, atomically update manifest, and transition status to `CLOSED`, verified in `tests/test_observe_shutdown.py`.
- [x] 5.2 Implement bounded shutdown timeout (5.0s) in `DevelopmentObserver`: abort drain upon timeout, transition manifest to `INCOMPLETE` with `OBSERVER_DRAIN_TIMEOUT`, accurately log pending and dropped counts, and unblock continuous runtime shutdown, verified in `tests/test_observe_shutdown.py`.

## 6. Atomic Marker Inbox & Async Screenshot Pipeline

- [x] 6.1 Implement atomic marker inbox writer and consumer in `companion/observe/markers.py`, using two-stage write (`<marker_id>.tmp` -> `<marker_id>.json`), concurrency-safe UUID filenames, ignoring incomplete `.tmp` files, and reporting inactive sessions honestly when no session is active, verified with concurrent execution tests in `tests/test_observe_markers.py`.
- [x] 6.2 Implement opt-in asynchronous screenshot capture worker in `companion/observe/screens.py` using MSS backend, enforcing monitor isolation, 30s cooldown, 50 screenshot quota, structured result records (`CAPTURED`, `SKIPPED_BUDGET`, `SKIPPED_COOLDOWN`, `SKIPPED_SHUTDOWN`, `CAPTURE_FAILED`), and independent degradation to `DEGRADED` health without state mutation, verified with unit tests in `tests/test_observe_screens.py`.

## 7. CLI Commands & Operational Telemetry

- [x] 7.1 Update CLI options in `companion/cli.py` to add `--observe-dev`, `--observe-screens`, and display selection to `companion runtime start`, verified via CLI argument parsing tests in `tests/test_cli_runtime.py`.
- [x] 7.2 Add `companion observe` CLI subcommand group (`mark`, `status`, `summary`, `review`, `cleanup`) in `companion/cli.py`, verified with CLI execution tests in `tests/test_cli_observe.py`.
- [x] 7.3 Implement periodic operational telemetry flushes in `ContinuousRuntimeOrchestrator` and `DevelopmentObserver`, tracking loop duration, log poll latency, enqueue latency, queue depth, writer latency, capture latency, and dropped event counts using monotonic timers, verified in `tests/test_observe_telemetry.py`.

## 8. Post-Session Analysis, Hermes Review & Partial Recovery

- [x] 8.1 Implement `SessionSummaryGenerator` in `companion/observe/summary.py` supporting clean, partial, and timed-out sessions, computing aggregate statistics, flagging review candidate categories (`PARSER_GAP_CANDIDATE`, `OBJECTIVE_USEFULNESS_REVIEW`, `NOTIFICATION_SPAM_CANDIDATE`, etc.), and writing `session_summary.json` and `session_summary.md`, verified with mock session datasets in `tests/test_observe_summary.py`.
- [x] 8.2 Implement `companion observe review` command producing `DEVELOPMENT_OBSERVATION_REPORT.md` adhering to the 6-section taxonomy with evidence quality rules (concrete event ID citations, occurrence counts, time windows, corroboration, missing parent evidence under `MISSING_EVIDENCE`, and classifying single weak anomalies as `NOT ENOUGH EVIDENCE`), verified in `tests/test_observe_review.py`.

## 9. Comprehensive Verification Suite & Live Gameplay Soak

- [x] 9.1 Implement comprehensive deterministic unit and integration test suite in `tests/test_observe_suite.py` asserting:
  - Session is not `CLOSED` while observer queue still has pending events.
  - Successful bounded drain produces `CLOSED`.
  - Drain timeout produces `INCOMPLETE` with `OBSERVER_DRAIN_TIMEOUT` without blocking continuous runtime shutdown.
  - Fatal observer writer failure transitions health to `FAILED` and caps queue without crashing runtime.
  - Screenshot worker failure transitions health to `DEGRADED` without corrupting state or halting event logging.
  - Deterministic priority shedding drops `LOW` before `MEDIUM` before `HIGH`, and dropped `HIGH` is reported honestly.
  - Surviving child correlation records flag missing dropped parents under `MISSING_EVIDENCE`.
  - Sequence gaps caused by drops are accounted for in manifest reconciliation (`persisted + dropped == sequence_high_watermark`).
  - Active sessions, finalizing sessions, and newly closed sessions are protected from retention eviction during close.
  - Incomplete `.tmp` marker files are ignored and concurrent marker submissions succeed without collision.
  - Ambiguous unparsed lines withhold representative text (`PRIVACY_SAMPLE_WITHHELD = true`).
- [x] 9.2 Implement compliance test in `tests/test_observe_compliance.py` asserting zero input injection (`NoInputGuard`), zero runtime behavior divergence when observer is disabled, and git status isolation.
- [x] 9.3 Prepare live play soak test protocol in `docs/audits/live_observation_guide.md` specifying the 60-120 minute real play acceptance protocol, recording queue watermark, dropped counts, storage growth, CPU/memory qualitative observations, verifying clean shutdown drain, queue emptiness, sequence watermark reconciliation, and reporting unobserved events as `NOT OBSERVED`.
