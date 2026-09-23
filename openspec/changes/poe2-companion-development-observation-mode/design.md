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
- Implement an atomic cross-process marker inbox (`.tmp` -> `.json` rename) that eliminates shared append-file concurrency hazards and separates marker IPC from persisted marker evidence.
- Enforce fail-closed privacy: when an unparsed log line's safety classification is uncertain, withhold representative text, record `PRIVACY_SAMPLE_WITHHELD = true`, and store only normalized signatures, counts, and timestamps.
- Provide opt-in event-triggered screenshot capture via MSS dispatched to a background worker with strict rate limits, budgets, display targeting, and non-blocking error handling (`SKIPPED_BUDGET`, `SKIPPED_COOLDOWN`, `CAPTURE_FAILED`).
- Manage session manifests atomically across crashes and reconcile sequence counters (`persisted + dropped == sequence_high_watermark`).
- Enforce bounded storage via JSONL rotation and a global quota with deterministic cleanup at session boundaries (never mid-tick), protecting active sessions, finalizing sessions, newly closed sessions, and audit reports.
- Establish a two-plane architecture decoupling a deterministic local live analysis data plane (`companion observe analyze-live`) from an interactive Hermes AI review plane.
- Implement an independent dual-cursor model: `reader_cursor` (data plane ingestion) vs `review_cursor` (Hermes AI review), accurately tracking and displaying separate reader lag and review lag, while strictly distinguishing physical per-stream read positions from the global contiguous analyzed frontier.
- Ensure crash consistency across both layers via an at-least-once input and idempotent derived output contract: crash-safe multi-stream read-ahead with persistent `accounted_ahead_ranges`, a deterministic `seen_ahead` capacity saturation policy (`ANALYST_READ_AHEAD_SATURATED`), deterministic `review_batch_id` from structured evidence, durable review batch results (`review_batches/<review_batch_id>.json`), and finding revision idempotency.
- Ensure durable stream identity and rotation handling: track stream name, segment identity, byte offsets, and sequence watermarks; detect missing or ambiguous segments as `ANALYST_STREAM_GAP` without silent skipping.
- Enforce clear findings ownership: local data plane emits factual observations (`local_signals.jsonl`), while Hermes AI review synthesizes interpreted development findings (`hermes_findings.jsonl`) without persisting hidden chain-of-thought.
- Track Hermes review liveness via a heartbeat artifact (`hermes_review_status.json`), never inferring active status from stale cursor files.
- Protect continuous runtime and observation evidence against AI provider failures: cover four explicit failure/crash recovery cases (Cases A, B, C, D) so AI errors or task stops leave runtime and evidence intact, allowing seamless review resumption from `review_cursor`.
- Provide an honest multi-tier live status CLI distinguishing observation, local data plane analysis, and Hermes AI review.
- Collect observer operational telemetry (enqueue latency, queue depth, dropped events, worker latency, capture latency) using monotonic timing.

**Non-Goals:**
- Gameplay automation, macro execution, or sending any keystroke/mouse input to the game.
- Autonomous self-modifying code, automatic schema updates, or dynamic build rule changes during a session.
- Continuous high-frequency video capture or continuous screen polling.
- Cloud telemetry, remote reporting, or external API integration.
- Persisting raw Client.txt or unparsed player chat messages.
- Shared append-only JSONL files as cross-process IPC.
- Second runtime duplication: the observer must not instantiate duplicate `ProcessMonitor`, `ClientLogTailer`, `CharacterStateStore`, or `ObjectiveEngine` instances.
- Guaranteeing uninterrupted indefinite AI provider calls.

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
  markers.jsonl                  # Normalized persisted player markers
  screenshots/                   # Opt-in screenshot PNGs (if enabled)
  session_summary.json           # Aggregated post-session metrics
  session_summary.md             # Human-readable post-session summary
  live_analysis/                 # Dedicated local live analysis workspace
    reader_state.json            # Local reader cursors and working indexes
    local_signals.jsonl          # Structured deterministic factual observations
    hermes_review_cursor.json    # Durable cursor of Hermes AI review progress
    hermes_findings.jsonl        # Evaluated development findings from Hermes
    hermes_review_status.json    # Lightweight review heartbeat and liveness status
    review_batches/              # Durable structured review batch outcomes
      <review_batch_id>.json
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

### 7. Authoritative Marker IPC vs Persisted Marker Evidence

**Decision**: Maintain a strict separation between cross-process marker IPC and persisted observation evidence:
```
CLI Process (companion observe mark "<note>")
  │
  ├── 1. Check for active observation session descriptor (fail-fast honesty if none)
  ├── 2. Generate unique UUID marker_id
  ├── 3. Write runtime/observations/marker_inbox/<marker_id>.tmp
  ├── 4. Flush and atomically rename to runtime/observations/marker_inbox/<marker_id>.json
  └── 5. Exit immediately (sub-millisecond CLI response)

Continuous Runtime DevelopmentObserver (Marker Ingestion Loop)
  │
  ├── 1. Poll marker_inbox/ for *.json (completely ignoring *.tmp)
  ├── 2. Parse complete JSON payload and correlate with active runtime state
  ├── 3. Wrap into canonical ObservationEnvelope (event_type: "USER_MARKER")
  ├── 4. Persist to runtime/observations/<session>/markers.jsonl
  └── 5. Atomically remove or archive processed inbox file

Local Live Analyst / Hermes AI Review
  │
  └── Read persisted markers strictly from markers.jsonl (NOT from marker_inbox/)
```

**Key Architectural Invariants**:
- *No Shared Append IPC*: Shared append-only JSONL files (`markers.jsonl`) are strictly forbidden as a cross-process IPC transport because of Windows file locking collisions and multi-writer corruption hazards.
- *Authoritative Marker Input Path*: `marker_inbox/<uuid>.tmp` -> atomic rename -> `<uuid>.json` is the sole authoritative input path.
- *Concurrency Safety*: Every CLI marker invocation creates an isolated, uniquely named UUID file; concurrent submissions never contend on the same file descriptor.
- *Incomplete File Immunity*: Any unrenamed `.tmp` file left by an interrupted CLI process is ignored by the observer consumer until fully renamed.
- *No-Active-Session Honesty*: If a user executes `companion observe mark` when no continuous runtime observation session is active, the CLI prints: `"No active observation session found; marker discarded/unattached"`. It never creates orphaned active records.

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

### 10. Acceptance Policy: Development Observation vs Endurance

**Development-observation acceptance:** Require one continuous real gameplay observation session of at least 30 minutes. Do not add shorter sessions. After the duration gate, compare the saved final manifest, generated summary, and embedded manifest: all must agree on `CLOSED` and terminal timing. Require `HEALTHY`, zero pending, `persisted + dropped == sequence_high_watermark`, no unexplained sequence gaps or unresolved worker errors, a passing privacy audit, and local gitignored raw artifacts. Failure of any gate prevents acceptance regardless of duration.

**Optional endurance/stability soak:** Suggest 60–120 minutes when deeper sustained performance and stability evidence is needed. It is not required for every development-observation acceptance. Do not retrospectively alter the measured lengths of earlier sessions.

**Evidence sufficiency:** No quota of zones or requirement to trigger death, level-up, selected-objective transition, or a notification. Mark naturally absent events `NOT OBSERVED`. Observer acceptance attests to integrity of captured evidence, not to the sufficiency of that evidence for each development recommendation: unsupported conclusions remain `NOT ENOUGH EVIDENCE`. Keep both verdicts distinct in audit reports.

### 11. Two-Plane Architecture: Local Live Analysis Data Plane vs Hermes AI Review Plane

**Decision**: Real-time development observation strictly separates local data-plane evidence processing from AI provider availability:
```
ContinuousRuntimeOrchestrator
  │
  ▼ (Asynchronous Bounded Queue)
DevelopmentObserver (Subordinate single-writer worker)
  │
  ▼ (JSONL streams + atomic manifests)
runtime/observations/<active-session>/*.jsonl
  │
  ├──────────────────────────────────────────────────────────────────┐
  │                                                                  │
  ▼                                                                  ▼
PLANE A: Local Live Analysis Data Plane             PLANE B: Hermes AI Review Plane
(Deterministic, read-only Python process)           (Interactive reasoning model)
  │                                                   │
  ├── companion observe analyze-live                  ├── Triggered via Hermes session
  ├── IncrementalStreamReader                         ├── Reads unreviewed evidence from
  │     └── Tracks reader_cursor.json                 │     hermes_review_cursor.json
  ├── Maintains working indexes:                      ├── Correlates multi-stream causal chains
  │     ├── UNKNOWN persistence duration              ├── Prioritizes pending user markers
  │     ├── Objective churn patterns                  ├── Evaluates development implications
  │     └── Notification queuing telemetry            ├── Inspects bounded Client.txt ranges
  ├── Emits local_signals.jsonl (facts only)          ├── Journals hermes_findings.jsonl
  └── Completely independent of AI availability       └── If AI stops: resumes cleanly later
```

**Layer Responsibilities & Prohibitions**:
- **Layer A: Local Live Analysis Data Plane (`companion observe analyze-live`)**:
  - *Responsibilities*:
    1. Identify the active observation session descriptor.
    2. Incrementally read newly appended JSONL evidence across rotated segments.
    3. Maintain durable `reader_cursor` in `reader_state.json`.
    4. Maintain session correlation indexes and stream watermarks.
    5. Track UNKNOWN persistence durations and objective churn patterns.
    6. Emit objective factual signals into `local_signals.jsonl`.
    7. Surface new evidence candidate bundles requiring AI review.
    8. Recover cleanly across process restarts independently of Hermes context.
  - *Prohibitions*:
    - MUST NOT modify `CharacterState`.
    - MUST NOT modify objectives or recommendation priorities.
    - MUST NOT modify game runtime or OS environment.
    - MUST NOT perform gameplay inputs.
    - MUST NOT edit code or specs.
    - MUST NOT autonomously infer `LIKELY_DEFECT` or `FEATURE_OPPORTUNITY`.
  - May run continuously in the background or be stepped deterministically via CLI.

- **Layer B: Hermes AI Review Plane**:
  - *Responsibilities*:
    1. Read only unreviewed evidence bundles starting from `hermes_review_cursor.json`.
    2. Inspect raw local evidence and bounded `Client.txt` windows when necessary.
    3. Reason about development implications and root causes.
    4. Prioritize and investigate manual user markers.
    5. Classify evidence strength using the conservative finding lifecycle.
    6. Journal evaluated findings into `hermes_findings.jsonl`.
    7. Maintain heartbeat telemetry in `hermes_review_status.json`.
  - *Decoupled Independence*:
    - If Hermes, the AI provider, or the terminal session terminates, the continuous companion runtime, `DevelopmentObserver`, and local data plane remain 100% unaffected.
    - The system never assumes or promises that Hermes will maintain an uninterrupted AI call loop for hours.

### 12. Incremental JSONL Stream Reader & Durable Rotation Cursor Contract

**Decision**: The local data plane uses `IncrementalStreamReader` (`companion/observe/reader.py`) to traverse streams without full rescans.
To prevent cursor corruption across file rotations, the cursor tracks full stream identity rather than bare offsets:

```json
{
  "session_id": "obs_20260923_140000_abc123",
  "updated_at": "2026-09-23T14:15:30.123456+00:00",
  "contiguous_frontier": 7995,
  "read_ahead_saturated": false,
  "accounted_ahead_ranges": [
    [7997, 8000]
  ],
  "streams": {
    "events": {
      "stream_name": "events",
      "current_segment": "events.jsonl",
      "byte_offset": 84210,
      "last_processed_sequence": 8000,
      "updated_at": "2026-09-23T14:15:28.000000+00:00"
    },
    "state_deltas": {
      "stream_name": "state_deltas",
      "current_segment": "state_deltas.jsonl",
      "byte_offset": 23400,
      "last_processed_sequence": 7995,
      "updated_at": "2026-09-23T14:15:29.000000+00:00"
    },
    "markers": {
      "stream_name": "markers",
      "current_segment": "markers.jsonl",
      "byte_offset": 2048,
      "last_processed_sequence": 7990,
      "updated_at": "2026-09-23T14:15:30.000000+00:00"
    }
  }
}
```

**Reader Invariants & Edge Case Handling**:
1. *Complete Record Boundary*: Read strictly up to complete `\n`. If a trailing record is partial at EOF, the reader retreats its cursor to before the partial record, yields without raising JSON decode errors, and resumes once flushed.
2. *Segment Rotation Traversal*:
   - Upon encountering EOF on `events.jsonl` when `events.1.jsonl` exists:
   - Drain remaining complete records from `events.jsonl`.
   - Transition `current_segment` to `events.1.jsonl` and reset `byte_offset` to 0.
   - Validate that sequence numbers in the new segment continue monotonically from `last_processed_sequence` using sequence bounds without whole-file hashing.
   - Never re-read previously consumed records as new.
   - Never skip a segment silently.
3. *Stream Gap Detection (`ANALYST_STREAM_GAP`)*:
   - If a segment unexpectedly disappears (e.g. external deletion) or filename numbering has gaps (e.g. segment 1 exists, segment 2 missing, segment 3 present):
   - The reader refuses to advance blindly.
   - It records `ANALYST_STREAM_GAP` in `reader_state.json` and preserves the last safe cursor.
   - Retention policy explicitly protects all segments of active sessions, preventing retention from causing gaps.
4. *Zero Side-Effects*: Reader opens files read-only (`r` / `rb`), never takes exclusive locks, and never alters observer writer pointers.

### 13. Decoupled Ingestion & Review Dual-Cursor Model (`reader_cursor` vs `review_cursor`)

**Decision**: The system explicitly decouples the local evidence ingestion cursor from the AI review cursor:
- `reader_cursor` (persisted in `reader_state.json`): Tracks how far the local incremental reader has safely ingested, parsed, and indexed raw observation evidence.
- `review_cursor` (persisted in `hermes_review_cursor.json`): Tracks how far Hermes AI review has actually reasoned over evidence, correlated markers, and synthesized findings.

#### A. Contiguous Reader Frontier, Physical Cursors & Crash-Safe Read-Ahead
- **Contiguous Reader Frontier Definition**:
  `reader_latest_sequence` MUST NOT mean "highest sequence number ever observed" and MUST NOT mean "per-stream byte cursor advanced."
  It strictly denotes the "highest contiguous global observation sequence for which all evidence up to N is safely accounted for by the local analysis layer."
  *Example*: If sequences 91, 92, 93, 94, 96, 97, 98, 99, 100 are processed, but sequence 95 is not yet available/accounted, `reader_latest_sequence` MUST remain 94, NOT 100.
  The reader may internally know that later sequences were seen, but the durable safe frontier remains 94 until 95 is:
  1. Processed from its stream,
  2. Explicitly dropped/accounted via durable metadata, or
  3. Represented by an approved gap condition.
  It is never silently skipped.

- **Explicit Distinction: Physical Per-Stream Read Position vs Global Contiguous Frontier**:
  The system strictly separates:
  1. *Physical per-stream read positions*: `streams.<name>.byte_offset` and `streams.<name>.last_processed_sequence` tracking disk read positions for each typed stream file.
  2. *Global contiguous analyzed frontier*: `contiguous_frontier` representing the total monotonic sequence prefix up to which all evidence has been processed or durably accounted.
  When Stream A advances physically ahead of Stream B, physical read positions move beyond the global contiguous frontier. To ensure read-ahead is crash-safe without a database:
  - `reader_state.json` durably persists compact `accounted_ahead_ranges` (`[[start_seq, end_seq], ...]`) alongside per-stream byte offsets.
  - On restart, the reader loads both the stream byte offsets and `accounted_ahead_ranges`, seamlessly restoring its ahead-sequence knowledge.
  - Slower streams catching up immediately advance `contiguous_frontier` through the accounted ranges without re-reading or skipping records.
  - If ahead state cannot be reconstructed safely, physical read cursors rewind to the stream offset aligned with the contiguous frontier and replay deterministically.

- **Multi-Stream Accounting Architecture**:
  The existing observation storage layer writes observation envelopes into multiple typed streams (`events.jsonl`, `state_deltas.jsonl`, `objective_traces.jsonl`, `notification_traces.jsonl`, `telemetry.jsonl`, `markers.jsonl`).
  Global sequence numbers are allocated monotonically by `DevelopmentObserver` across all streams, meaning sequence numbers are interleaved across separate stream files.
  Therefore, the local reader cannot assume `max(sequence_seen_across_streams)` equals safe contiguous progress.
  To prove contiguous global sequence coverage without building an external database, the reader implements a minimal, deterministic frontier accounting mechanism:
  - `contiguous_frontier`: Monotonic integer representing the highest contiguous accounted sequence (persisted in `reader_state.json`).
  - `seen_ahead`: A compact set tracking sequences observed ahead of the frontier, persisted as compact `accounted_ahead_ranges` in `reader_state.json`.
  - When an envelope with sequence `seq` arrives from any typed stream:
    - If `seq <= contiguous_frontier`: duplicate or previously processed sequence; deduplicate without altering the frontier.
    - If `seq == contiguous_frontier + 1`: increment `contiguous_frontier` to `seq`; then while `contiguous_frontier + 1 in seen_ahead`, remove `contiguous_frontier + 1` from `seen_ahead` and advance `contiguous_frontier`.
    - If `seq > contiguous_frontier + 1`: insert `seq` into `seen_ahead`. `contiguous_frontier` remains unchanged.
  This ensures that a faster stream reaching sequence 100 never causes slower stream evidence (e.g. sequence 95 in `objective_traces.jsonl`) to be skipped.

- **seen_ahead Capacity Behavior and Deterministic Saturation Policy**:
  The bounded ahead window (capacity max 1000 ahead sequences) MUST NOT silently discard ahead sequence knowledge upon reaching its limit.
  If `seen_ahead` reaches its configured bound:
  1. *Stop Additional Read-Ahead*: The reader pauses reading further records from any stream whose sequences are ahead of `contiguous_frontier`.
  2. *Keep Safe Frontier Unchanged*: `contiguous_frontier` remains at the last safe contiguous sequence.
  3. *Wait for Frontier + 1*: The reader waits for the lagging stream to emit `contiguous_frontier + 1`, for durable drop metadata in `session_manifest.json` (`dropped_sequence_ranges`), or for an explicit stream gap.
  4. *Expose Saturation Telemetry*: Set `read_ahead_saturated = true` in `reader_state.json` and report `ANALYST_READ_AHEAD_SATURATED` in live status.
  5. *Zero Runtime Interference*: Saturation pauses ONLY the independent local live analyst; it NEVER blocks `ContinuousRuntimeOrchestrator` or `DevelopmentObserver` background writes.
  6. *Saturation Clearance*: Once the missing sequence arrives, `contiguous_frontier` advances through the retained ahead range, capacity is freed, `read_ahead_saturated` resets to `false`, and normal intake resumes.

- **Crash Safety Guarantees**:
  - *Crash loses no un-frontiered evidence*: Every read envelope is either already durably in the stream files on disk, or its ahead range is stored in `reader_state.json`.
  - *Restart reconstructs all ahead records*: Upon restart, `reader_state.json` restores `contiguous_frontier`, `accounted_ahead_ranges`, and per-stream `byte_offset`.
  - *Duplicate replay remains safe*: Replayed records yield deterministic `local_signal_id` values, deduplicating signals without side effects.
  - *Contiguous frontier remains authoritative*: Only contiguous sequences or verified durable drops advance `contiguous_frontier`.

- **Strict Gap Semantics**:
  The reader distinguishes four explicit sequence states:
  1. *Temporarily Not Yet Read*: An interleaved stream has not yet reached or flushed sequence N. The contiguous frontier does NOT advance and waits for the stream to catch up.
  2. *Explicitly Dropped by Observer*: When sequence N was dropped under backpressure by the observer, it is accounted only if durable drop metadata proves it (via `dropped_sequence_ranges` in `session_manifest.json` or explicit drop tombstones). Once verified, the frontier advances through the dropped range.
  3. *ANALYST_STREAM_GAP / Missing Segment*: If an unrecoverable segment gap or file corruption is detected, the reader does NOT advance through the gap, preserves the last safe contiguous frontier, and records `ANALYST_STREAM_GAP` in `reader_state.json`.
  4. *Duplicate Sequence*: Deduplicated immediately; never alters or corrupts the frontier.

#### B. Contiguous Review Cursor Semantics
- `review_cursor` strictly denotes that "all reviewable evidence up to sequence N has completed durable Hermes review accounting."
- The review cursor advances ONLY over a contiguous reviewed/accounted range.
- *Example*: If Hermes reviews sequences 1..500 and 502..550 while sequence 501 is still pending, `review_cursor` MUST remain 500, NOT 550.
- Evidence beyond the frontier may be staged or prefetched internally, but cannot become the durable review frontier until the intervening gap is fully resolved.
- *Empty Batch Review Accounting*: When an evidence batch contains items reviewed where no candidate finding is warranted, Hermes persists lightweight review-batch metadata (`review_batches.jsonl` or embedded in `hermes_review_cursor.json`) indicating the contiguous sequence range reviewed, allowing `review_cursor` to advance safely without generating fake findings.

#### C. Review Lag Computation
Lags are calculated strictly using contiguous frontiers, never maximum-seen sequences:
```
observer_latest_sequence   = 8000 (highest sequence produced by observer)
reader_contiguous_frontier = 7995 (highest contiguous safely analyzed sequence)
review_contiguous_frontier = 7600 (highest contiguous durably reviewed sequence)

reader_lag = observer_latest_sequence - reader_contiguous_frontier = 8000 - 7995 = 5 events
review_lag = reader_contiguous_frontier - review_contiguous_frontier = 7995 - 7600 = 395 events
```
- Honest transparency: Terminal status commands report both metrics separately.
- Independent crash recovery: If Hermes review is interrupted or fails, `reader_cursor` continues advancing. When Hermes restarts, it loads `hermes_review_cursor.json` and resumes from sequence 7600 without re-reading the entire session.

### 14. Crash-Consistent Execution Ordering & Idempotency Models

**Decision**: Both the local data plane and Hermes review layer follow an explicit crash-consistency contract:

#### A. Local Reader Crash-Consistency Model
```
1. Read complete unparsed records from streams up to safe \n boundary
   │
2. Derive deterministic local signals & candidate review bundles
   │
3. Durably persist derived outputs to local_signals.jsonl
   │
4. ONLY after successful persistence, atomically advance reader_cursor in reader_state.json
```
- **Replay Safety & Deterministic Signal Identity**:
  If a crash occurs after step 3 but before step 4, the replayed records will be reprocessed on restart.
  To prevent duplicate logical signals, every derived signal is assigned a stable deterministic identifier:
  `local_signal_id = f"sig:{session_id}:{signal_type}:{source_event_ids_or_range_hash}"`
  Replaying the exact same source evidence yields the exact same signal identity. Analysis state deduplicates by signal identity rather than relying on an unbounded in-memory cache.
- **Strict Error Boundary**:
  If local signal persistence fails, bundle persistence fails, stream segment parsing encounters an unrecoverable format error, or `ANALYST_STREAM_GAP` occurs:
  `reader_cursor` strictly remains at the last safely processed contiguous position. It never skips unpersisted or failed processing.

#### B. Hermes AI Review Crash-Consistency Model
```
1. Determine next pending evidence window past contiguous hermes_review_cursor.json
   │
2. Compute deterministic review_batch_id from structured evidence
   │
3. Check for existing completed live_analysis/review_batches/<review_batch_id>.json
   │
   ├── If EXISTS & COMPLETED: Skip AI invocation, load durable batch result
   └── If MISSING: Invoke Hermes AI review to reason over multi-stream evidence
   │
4. Durably persist structured review result to review_batches/<review_batch_id>.json
   │
5. Idempotently apply finding operations to hermes_findings.jsonl (tracked by review_batch_id)
   │
6. ONLY after successful persistence of batch result & findings,
   atomically advance hermes_review_cursor.json
```

- **Deterministic Review Batch Identity**:
  Do not rely solely on an AI-generated semantic issue key or model text for replay idempotency. Before invoking Hermes, the system calculates a deterministic batch identifier from structured evidence:
  ```python
  content = f"{session_id}:{start_seq}:{end_seq}:{','.join(sorted(source_evidence_ids))}"
  review_batch_id = f"rb_{hashlib.sha256(content.encode()).hexdigest()[:16]}"
  ```
  The batch ID is strictly deterministic based on session ID, sequence boundaries, and ordered source evidence IDs.

- **Durable Review Batch Result Model**:
  Before advancing `review_cursor`, the review plane persists an atomic structured result in `runtime/observations/<session>/live_analysis/review_batches/<review_batch_id>.json`:
  ```json
  {
    "schema_version": "1.0",
    "review_batch_id": "rb_8f2a1b9c3d4e5f60",
    "session_id": "obs_20260923_140000_abc123",
    "sequence_start": 7501,
    "sequence_end": 7600,
    "reviewed_evidence_ids": ["evt_10a", "evt_10b"],
    "operations": [
      {
        "op": "UPDATE",
        "finding_id": "find:obs_20260923_140000_abc123:notification:late-delivery:zone_entry",
        "status": "CORROBORATED",
        "occurrence_count_delta": 1,
        "new_evidence_ids": ["evt_10b"],
        "corroboration_note": "Corroborated by user marker mrk_1"
      }
    ],
    "review_status": "COMPLETED",
    "timestamp": "2026-09-23T14:15:30.123456+00:00"
  }
  ```
  Hidden chain-of-thought is never persisted; only structured review outcomes and finding operations are saved.

- **Replay Semantics & Skipping Duplicate AI Invocations**:
  On Hermes resume or process restart:
  - If the next pending deterministic `review_batch_id` already has a valid durable completed review result file on disk:
    - The review engine MUST NOT invoke the AI provider again merely because `review_cursor` was not advanced.
    - Instead, it loads that durable structured result and replays/applies the operations idempotently.
    - Finding revisions are deduped using `review_batch_id`.
    - `review_cursor` advances safely to `sequence_end`.
  - This eliminates reliance on the model generating identical prose or formatting across separate API calls.

- **Finding Revision Idempotency**:
  Each finding revision produced by a review batch records its source `review_batch_id` in `applied_review_batch_ids: list[str]`.
  - *Applying the SAME review_batch_id twice*:
    - Detected as already applied.
    - Zero duplicate revisions emitted.
    - No increment to `occurrence_count`.
    - No duplicated `evidence_refs`.
  - *NEW review batch with NEW corroborating evidence*:
    - Generates a new `review_batch_id`.
    - Updates the existing logical finding (`find:{session_id}:{category}:{semantic_issue_key}`).
    - Increments `revision` once, updates status, and appends new evidence IDs.
  - *Logical Finding Key*:
    The logical finding identity remains stable (`session_id + category + canonical semantic_issue_key`), while review-batch identity guarantees complete replay idempotency.

- **Logical Finding Identity: Stable Key vs Mutable Evidence Set**:
  Logical finding identity is separated into two distinct concepts:
  1. *Stable Logical Finding Key / ID*:
     Must remain stable while the same underlying issue is corroborated. Derived from stable semantic properties:
     `finding_id = f"find:{session_id}:{category}:{semantic_issue_key}"`
     Where `semantic_issue_key` is a normalized subject or semantic issue key, conceptually:
     - `notification:late-delivery:<objective-or-advisory-key>`
     - `unknown-persistence:<field>`
     - `objective-churn:<objective-key>`
     - `parser-gap:<signature>`
     Finding identity is NEVER derived from the complete mutable evidence set.
  2. *Mutable Evidence Set & Revision*:
     Evidence references are mutable, growing attributes of the logical finding:
     - As new evidence arrives: same `finding_id`
     - Append evidence IDs: `evidence_refs: list[str]`
     - Update `occurrence_count`
     - Evolve lifecycle `status` (e.g. `WATCHING` -> `POSSIBLE_PATTERN` -> `CORROBORATED` -> `LIKELY_DEFECT`)
     - Update `corroboration` notes and timestamps
     - Increment `revision: int`

- **Review Replay Idempotency**:
  - When the exact same review batch is replayed after a crash before cursor advance, it resolves to the exact same logical finding ID, preventing duplicate findings.
  - When NEW corroborating evidence is reviewed later, it updates the same finding where the semantic issue key matches, preserving `finding_id`.
  - Identity does not depend on generated prose equality.
  - Unrelated semantic issues produce distinct logical finding IDs (e.g. F2).
  - Lifecycle state transitions (`WATCHING` -> `CORROBORATED`) preserve the same logical finding ID.

- **Crash / Restart Recovery Behavior**:
  After restart, reader and review processes may replay already-seen records. Stable signal and finding identity prevent logical duplicates.
  Cursor advancement strictly follows contiguous-frontier semantics: no sequence gap may be silently jumped merely because later output already exists.

### 15. Heartbeat-Based Hermes Review Liveness Telemetry

**Decision**: Hermes review liveness is decoupled from static cursor artifacts.
- In `runtime/observations/<session>/live_analysis/hermes_review_status.json`:
  ```json
  {
    "review_run_id": "rev_20260923_141500_xyz789",
    "started_at": "2026-09-23T14:15:00.123456+00:00",
    "last_heartbeat": "2026-09-23T14:15:25.123456+00:00",
    "last_reviewed_sequence": 7600,
    "state": "ACTIVE"
  }
  ```
- **Heartbeat Rules**:
  - `ACTIVE`: A live Hermes review task is actively running and has updated `last_heartbeat` within the freshness window (30 seconds).
  - `OFFLINE / STALE`: `last_heartbeat` is older than 30 seconds, or the file does not exist, or `state` is `STOPPED` / `FAILED`.
  - The system NEVER infers that Hermes is active merely because `hermes_review_cursor.json` exists or old findings are present on disk.
  - The heartbeat file is strictly observational telemetry: it never acts as a blocking mutex, writer lease, or process lock. Provider failure or stale heartbeat has zero impact on the continuous runtime or local data plane.

### 16. Marker Prioritization Across AI Availability

**Decision**:
- When a user submits a marker via `companion observe mark "<note>"`, it is ingested by the observer and persisted to `markers.jsonl`.
- *Hermes Online*: Hermes detects the persisted marker on its next review cycle, prioritizes it ahead of routine telemetry, inspects preceding state and log context, and creates or updates a correlated finding.
- *Hermes Offline*: The local data plane marks the marker as `pending_review = true` in `reader_state.json`.
- *Hermes Resume*: When Hermes connects or resumes review, it immediately processes all pending markers before consuming routine background telemetry. No marker is lost or ignored due to AI downtime.

### 17. Bounded Raw Client.txt Inspection Policy & Privacy Redaction

**Decision**:
- *Bounded Window Inspection*: When structured observation envelopes do not provide sufficient context to diagnose a novel anomaly or marker, Hermes may inspect raw `Client.txt` using bounded byte offsets or timestamp windows around known event offsets.
- *Full Rescan Prohibition*: Scanning `Client.txt` from offset 0 on polling cycles is strictly prohibited to prevent disk thrashing and high latency.
- *Privacy Redaction*: Raw whispers, private chat channels, passwords, and tokens must NEVER be copied into `hermes_findings.jsonl` or `DEVELOPMENT_OBSERVATION_REPORT.md`. If sensitive text appears locally, findings must redact the content and cite only sanitized event IDs and pattern hashes.

### 18. Interactive Hermes Usage Workflow & AI Provider Failure Recovery

**Real-Time Hermes Usage Workflow**:
When the player begins gameplay, the intended interactive workflow is:
1. User starts runtime and observer: `companion runtime start --observe-dev`
2. In Hermes desktop session: User prompts `"Start live development observation"`
3. Hermes:
   - Discovers the active session descriptor in `runtime/observations/active_session.json`.
   - Reads newly appended evidence from `hermes_review_cursor.json`.
   - Executes bounded review cycles while the task remains active, heartbeating into `hermes_review_status.json`.
   - Advances `hermes_review_cursor.json` upon completing each review batch.
   - Prioritizes manual markers and evaluates emerging patterns.
   - Continues until session closes or the Hermes turn concludes.

**AI Provider Failure & Crash Recovery Cases**:
The review plane handles provider failures and crashes deterministically across four explicit cases:
- **Case A: Provider fails before durable review batch result exists**:
  - Provider network drops, rate limits, or context crashes before `<review_batch_id>.json` is written.
  - `review_cursor` remains unchanged at the previous contiguous frontier.
  - No completed batch result exists on disk.
  - Unreviewed evidence stays pending in reader streams.
  - `hermes_review_status.json` transitions to `FAILED` or becomes stale.
  - On the next Hermes invocation, the batch is retried cleanly.
- **Case B: Durable review batch result exists but crash occurs before finding application completes**:
  - `<review_batch_id>.json` was written and marked `COMPLETED`, but the process crashed while updating `hermes_findings.jsonl`.
  - On resume, Hermes calculates the pending `review_batch_id`, discovers the existing completed result in `review_batches/<review_batch_id>.json`.
  - Hermes skips calling the AI provider, loads the structured finding operations from the file, and idempotently finishes applying them to `hermes_findings.jsonl`.
  - Once finding application completes, `review_cursor` advances safely to `sequence_end`.
- **Case C: Finding application completed but crash occurs before review_cursor advances**:
  - Finding operations were journaled to `hermes_findings.jsonl`, but the process terminated before `hermes_review_cursor.json` was updated.
  - On resume, the deterministic batch result is found.
  - Replaying finding application checks `applied_review_batch_ids` on each finding, detecting that the batch was already applied: zero duplicate revisions, no increment to `occurrence_count`, and no duplicate `evidence_refs`.
  - `review_cursor` catches up cleanly to `sequence_end`.
- **Case D: Review completed with NO_FINDING**:
  - Hermes reviews a sequence range (e.g. routine telemetry) and determines no candidate finding or defect is warranted.
  - The durable batch result `<review_batch_id>.json` records `review_status: "COMPLETED"` and `operations: []` (or `NO_FINDING`).
  - `review_cursor` advances safely across the sequence range.
  - On any subsequent restart or recovery, the batch is recognized as complete without re-invoking AI or emitting fake finding records.

Across all cases, `ContinuousRuntimeOrchestrator`, `DevelopmentObserver`, and the local live reader data plane continue running 100% unaffected.

### 19. Runtime Safety Invariants & Prohibition of Live Self-Modification

**Decision**:
- The continuous runtime is the sole authoritative process for game tracking.
- Observation and analysis components are strictly read-only.
- *Prohibition of Live Self-Modification*: During an active observation session, Hermes and all automated tools are strictly forbidden from:
  - Modifying production Python code
  - Modifying test files
  - Modifying OpenSpec specifications or tasks
  - Modifying objective evaluation priority rules
  - Installing OCR libraries or third-party hooks
  - Mutating `CharacterStateStore`
  - Restarting the continuous runtime automatically
- All architectural fixes, schema changes, and heuristic improvements occur post-session after engineer review.

### 20. Non-Intrusive Multi-Tier Live Observation Status CLI UX

**Decision**: The `companion observe live-status` (or `status --live`) command clearly displays the three separate layers with two distinct lags:
```
Observation Session: obs_20260923_140000_abc123
[OBSERVATION]
  Status: OPEN (Elapsed: 22m 15s)
  Observer Health: HEALTHY (Queue depth: 0, Dropped: 0)
  Latest Sequence: 8000

[LOCAL ANALYSIS]
  Reader Contiguous Sequence: 7995 (Reader Lag: 5 events)
  Reader Saturation: HEALTHY (max 1000 ahead; 0 ahead buffered)
  Current Zone: The Forest (Level 12)
  Selected Objective: quest:clear_fetid_pool
  Persistent UNKNOWNs: None
  Factual Signals: 3 active (1 marker, 2 anomaly repetitions)

[HERMES REVIEW]
  Status: ACTIVE (Heartbeat: 4s ago)
  Reviewed Contiguous Sequence: 7600 (Review Lag: 395 events)
  Review Batches: 4 completed, 1 pending
  Active Findings: 2 candidate(s)
    - [CORROBORATED] Notification delay on zone entry (evt_10a; Marker: mrk_1)
    - [WATCHING] Novel engine debug line signature (hash: 7a8f02)
  Pending Markers: 0 unreviewed
```
- If Hermes is offline, the status explicitly states `Hermes Review: OFFLINE / INACTIVE / STALE`. It never misleadingly displays "Hermes LIVE" when only the local data plane is active.
- Lag reporting strictly uses contiguous frontiers: `reader_lag = observer_latest_sequence - reader_contiguous_frontier` and `review_lag = reader_contiguous_frontier - review_contiguous_frontier`. Maximum-seen sequence across streams is never used for lag reporting.
- Reader saturation is reported explicitly (`ANALYST_READ_AHEAD_SATURATED` when saturated) and review batch progress is summarized.

### 21. Immediate Minute-0 Inception vs 30-Minute Acceptance Gate

**Decision**:
- *Minute-0 Inception*: Live analysis starts immediately at minute 0 as soon as the session starts and records are emitted. Actionable development findings can be discovered and corroborated at minute 2, 5, or 10.
- *30-Minute Acceptance Gate*: The >=30-minute requirement applies exclusively to development-observation acceptance qualification (certifying that an observation session provided sufficient sustained duration to validate runtime stability and evidence integrity). It is never an artificial wait condition for beginning development analysis.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| **I/O burst stalls continuous runtime** | Bounded queue with non-blocking enqueue; drop low-priority telemetry under backpressure; background worker performs all disk writes. |
| **Worker thread crash halts runtime** | Worker wraps loop in exception handler, records error to `observer_health.json`, caps queue, and allows continuous runtime loop to proceed unimpeded. |
| **Observer shutdown hangs runtime termination** | Hard bounded shutdown timeout (5.0s); transitions to `INCOMPLETE` with `OBSERVER_DRAIN_TIMEOUT` if queue cannot drain within budget. |
| **Shared marker file corruption across processes** | Two-stage atomic inbox (`.tmp` -> `.json` rename) ensures independent UUID files and prevents write collisions; shared append-only files forbidden as IPC. |
| **Private chat or whisper leakage in unparsed logs** | Fail-closed privacy gate: unparsed lines with uncertain safety classification withhold representative text, setting `PRIVACY_SAMPLE_WITHHELD = true` and saving only hashes and counts. |
| **Screenshot capture freezes game or runtime loop** | Screenshots dispatched asynchronously to worker thread; 30s cooldown and 50 screenshot session cap prevent resource exhaustion. |
| **Disk space exhaustion from long sessions** | 10 MB per-stream JSONL rotation, max 5 segments, max 50 screenshots, plus global storage quota enforced at session boundaries (start, close, cleanup). |
| **Newly closed session deleted before review** | Active sessions, finalizing sessions, and newly closed sessions are explicitly protected from retention eviction during session shutdown. |
| **Corrupted state on sudden process crash** | Atomic `.tmp` -> `.json` manifest writes; unfinalized `OPEN` sessions safely transitioned to `INCOMPLETE / ABORTED` on next startup, enabling partial evidence review. |
| **Multi-stream read-ahead skips un-frontiered evidence after crash** | `reader_state.json` persists compact `accounted_ahead_ranges` alongside per-stream byte positions, restoring ahead-sequence knowledge upon restart. |
| **seen_ahead buffer saturates under persistent stream lag** | Deterministic saturation policy pauses read-ahead (`ANALYST_READ_AHEAD_SATURATED`) without dropping sequence knowledge or stalling continuous runtime. |
| **AI provider failure or Hermes process crash** | Two-plane architecture decouples local data plane from AI review. Runtime and evidence continue unimpeded; Hermes resumes from durable `hermes_review_cursor.json` without full-session reread. |
| **Crash after review batch re-invokes AI and alters finding prose/keys** | Deterministic `review_batch_id` computed from structured evidence + durable review batch results in `review_batches/<id>.json` + finding revision idempotency ensuring zero duplicate revisions or doubled counts. |
| **Replay after crash produces duplicate findings** | Stable logical finding ID (`session_id + category + semantic_issue_key`) and evidence set evolution ensure replayed records and corroborating batches update existing finding rather than creating duplicates or conflicting hashes. |
| **Stale cursor misleadingly indicates active review** | Liveness tracked via `hermes_review_status.json` with 30s freshness window; never inferred from cursor existence. |
| **Stream segment rotation causes lost or skipped records** | `IncrementalStreamReader` tracks stream name, segment identity, byte offsets, and sequence watermarks; detects missing segments as `ANALYST_STREAM_GAP` and preserves cursor. |
| **Local analyzer makes speculative defect claims** | Strict findings ownership: local data plane produces factual signals only (`local_signals.jsonl`); high-level development interpretation belongs exclusively to Hermes review (`hermes_findings.jsonl`). |
| **Live analysis modifies code during active gameplay** | Strict prohibition invariant: live analysis is strictly read-only; code/spec fixes occur only post-session after engineer review. |
| **Analyst falls behind during high-event bursts** | Batch reading with contiguous sequence tracking; routine telemetry processed in bulk while markers and errors trigger high-priority focus; dual cursors accurately report separate contiguous reader and review lag. |

## Migration Plan

1. 100% additive change: all new observation logic resides in `companion/observe/` and `companion observe` CLI subcommands.
2. Continuous runtime behavior without `--observe-dev` remains completely identical, incurring only negligible callback branch checks (`if self._observer:`), with zero background threads and zero storage I/O.
3. No database migrations, external service dependencies, or configuration breaking changes.
4. Rollback is instantaneous by omitting observation flags.
