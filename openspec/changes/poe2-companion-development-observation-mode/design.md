# Design: Development Observation Mode

## Context

The Path of Exile 2 Companion continuous runtime (`companion runtime start`) coordinates game process sensing (`ProcessMonitor`), log streaming (`parse_log_line`), state reconciliation (`reconcile_observation`), single-writer persistence (`CharacterStateStore`), and objective generation (`run_objective_pipeline`). All runtime components operate under an OS file-backed writer lease (`WriterLeaseManager`) in `runtime/`.

Currently, identifying gaps in sensing (such as DEF-01 unparsed log formats), objective evaluation churn, and notification cadence requires manual reproduction or ad-hoc log review. To enable rapid, evidence-grounded evolution of companion capabilities, we need a mechanism to gather development telemetry during actual play sessions without altering runtime semantics, violating game automation rules, or compromising privacy.

See `proposal.md` for problem motivation and `specs/development-observation/spec.md` for behavioral requirements.

## Goals / Non-Goals

**Goals:**
- Provide a clean, read-only observation tap (`DevelopmentObserver`) that consumes events from `ContinuousRuntimeOrchestrator` without competing with or duplicating existing sensing, state reconciliation, or objective engines.
- Ensure the observer is strictly subordinate to continuous runtime correctness: use a bounded asynchronous pipeline so observation I/O never blocks or crashes runtime loops.
- Guarantee orderly bounded shutdown: drain pending queue evidence within a strict timeout (5.0s) before marking status `CLOSED`, or transition to `INCOMPLETE` with `OBSERVER_DRAIN_TIMEOUT` if timeout elapses, never blocking runtime termination indefinitely.
- Track explicit observer health states (`HEALTHY`, `DEGRADED`, `FAILED`) and isolate worker failures so runtime execution continues unaffected without unbounded queue accumulation or endless restart loops.
- Implement a deterministic 3-tier priority drop policy (`HIGH`, `MEDIUM`, `LOW`) under backpressure, preserving critical state and error evidence while honestly reporting dropped items and sequence gaps.
- Maintain correlation integrity under backpressure: flag missing causal parents (`correlation_missing_due_to_backpressure`) so Hermes review surfaces gaps under `MISSING_EVIDENCE` without false defect promotion.
- Classify all recorded evidence under a strict fact taxonomy: `OBSERVED_FACT`, `DERIVED_FACT`, `INFERENCE`, `UNKNOWN`, and `ERROR`.
- Establish a canonical evidence envelope featuring `schema_version`, monotonically increasing sequence numbers, unique event IDs, and explicit correlation chains linking logs -> state deltas -> objective traces -> notifications -> screenshots -> manual markers.
- Implement an atomic cross-process marker inbox (`.tmp` -> `.json` rename) that eliminates shared append-file concurrency hazards.
- Enforce fail-closed privacy: when an unparsed log line's safety classification is uncertain, withhold representative text, record `PRIVACY_SAMPLE_WITHHELD = true`, and store only normalized signatures, counts, and timestamps.
- Provide opt-in event-triggered screenshot capture via MSS dispatched to a background worker with strict rate limits, budgets, display targeting, and non-blocking error handling (`SKIPPED_BUDGET`, `SKIPPED_COOLDOWN`, `CAPTURE_FAILED`).
- Manage session manifests atomically across crashes and reconcile sequence counters (`persisted + dropped == sequence_high_watermark`).
- Enforce bounded storage via JSONL rotation and a global quota with deterministic cleanup at session boundaries (never mid-tick), protecting active sessions, finalizing sessions, newly closed sessions, and audit reports.
- Define a rigorous Hermes post-session review protocol with explicit evidence quality criteria, preventing isolated weak anomalies from being misclassified as defects.
- Collect observer operational telemetry (enqueue latency, queue depth, dropped events, worker latency, capture latency) using monotonic timing.

**Non-Goals:**
- Gameplay automation, macro execution, or sending any keystroke/mouse input to the game.
- Autonomous self-modifying code, automatic schema updates, or dynamic build rule changes during a session.
- Continuous high-frequency video capture or continuous screen polling.
- Cloud telemetry, remote reporting, or external API integration.
- Persisting raw Client.txt or unparsed player chat messages.
- Second runtime duplication: the observer must not instantiate duplicate `ProcessMonitor`, `ClientLogTailer`, `CharacterStateStore`, or `ObjectiveEngine` instances.

## Decisions

### 1. Subordinate Non-Blocking Asynchronous Observer Tap & Isolation Architecture

**Decision**: The observer attaches to `ContinuousRuntimeOrchestrator` via an `ObservationTap` interface that dispatches events through a bounded queue to a dedicated background writer/capture worker thread:
```
Runtime Callback (on_log_parsed / on_state_reconciled / on_objective_evaluated / etc.)
  │
  ├── 1. Construct compact, immutable ObservationEnvelope (sub-millisecond)
  ├── 2. Non-blocking queue enqueue: queue.put_nowait(envelope)
  │      └── If queue full (backpressure):
  │            ├── Apply 3-tier drop policy (LOW dropped before MEDIUM before HIGH)
  │            ├── Increment dropped_event_count (and dropped_high_priority_count if HIGH)
  │            └── Record OBSERVATION_BACKPRESSURE metadata
  └── 3. Runtime immediately resumes core loop (Client.txt / state / objective / lease)
        │
        ▼ (Asynchronous)
Background Observer Worker Thread
  ├── 1. Dequeue envelope batch
  ├── 2. Append to corresponding stream (events.jsonl, state_deltas.jsonl, etc.)
  ├── 3. Enforce per-stream file rotation (10 MB threshold)
  ├── 4. Execute pending screenshot captures (if triggered & budgeted)
  └── 5. Catch and isolate any I/O / worker exceptions to health state
```

**Orderly Bounded Shutdown & Queue Drain Sequence**:
When continuous runtime shuts down, the observer executes a strict 9-step termination pipeline:
1. `ContinuousRuntimeOrchestrator` invokes `observer.stop()`.
2. The observer immediately sets an internal shutdown flag to stop accepting new ordinary observation events from runtime callbacks.
3. The background worker drains remaining records from the bounded observation queue.
4. Pending screenshot capture tasks are either completed (if under budget) or marked `SKIPPED_SHUTDOWN`.
5. All active JSONL stream writers are flushed to disk and closed cleanly.
6. Final event counters and sequence watermarks are reconciled: `persisted_event_count + dropped_event_count == sequence_high_watermark`.
7. `session_summary.json` and `session_summary.md` artifacts are generated from persisted stream data.
8. `session_manifest.json` is atomically updated via `.tmp` file write and OS atomic rename.
9. Manifest status is transitioned to `CLOSED`.

**Shutdown Timeout & Fallback (Bounded Drain)**:
- A hard bounded shutdown timeout (default 5.0 seconds) governs the drain pipeline.
- If queue draining, disk flushing, or screenshot capture cannot complete within 5.0 seconds, the drain loop aborts immediately to ensure continuous runtime termination is never blocked indefinitely.
- The manifest status is set to `INCOMPLETE` with `aborted_reason: "OBSERVER_DRAIN_TIMEOUT"`, recording accurate `pending_event_count`, `dropped_event_count`, and `sequence_high_watermark`. The session is never falsely marked `CLOSED`.

**Observer Health States & Worker Degradation**:
- Health states: `HEALTHY`, `DEGRADED`, `FAILED`.
- *Fatal writer failure*: If the background persistence worker encounters an unrecoverable exception (e.g. disk full, permission failure):
  - Observer health transitions to `FAILED`.
  - The continuous companion runtime continues running normally without crashing.
  - Future observation callbacks immediately drop incoming events (or reject enqueue) to prevent unbounded memory growth.
  - Dropped event counters advance, and the session manifest will record `INCOMPLETE` with reason `WORKER_FAILURE`.
  - Worker restart is bounded to at most 1 attempt; infinite restart loops are strictly forbidden.
- *Screenshot worker failure*: If display capture fails repeatedly, observer health transitions to `DEGRADED`. Screenshot capture is suspended while text, delta, and objective persistence continue operating normally.

### 2. Deterministic 3-Tier Backpressure Priority Drop Policy

**Decision**: When the bounded observation queue (capacity 1000) experiences capacity pressure due to rapid log bursts or disk write latency, the system drops events deterministically by priority class:
- `HIGH`: `ERROR` events, novel parser anomalies, state deltas, user manual markers, top objective changes.
- `MEDIUM`: notification dispatch decisions, ordinary parsed gameplay events.
- `LOW`: periodic performance telemetry records, unchanged/no-op diagnostics.

**Drop Resolution Algorithm**:
1. When enqueue is attempted on a full queue, the observer inspects queued items to evict the oldest `LOW`-tier item first, allowing the new record to enqueue.
2. If no `LOW`-tier items exist, the observer evicts the oldest `MEDIUM`-tier item.
3. If the queue is saturated entirely with `HIGH`-tier items and a new record arrives:
   - If the new record is `LOW` or `MEDIUM`, it is dropped immediately at the boundary.
   - If the new record is `HIGH`, the oldest `HIGH` record is shed, `dropped_high_priority_count` is incremented, and an explicit `OBSERVATION_BACKPRESSURE` data-loss event is registered.
4. The system never claims high-value evidence is guaranteed under arbitrary backpressure; all drops are counted and reported honestly.

### 3. Canonical Evidence Envelope, Correlation Contract, and Backpressure Integrity

**Decision**: Every observation record is wrapped in a standardized envelope:
```json
{
  "schema_version": "1.0",
  "observation_session_id": "obs_20260923_140000_abc123",
  "event_id": "evt_9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "sequence_number": 42,
  "taxonomy": "DERIVED_FACT",
  "recorded_at": "2026-09-23T14:05:10.123456+00:00",
  "source_timestamp": "2026/09/23 14:05:09",
  "event_type": "STATE_DELTA",
  "source_ref": "client_log:offset_142055",
  "correlation_refs": [
    "evt_0a2efb3c-1c5d-4bae-8eed-1a0c6a2cba5c"
  ],
  "correlation_missing_due_to_backpressure": false,
  "payload": {
    "field": "level",
    "before": 10,
    "after": 11,
    "verification_status": "VERIFIED"
  }
}
```

**Key rules**:
- `sequence_number`: Strictly monotonic uint64 per session starting from 1, providing total order.
- `event_id`: Unique UUID per event.
- `source_timestamp` vs `recorded_at`: External log timestamps are strictly decoupled from local observation arrival times.
- Explicit correlation graph: downstream records reference preceding upstream event IDs in `correlation_refs`:
  `log observation evt_id` -> `state delta evt_id` -> `objective eval evt_id` -> `notification evt_id` -> `screenshot evt_id` -> `manual marker evt_id`.
- Correlation integrity under backpressure:
  - If an upstream event (e.g. log observation A) is dropped under backpressure while downstream events (state delta B, objective eval C) survive:
  - Records B and C retain their reference to A in `correlation_refs` but set `correlation_missing_due_to_backpressure = true`.
  - Alternatively, the session manifest logs dropped sequence ranges (e.g. `dropped_sequence_ranges: [[14, 18]]`).
  - Sequence gaps are thus fully explainable and distinguishable from storage corruption.
  - Hermes review flags missing causal parents under `MISSING_EVIDENCE` and avoids promoting findings that lack verified parent support.
- Monotonic clock: `time.perf_counter()` or `time.monotonic()` is used for duration, latency, and interval metrics, while ISO-8601 wall-clock timestamps are preserved for review.

### 4. Storage Architecture: JSONL Rotation, Atomic Manifests, and Boundary Global Retention

**Decision**: Raw session artifacts are organized under gitignored `runtime/observations/<observation_session_id>/`:
```
runtime/observations/<observation_session_id>/
  session_manifest.json          # Atomic manifest (status, watermark, dropped counts)
  events.jsonl                   # General lifecycle and sensing events
  state_deltas.jsonl             # Compact before/after state mutations
  objective_traces.jsonl         # Objective evaluations and suppression rationales
  notification_traces.jsonl      # Notification dispatches and queue states
  anomalies.json                 # Privacy-filtered unknown log patterns & samples
  telemetry.jsonl                # Periodic performance metrics
  markers.jsonl                  # Manual player markers
  screenshots/                   # Opt-in screenshot PNGs (if enabled)
  session_summary.json           # Aggregated post-session metrics
  session_summary.md             # Human-readable post-session summary
```

**Rotation and Global Retention Rules**:
- *Per-stream rotation*: Each JSONL file rotates at 10 MB, maintaining up to 5 segments per stream (`events.1.jsonl`, `events.2.jsonl`, etc.).
- *Global storage quota*: A global storage bound across all observation sessions (default 1 GB) prevents disk exhaustion.
- *Boundary execution*: Destructive cleanup is strictly forbidden in the middle of a gameplay tick. Pruning runs only at:
  1. Observation session start
  2. Observation session close
  3. Explicit CLI command (`companion observe cleanup --prune`)
- *Deterministic oldest-session eviction*: When total storage exceeds quota, the oldest unpinned sessions are deleted until storage is below quota.
- *Protection rules for active and newly closed sessions*:
  - The currently active session is immune from deletion.
  - The session currently being finalized and a newly `CLOSED` session remain strictly protected through final summary and manifest writing, preventing retention cleanup from deleting a session before it can be reviewed.
  - Pinned sessions (bearing `.pinned` or `--pin`) are preserved.
  - Reports under `docs/audits/` are permanent project artifacts and are never automatically deleted by retention cleanup.
- *Eviction audit*: Evicted session IDs and freed byte counts are recorded in `runtime/observations/retention_log.jsonl`.

**Atomic Manifest & Counter Reconciliation**:
- `session_manifest.json` tracks `schema_version: "1.0"`, `session_id`, `runtime_run_id`, `started_at`, `ended_at`, `status` (`OPEN`, `CLOSED`, `INCOMPLETE`, `ABORTED`), `sequence_high_watermark`, `persisted_event_count`, `dropped_event_count`, `dropped_high_priority_count`, and artifact counts.
- Manifest updates are atomic via `.tmp` file write followed by OS atomic rename.
- Counter reconciliation invariant: `persisted_event_count + dropped_event_count == sequence_high_watermark`.
- On startup, the observer inspects existing session manifests. Any manifest left in `OPEN` status is transitioned to `INCOMPLETE / ABORTED` with `aborted_reason: "UNEXPECTED_TERMINATION"`. Raw trace files are preserved intact, enabling partial post-session review.

### 5. Fail-Closed Privacy Filter and Anomaly Sampling

**Decision**: Unparsed `Client.txt` lines must pass a strict four-stage privacy filter before pattern extraction or sampling:
1. *Chat & Credential Rejection*: Immediate discard if matching chat channels (`@From`, `@To`, `#`, `$`, `%`, `&`, `!`) or sensitive patterns (tokens, session keys, passwords, bearer credentials).
2. *Approved Envelope Verification*: Verify line matches known debug/engine envelopes (e.g. `[ENGINE]`, `[SYSTEM]`, `Async loading`, zone transition syntax).
3. *Sanitization*: Strip dynamic values (timestamps, player names, IP addresses, object IDs).
4. *Uncertainty Gate (Fail-Closed)*:
   - If line safety classification is uncertain or ambiguous:
     - DO NOT persist representative text!
     - Persist only: normalized signature hash, parser/context classification, `occurrence_count`, `first_seen_at`, `last_seen_at`, and flag `PRIVACY_SAMPLE_WITHHELD = true`.
   - Representative text is persisted (up to 3 samples per signature, max 100 unique signatures) ONLY when the line unequivocally passes all checks and sanitization.
   - Privacy uncertainty strictly reduces available evidence, never leaking arbitrary user text or whispers.

### 6. Asynchronous Opt-In Screenshot Pipeline

**Decision**: Screenshots are strictly opt-in (`--observe-screens`), disabled by default. When enabled:
- *Non-blocking async capture*: The runtime callback emits a `ScreenshotCaptureRequest` envelope to the background worker. Capture and PNG compression occur on the worker thread, ensuring zero frame stalling in runtime callbacks.
- *Discrete triggers*: Triggers only on top objective change, major UNKNOWN state transition, novel parser anomaly, or manual user marker.
- *Rate limits & budgets*: Minimum 30s cooldown between captures, capped at 50 screenshots (or 100 MB) per session.
- *Structured outcomes*: Every request produces an envelope recording `capture_result`:
  - `CAPTURED`: Successful capture with image relative path, SHA-256 hash, and dimensions.
  - `SKIPPED_COOLDOWN`: Suppressed due to active cooldown timer.
  - `SKIPPED_BUDGET`: Suppressed due to exhausted session screenshot budget.
  - `SKIPPED_SHUTDOWN`: Cancelled during bounded shutdown drain.
  - `CAPTURE_FAILED`: OS display capture exception, recorded with error message.
- *State isolation*: Screenshots never mutate `CharacterState` and are never passed to OCR during continuous play.

### 7. Atomic Cross-Process Manual Marker Inbox

**Decision**: Replace shared append-only files with an atomic local inbox directory:
```
runtime/observations/marker_inbox/
  <marker_id>.tmp     # Written during CLI execution
  <marker_id>.json    # Atomically renamed when write completes
```

**Workflow**:
1. User runs `companion observe mark "Gear advice unhelpful"`.
2. CLI checks for active observation session descriptor. If no session is active, reports: `"No active observation session found; marker saved unattached"`.
3. CLI generates unique UUID `marker_id`, writes `<marker_id>.tmp`, flushes, and atomically renames to `<marker_id>.json`.
4. Continuous runtime drains complete `.json` files from `marker_inbox/`, enriches them with active character, zone, top objective ID, and recent sequence numbers, and enqueues to the observer worker.
5. Ingested marker files are moved or deleted atomically according to the retention contract. Incomplete `.tmp` files are ignored.
6. Eliminates Windows file-sharing locks and multi-process append corruption without requiring HTTP/socket daemons.

### 8. Post-Session Analysis, Hermes Evidence Quality Grading, and Partial Recovery

**Decision**: At session shutdown (or via `companion observe review <session_id>`), the system produces `session_summary.json` and `session_summary.md`. Hermes uses these artifacts to compile `DEVELOPMENT_OBSERVATION_REPORT.md` following strict evidence quality rules:
- *Required evidence fields for all findings*:
  - `evidence_ids`: array of concrete observation event IDs.
  - `occurrence_count`: verified frequency.
  - `affected_window`: duration or timestamp span.
  - `corroborated_by_marker`: boolean and marker ID citation.
  - `corroborated_by_screenshot`: boolean and screenshot ID citation.
  - `reproducible`: whether observed repeatedly across sessions or state changes.
  - `missing_evidence`: explicit notes on withheld text (`PRIVACY_SAMPLE_WITHHELD`), skipped captures (`SKIPPED_COOLDOWN`), or dropped causal parents (`correlation_missing_due_to_backpressure`).
- *Defect classification gate*: An anomaly cannot be classified as `LIKELY DEFECT` from a single isolated occurrence unless it represents an unequivocal state invariant violation. Weak isolated anomalies remain classified as `NOT ENOUGH EVIDENCE`.
- *Objective*: Improve companion precision, maintainability, and truthfulness, not inflate recommendation counts.
- *Partial session support*: The summary generator safely ingests incomplete or aborted sessions, computing statistics on available segments without crashing.

### 9. Observer Performance Instrumentation & Monotonic Telemetry

**Decision**: Telemetry flushes periodically record observer health and timing metrics:
- `enqueue_latency_ms`: Monotonic duration to construct envelope and enqueue (sub-millisecond target).
- `observer_queue_depth`: Current fill level of bounded observer queue.
- `dropped_event_count`: Cumulative count of events shed under backpressure.
- `dropped_high_priority_count`: Count of high-priority events shed under backpressure.
- `writer_latency_ms`: Duration of background worker batch write cycle.
- `screenshot_capture_latency_ms`: Duration of MSS frame capture and PNG encoding.
- `worker_error_count`: Cumulative count of caught exceptions in background worker.
- Monotonic timers (`time.perf_counter()`) ensure telemetry values are immune to system clock shifts or NTP adjustments.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| **I/O burst stalls continuous runtime** | Bounded queue with non-blocking enqueue; drop low-priority telemetry under backpressure; background worker performs all disk writes. |
| **Worker thread crash halts runtime** | Worker wraps loop in exception handler, records error to `observer_health.json`, caps queue, and allows continuous runtime loop to proceed unimpeded. |
| **Observer shutdown hangs runtime termination** | Hard bounded shutdown timeout (5.0s); transitions to `INCOMPLETE` with `OBSERVER_DRAIN_TIMEOUT` if queue cannot drain within budget. |
| **Shared marker file corruption across processes** | Two-stage atomic inbox (`.tmp` -> `.json` rename) ensures independent UUID files and prevents write collisions. |
| **Private chat or whisper leakage in unparsed logs** | Fail-closed privacy gate: unparsed lines with uncertain safety classification withhold representative text, setting `PRIVACY_SAMPLE_WITHHELD = true` and saving only hashes and counts. |
| **Screenshot capture freezes game or runtime loop** | Screenshots dispatched asynchronously to worker thread; 30s cooldown and 50 screenshot session cap prevent resource exhaustion. |
| **Disk space exhaustion from long sessions** | 10 MB per-stream JSONL rotation, max 5 segments, max 50 screenshots, plus global storage quota enforced at session boundaries (start, close, cleanup). |
| **Newly closed session deleted before review** | Active sessions, finalizing sessions, and newly closed sessions are explicitly protected from retention eviction during session shutdown. |
| **Corrupted state on sudden process crash** | Atomic `.tmp` -> `.json` manifest writes; unfinalized `OPEN` sessions safely transitioned to `INCOMPLETE / ABORTED` on next startup, enabling partial evidence review. |
| **False-positive defect reports from noisy anomalies** | Hermes evidence grading rules require concrete event ID citations, occurrence counts, and corroboration; single isolated events remain `NOT ENOUGH EVIDENCE`. |

## Migration Plan

1. 100% additive change: all new observation logic resides in `companion/observe/` and `companion observe` CLI subcommands.
2. Continuous runtime behavior without `--observe-dev` remains completely identical, incurring only negligible callback branch checks (`if self._observer:`), with zero background threads and zero storage I/O.
3. No database migrations, external service dependencies, or configuration breaking changes.
4. Rollback is instantaneous by omitting observation flags.
