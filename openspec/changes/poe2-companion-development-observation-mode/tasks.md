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
- [x] 9.3 Prepare live play observation acceptance protocol in `docs/audits/live_observation_guide.md` specifying one continuous >=30-minute real observation, with a separate optional 60–120-minute endurance/stability soak; record queue watermark, dropped counts, storage growth when measured, CPU/memory observations when measured, clean shutdown drain, queue emptiness, sequence watermark reconciliation, privacy and locality checks. Classify naturally unobserved gameplay events as `NOT OBSERVED`, independently of technical observer acceptance and feature-specific evidence sufficiency.

## 10. Incremental JSONL Stream Reader & Durable Rotation Cursor

- [x] 10.1 Implement `IncrementalStreamReader` in `companion/observe/reader.py` with multi-stream sequence accounting across typed streams (`events`, `state_deltas`, `objective_traces`, `notification_traces`, `telemetry`, `markers`), distinguishing physical per-stream read positions (`byte_offset`, `last_processed_sequence`) from the global contiguous analyzed frontier (`contiguous_frontier`), persisting compact `accounted_ahead_ranges` (`[[start, end], ...]`) in `reader_state.json` for crash-safe read-ahead reconstruction, implementing deterministic `seen_ahead` capacity saturation policy (max 1000 ahead sequences: stopping read-ahead on ahead streams, keeping safe frontier unchanged, waiting for frontier+1 / slower stream / durable drop metadata, exposing `ANALYST_READ_AHEAD_SATURATED`, never dropping sequence knowledge, pausing only local analyzer without blocking `ContinuousRuntimeOrchestrator` or `DevelopmentObserver`, and clearing saturation when missing sequence arrives), complete newline record boundary validation (never failing on partial trailing lines), sequential multi-segment rotation traversal (`events.jsonl` -> `events.1.jsonl`), sequence continuity validation without whole-file hashing, and explicit gap semantics (temporarily unread holds frontier, explicitly dropped sequences accounted via durable manifest `dropped_sequence_ranges` or drop tombstones, duplicate sequences deduplicated, `ANALYST_STREAM_GAP` on missing or ambiguous segments halts frontier and reports degraded gap state), verified with reader crash tests (Stream A ahead, Stream B missing frontier+1, crash/restart with ahead state preserved; physical cursor ahead of frontier reconstructs/replays; capacity saturation pauses reading safely without discarding evidence; missing sequence clears saturation and advances frontier; saturation does not affect continuous runtime or observer), rotation, partial-line, gap, multi-stream interleaved, and continuity unit tests in `tests/test_observe_reader.py`.
- [x] 10.2 Implement decoupled dual cursor managers in `companion/observe/cursor.py`: local reader cursor (`reader_cursor` in `reader_state.json` tracking `contiguous_frontier`, `accounted_ahead_ranges`, and `read_ahead_saturated`) and Hermes review cursor (`review_cursor` in `hermes_review_cursor.json` tracking `review_contiguous_frontier`) with independent atomic updates, crash recovery, contiguous sequence frontier tracking, and distinct contiguous lag calculations (`reader_lag = observer_sequence - reader_contiguous_frontier`, `review_lag = reader_contiguous_frontier - review_contiguous_frontier`, never using maximum-seen sequence for lag), verified with crash/restart simulation tests in `tests/test_observe_cursor.py`.

## 11. Local Live Analysis Data Plane & Live Journaling

- [x] 11.1 Implement local live analysis data plane and deterministic factual signal generation in `companion/observe/analyst.py`: at-least-once input and idempotent derived output pipeline, deriving deterministic `local_signal_id` (`signal_type + source_event_ids_or_range + session_id`), UNKNOWN duration tracking, objective churn detection, notification queuing analysis, anomaly repetition counting, and correlation index maintenance, emitting structured observations to `local_signals.jsonl` without autonomous defect or opportunity classification, asserting that replay after crash does not create duplicate logical signals and persistence failure preserves cursor position, verified with factual signal unit tests in `tests/test_observe_analyst.py`.
- [x] 11.2 Implement Hermes finding models, lifecycle state machine (`WATCHING` -> `POSSIBLE_PATTERN` -> `CORROBORATED` -> `LIKELY_DEFECT` / `USABILITY_SIGNAL` / `DATA_GAP` / `NOT_ENOUGH_EVIDENCE`), deterministic review batch identity, durable review batch results, and finding revision idempotency in `companion/observe/journal.py`:
  - Compute deterministic `review_batch_id` before AI invocation (`hash(session_id + contiguous_start_sequence + contiguous_end_sequence + ordered source evidence IDs)`), independent of model-generated text.
  - Durably persist structured review batch result to `live_analysis/review_batches/<review_batch_id>.json` written atomically before advancing `review_cursor` (recording sequence bounds, evidence IDs, finding operations [CREATE, UPDATE, NO_FINDING], canonical finding keys, timestamp, and review status, without hidden chain-of-thought).
  - Implement replay semantics: on resume, if completed `<review_batch_id>.json` exists, skip AI re-invocation, replay structured result idempotently, and advance `review_cursor`.
  - Implement finding revision idempotency: each finding revision remembers source `review_batch_id` in `applied_review_batch_ids`; applying the same `review_batch_id` twice produces zero duplicate revisions, no increment to `occurrence_count`, and no duplicate `evidence_refs`.
  - Implement two-part finding identity architecture: (1) stable logical finding identity (`finding_id = f"find:{session_id}:{category}:{semantic_issue_key}"`) derived from session ID, category, and normalized subject / semantic issue key (e.g. `notification:late-delivery:<key>`, `unknown-persistence:<field>`, `objective-churn:<key>`, `parser-gap:<sig>`), and (2) mutable/growing evidence set and revisions (appending `evidence_refs`, updating `occurrence_count`, evolving status, and updating corroboration notes without changing `finding_id`).
  - Handle 4 failure/crash recovery cases (Case A: provider fails before batch result -> retry; Case B: batch result exists, crash before findings -> apply without AI call; Case C: findings journaled, crash before cursor -> catch up without duplicate revision; Case D: NO_FINDING batch advances cursor safely).
  - Verified with journal serialization, evolution, replay idempotency, batch result persistence, and redaction tests in `tests/test_observe_journal.py`.

## 12. Real-Time Marker Prioritization & Multi-Tier Live Status CLI

- [x] 12.1 Implement high-priority marker escalation across AI availability in `companion/observe/analyst.py`: prompt detection of persisted markers in `markers.jsonl`, causal correlation with upstream evidence, offline queueing of pending markers in `reader_state.json`, and prioritization of pending markers upon Hermes resume, verified with marker escalation tests in `tests/test_observe_analyst.py`.
- [x] 12.2 Add multi-tier `companion observe live-status` (and `companion observe status --live`) command in `companion/cli.py` clearly separating OBSERVATION, LOCAL ANALYSIS, and HERMES REVIEW layers, reporting observer sequence, reader contiguous sequence, review contiguous sequence, reader lag (`observer - reader_contiguous_frontier`), review lag (`reader_contiguous_frontier - review_contiguous_frontier`) based strictly on contiguous frontiers, reader saturation state (`ANALYST_READ_AHEAD_SATURATED`), review batch counts (completed and pending), and integrating `hermes_review_status.json` heartbeat telemetry (reporting `ACTIVE` for fresh heartbeat, `OFFLINE / INACTIVE / STALE` for stale heartbeat or offline reviewer, never inferring active from cursor file alone), verified via CLI tests in `tests/test_cli_observe_live.py`.
- [x] 12.3 Add incremental local step command `companion observe analyze-live [--session <id>] [--max-events <n>]` in `companion/cli.py` providing deterministic local data plane execution and crash recovery independently of AI availability, verified with CLI tests in `tests/test_cli_observe_live.py`.

## 13. Safety Invariants, Comprehensive Test Suite & Live Acceptance Protocol

- [x] 13.1 Implement live analysis privacy redaction and bounded raw reading checks in `companion/observe/analyst.py`, verifying zero leakage of whispers, private chat, credentials, or tokens into findings, and asserting bounded `Client.txt` window reads without full-file rescans, verified in `tests/test_observe_analyst_privacy.py`.
- [x] 13.2 Implement comprehensive live integration tests in `tests/test_observe_live_integration.py` asserting:
  - Reader Crash Safety & Saturation:
    - Stream A read ahead, Stream B missing frontier+1, crash, restart: no ahead evidence lost.
    - Per-stream physical cursor ahead of global frontier: restart reconstructs/replays safely.
    - `seen_ahead` reaches capacity: reader pauses safely (`ANALYST_READ_AHEAD_SATURATED`) rather than dropping sequence knowledge.
    - Missing sequence later arrives: frontier advances through retained ahead range and clears saturation.
    - Saturation does not affect `ContinuousRuntimeOrchestrator` or `DevelopmentObserver`.
    - No evidence is silently discarded.
  - Review Batch Idempotency & Failure Cases:
    - Deterministic `review_batch_id` computed for identical evidence.
    - Case A: Provider failure before batch persistence retries review cleanly.
    - Case B: Batch persisted then crash before finding application completes resumes from batch result without re-invoking AI.
    - Case C: Finding application completed then crash before cursor does NOT invoke AI twice, does not duplicate revision, and does not double occurrence counts or evidence refs.
    - Case D: `NO_FINDING` batch resumes without repeated AI review and advances cursor safely.
    - New evidence creates new batch and evolves existing finding once (`revision += 1`).
  - Findings: same semantic finding + new evidence keeps same finding ID; exact review replay does not emit duplicate finding; unrelated semantic issue gets different finding ID; finding lifecycle evolution (e.g. `WATCHING` -> `CORROBORATED`) preserves finding ID.
  - Reader Frontier: sequences 1, 2, 4, 5 with missing 3 holds reader frontier at 2; arrival of missing sequence 3 advances frontier through 5; highest seen sequence never substitutes for contiguous frontier; duplicate sequence does not corrupt frontier; explicit durable dropped sequence accounted via manifest `dropped_sequence_ranges` advances frontier; `ANALYST_STREAM_GAP` prevents frontier advancement.
  - Multi-Stream Accounting: faster stream reaching later sequence cannot cause slower stream evidence to be skipped; canonical frontier accounting mechanism behaves deterministically across interleaved typed streams.
  - Review Frontier: reviewed sequences 1..100 and 102..120 with sequence 101 pending holds review cursor at 100; once sequence 101 review completes, review cursor advances through 120; crash/replay preserves review frontier and does not duplicate logical findings.
  - Local Reader Crash Consistency: output persisted then crash before cursor advance replayed without duplicate logical signal; output persistence failure holds cursor; stream gap holds cursor; incomplete line holds cursor.
  - Status & Heartbeat: fresh review heartbeat reports `ACTIVE`; stale heartbeat (>30s) reports `STALE/OFFLINE`; cursor file existence alone does NOT imply `ACTIVE`; provider failure updates status without affecting runtime or local reader.
  - Lag Reporting: `observer_latest_sequence`, `reader_latest_sequence`, `reader_lag`, `hermes_reviewed_sequence`, and `review_lag` calculate accurately and separately using contiguous frontiers, never maximum-seen sequences.
  - Markers: `mark` uses atomic marker inbox (`.tmp` -> `.json`), persisted marker evidence reaches live analyst, Hermes offline does not lose markers, and pending markers are reviewed after resume.
- [x] 13.3 Update live gameplay observation acceptance protocol in `docs/audits/live_observation_guide.md` specifying future acceptance requirements executed WHILE GAME IS STILL RUNNING:
  1. Observer evidence sequence advances
  2. Local incremental reader advances and can temporarily lag safely
  3. Review batch result exists before review cursor advances
  4. Hermes reviews at least one batch while game is running
  5. Review cursor advances only after durable review output/accounting
  6. User creates a marker via atomic inbox
  7. Marker appears in persisted observation evidence
  8. Hermes reviews/correlates that marker while game is running if Hermes is active
  9. Intentionally interrupt Hermes/provider after one completed review batch
  10. Continuous runtime and observer continue running completely unaffected
  11. New evidence accumulates while Hermes is stopped
  12. Local reader continues indexing new evidence
  13. Restart/resume Hermes
  14. Verify already completed review batch is not re-reviewed unnecessarily
  15. Verify no duplicate logical finding or revision upon resume
  16. Pending evidence and offline marker are reviewed (marker prioritized on resume)
  17. New evidence after resume produces a new review batch normally
  18. Hermes advances from review cursor
  19. Live status accurately reflects `ACTIVE` vs `OFFLINE`, saturation state, batch counts, and both lag values
  Confirming that the 30-minute rule remains solely the dataset acceptance duration threshold and not an analysis delay.
