# Spec Delta: Development Observation Mode

## Purpose

Enables non-intrusive, privacy-safe, read-only collection and deterministic packaging of development evidence during live gameplay without modifying continuous runtime behavior, game state, or objective priority rules.

## ADDED Requirements

### Requirement: Subordinate Non-Blocking Asynchronous Observation Tap
The companion runtime SHALL support an optional read-only development observation tap that attaches to the continuous runtime orchestrator lifecycle, consuming runtime events without modifying canonical character state, build rules, objective priority semantics, or writer locks. The observer SHALL be strictly subordinate to continuous runtime correctness, dispatching events through a bounded queue to a background writer/capture worker, and SHALL NOT execute synchronous filesystem I/O, screenshot capture, or blocking operations inside runtime callbacks. The observer SHALL NOT instantiate duplicate `ProcessMonitor`, `ClientLogTailer`, `CharacterStateStore`, or `ObjectiveEngine` instances.

#### Scenario: Observer attached during live runtime execution
- **WHEN** continuous runtime starts with development observation enabled
- **THEN** the observer receives sensing, state mutation, objective evaluation, and notification events asynchronously without altering the execution order or outcomes of the primary continuous runtime pipeline

#### Scenario: Observer disabled runtime behavior
- **WHEN** continuous runtime starts without observation flags
- **THEN** no observer background worker is created, no observation storage I/O occurs, and the runtime incurs only negligible callback branch check overhead

### Requirement: Orderly Bounded Observer Shutdown and Queue Drain
The system SHALL execute an orderly, bounded shutdown sequence upon runtime termination, and SHALL NOT mark an observation session status as `CLOSED` while queued evidence remains unwritten. The shutdown pipeline SHALL: (1) stop accepting new ordinary observation events, (2) drain pending queue records within a bounded timeout (5.0s), (3) complete or cancel/skip pending screenshot requests, (4) flush and close JSONL streams, (5) reconcile counters and watermarks, (6) write session summaries, (7) atomically update manifest, and (8) transition status to `CLOSED`. If the drain cannot complete within the timeout, the manifest SHALL be marked `INCOMPLETE` with reason `OBSERVER_DRAIN_TIMEOUT` and accurate pending/dropped counts, and SHALL NOT block continuous runtime shutdown indefinitely.

#### Scenario: Successful bounded queue drain and clean closure
- **WHEN** continuous runtime initiates shutdown and the observer queue drains completely within the 5.0-second timeout
- **THEN** the observer flushes all writers, reconciles sequence watermarks and counts, generates session summaries, atomically updates `session_manifest.json`, and marks status as `CLOSED`

#### Scenario: Bounded drain timeout produces incomplete status
- **WHEN** observer queue drain or writer flush exceeds the 5.0-second shutdown timeout
- **THEN** the observer stops draining, records manifest status as `INCOMPLETE` with reason `OBSERVER_DRAIN_TIMEOUT`, accurately logs `pending_event_count` and `dropped_event_count`, and unblocks runtime termination

#### Scenario: Runtime shutdown unblocked during observer hang
- **WHEN** the background worker thread encounters a deadlock or hang during final flush
- **THEN** the shutdown timeout terminates observer waiting, unblocks orchestrator termination, and ensures continuous runtime shutdown completes without indefinite blocking

### Requirement: Observer Health Degradation and Worker Failure Isolation
The system SHALL track observer operational health using explicit states (`HEALTHY`, `DEGRADED`, `FAILED`). A fatal persistence worker failure SHALL NOT crash or terminate the continuous runtime. Upon fatal worker failure, observer health SHALL become `FAILED`, new observation enqueue SHALL be rejected or discarded to prevent unbounded queue growth, dropped event counters SHALL advance, and the session manifest SHALL record status `INCOMPLETE`. Screenshot worker failures SHALL transition health to `DEGRADED` independently without halting non-screen event logging.

#### Scenario: Fatal writer worker failure transitions to failed health
- **WHEN** the persistence worker thread encounters an unrecoverable disk or OS I/O exception
- **THEN** observer health transitions to `FAILED`, incoming enqueue calls are discarded, queue size is capped, manifest is marked `INCOMPLETE`, and continuous runtime continues running normally

#### Scenario: Independent screenshot worker failure transitions to degraded health
- **WHEN** background screenshot capture encounters repeated OS display capture failures
- **THEN** observer health transitions to `DEGRADED`, screenshot capture is suspended, and text/state/objective trace persistence continues operating normally

#### Scenario: Bounded error recovery without infinite restart loops
- **WHEN** a worker thread crashes unexpectedly
- **THEN** the observer attempts at most one bounded restart before marking health as `FAILED`, forbidding infinite restart loops

### Requirement: Deterministic Prioritized Backpressure Shedding
The system SHALL classify observation evidence into deterministic priority tiers: `HIGH` (`ERROR`, parser anomalies, state deltas, user markers, objective changes), `MEDIUM` (`notification decisions`, ordinary parsed gameplay events), and `LOW` (`periodic performance telemetry`, unchanged diagnostics). Under queue capacity pressure, the observer SHALL drop LOW records before MEDIUM records before HIGH records. If HIGH records must be dropped under extreme backpressure, the observer SHALL explicitly record `dropped_high_priority_count` and log `OBSERVATION_BACKPRESSURE` metadata.

#### Scenario: Low priority telemetry dropped first under pressure
- **WHEN** the observer queue exceeds capacity during high log volume
- **THEN** periodic performance telemetry records are shed first while state deltas and parser anomalies are preserved in the queue

#### Scenario: High priority evidence drop reporting
- **WHEN** queue saturation forces the shedding of HIGH-tier evidence records
- **THEN** the observer increments `dropped_high_priority_count`, logs an explicit data-loss backpressure record, and reports the dropped range in session telemetry

### Requirement: Canonical Evidence Envelope and Correlation Contract
The observer SHALL wrap every recorded observation item in a canonical evidence envelope containing `schema_version`, `observation_session_id`, `event_id`, strictly monotonically increasing `sequence_number`, fact taxonomy classification, `recorded_at` local timestamp, optional distinct `source_timestamp`, `event_type`, `source_ref` provenance reference, explicit `correlation_refs` connecting related causal events, and structured payload. The system SHALL explicitly link log observation -> state delta -> objective evaluation -> notification decision -> screenshot -> manual marker rather than inferring correlation from approximate timestamps. When an upstream parent event is dropped under backpressure, downstream surviving records SHALL indicate missing causal parents via `correlation_missing_due_to_backpressure` or dropped parent references. Telemetry duration metrics SHALL use monotonic clock values.

#### Scenario: Monotonic sequence numbering and unique event identification
- **WHEN** multiple events are recorded across different subsystems within an observation session
- **THEN** each event receives a globally unique `event_id` and a `sequence_number` that strictly increases monotonically starting from 1

#### Scenario: Explicit correlation chain across runtime stages
- **WHEN** a parsed log line triggers a state change that subsequently alters an objective recommendation and dispatches a notification
- **THEN** each downstream observation envelope records the preceding event IDs in its `correlation_refs` array, establishing a deterministic causal graph

#### Scenario: Distinction between source and recorded timestamps
- **WHEN** an event originates from an external log line with its own timestamp
- **THEN** the envelope records the parsed log time in `source_timestamp` while capturing the local observer arrival time in `recorded_at`

#### Scenario: Correlation integrity with dropped parent evidence
- **WHEN** an upstream event (e.g. log observation A) is dropped under backpressure but downstream records (state delta B and objective trace C) survive
- **THEN** downstream records retain reference to A and flag `correlation_missing_due_to_backpressure = true`, allowing post-session analysis to distinguish dropped evidence from corrupt storage

### Requirement: Explicit Observation Session Lifecycle and Manifest Reconciliation
The system SHALL manage explicit development observation sessions, assigning a unique `observation_session_id`, linking to the active `runtime_run_id`, recording started and ended timestamps, sequence high watermarks, dropped event counts, and artifact counts within an atomically updated `session_manifest.json`. Upon session completion, total persisted records plus total dropped records SHALL reconcile exactly with `sequence_high_watermark`. If a prior session remains in `OPEN` status on startup, the system SHALL detect and transition it to `INCOMPLETE / ABORTED` status without overwriting history, preserving partial session artifacts for Hermes analysis.

#### Scenario: Clean session initialization and manifest creation
- **WHEN** observation mode is activated on runtime startup
- **THEN** the system generates an `observation_session_id`, initializes an isolated session directory under `runtime/observations/<session_id>/`, and atomically writes an initial `session_manifest.json` with status `OPEN`

#### Scenario: Manifest counter reconciliation on clean close
- **WHEN** an observation session shuts down cleanly
- **THEN** the manifest records `persisted_event_count` and `dropped_event_count` such that `persisted_event_count + dropped_event_count` equals `sequence_high_watermark`

#### Scenario: Recovery of unfinalized prior session on startup
- **WHEN** the runtime starts and discovers an existing session manifest with status `OPEN`
- **THEN** the system marks that manifest status as `INCOMPLETE / ABORTED` with termination reason `UNEXPECTED_TERMINATION` without deleting or modifying raw trace files, and initializes a fresh session

### Requirement: Compact State Change Evidence Recording
The observer SHALL record compact before/after deltas for modified fields of CharacterState with full field-level provenance and verification state, and SHALL NOT emit records on ticks where CharacterState has no mutations.

#### Scenario: Character level mutation detected
- **WHEN** incoming log events advance character level from 10 to 11 with verified provenance
- **THEN** the observer records a state change entry capturing field name, before value (10), after value (11), source identifier, verification status ("VERIFIED"), and observation ID

#### Scenario: Unchanged tick with no state mutations
- **WHEN** runtime completes a poll cycle where no CharacterState fields change
- **THEN** no state delta entry is emitted to the observation trace

### Requirement: Objective Decision Tracing
The observer SHALL record an objective decision trace whenever objective reevaluation occurs, detailing evaluation triggers, relevant state deltas, candidate objective identifiers/categories, the selected top objective, selection rationales, source trust, verification states, suppressed candidates (including those suppressed due to UNKNOWN or STALE state), and whether the output changed from the previous tick. The observer SHALL NOT alter candidate ranking or introduce numeric scoring.

#### Scenario: Objective reevaluation trace emission
- **WHEN** character state mutation triggers objective reevaluation
- **THEN** the observer writes a trace record capturing trigger events, input state deltas, evaluated candidate IDs, selected primary objective, suppression reasons for unchosen/stale candidates, and a boolean flag indicating whether the top objective changed

#### Scenario: Candidate suppression due to unverified or stale state
- **WHEN** an objective candidate cannot be selected because an essential state attribute is UNKNOWN or STALE
- **THEN** the trace record explicitly records the candidate ID and the suppression reason identifying the unverified or stale attribute

### Requirement: Notification Outcome Tracing
The observer SHALL record every notification decision made by the notification subsystem, including notification identity, category, severity, safe-zone status, dispatch decision (DELIVERED, QUEUED, DEDUPED, or SUPPRESSED), current queue depth, cooldown reasons if applicable, and delivery timestamp.

#### Scenario: Notification delivered in safe zone
- **WHEN** a notification is dispatched while the character is in a town or hideout safe zone
- **THEN** the observer logs a trace entry with safe_zone=True, dispatch_status="DELIVERED", queue depth, and delivery timestamp

#### Scenario: Notification queued or deduped
- **WHEN** a notification is evaluated during combat or matches an active deduplication key
- **THEN** the observer logs the suppression or queuing event with the exact policy reason (e.g. "DEDUPED" or "QUEUED_UNSAFE_ZONE")

### Requirement: Fail-Closed Privacy and Anomaly Discovery
The system SHALL inspect unparsed or unrecognized lines from Client.txt using strict privacy filters that completely discard whispers, chat channel messages, credentials, tokens, and private user text. Unrecognized non-chat records SHALL persist representative text ONLY IF the line passes all chat/private filters, matches an approved non-chat Client/debug envelope, and sanitization completely succeeds. When safety classification is uncertain, the system SHALL withhold representative text, record `PRIVACY_SAMPLE_WITHHELD = true`, and persist only normalized signature hashes, frequency counts, and timestamps.

#### Scenario: Safe non-chat unparsed log line with approved envelope
- **WHEN** Client.txt emits an unparsed line matching an approved non-chat debug/engine envelope and sanitization succeeds
- **THEN** the system generates a normalized pattern hash, increments occurrence counts, and stores a bounded sanitized representative sample

#### Scenario: Ambiguous or uncertain log line withheld
- **WHEN** an unparsed log line does not clearly match an approved debug envelope or contains ambiguous free-form tokens
- **THEN** the system withholds representative line text, sets `PRIVACY_SAMPLE_WITHHELD = true`, and records only the pattern hash, classification, occurrence count, and timestamps

#### Scenario: Chat, whisper, credential, or token line encountered
- **WHEN** Client.txt contains a guild chat, global chat, local chat, direct whisper, token, or credential pattern
- **THEN** the privacy filter immediately discards the line, preventing it from being stored as a signature or sample

### Requirement: Non-Blocking Opt-In Event-Triggered Screenshot Capture
The system SHALL support opt-in screenshot evidence capture using the existing read-only MSS capture backend, disabled by default. When enabled, screenshot requests SHALL be enqueued asynchronously to the observer capture worker without blocking runtime tick processing, state reconciliation, or objective evaluation. Screenshots SHALL trigger only on discrete events subject to cooldown and storage budgets, SHALL NOT mutate CharacterState or trigger game inputs, and SHALL record structured outcomes (CAPTURED, SKIPPED_BUDGET, SKIPPED_COOLDOWN, CAPTURE_FAILED).

#### Scenario: Screenshots disabled by default
- **WHEN** observation mode runs without `--observe-screens`
- **THEN** the screen capture backend remains idle and no screenshot files or capture requests are generated

#### Scenario: Event-triggered capture queued to background worker
- **WHEN** `--observe-screens` is enabled and an eligible trigger occurs outside cooldown under budget
- **THEN** a capture request is enqueued to the background worker, which saves the frame image asynchronously and records a `CAPTURED` evidence envelope with image hash and frame metadata

#### Scenario: Capture skipped due to budget or cooldown
- **WHEN** an eligible trigger occurs within the cooldown interval or after session budget exhaustion
- **THEN** the observer emits an evidence record with status `SKIPPED_COOLDOWN` or `SKIPPED_BUDGET` without attempting capture

#### Scenario: Capture failure handling without state mutation
- **WHEN** background screenshot capture encounters an OS display capture error
- **THEN** the observer records a `CAPTURE_FAILED` record with the error details while CharacterState and objective evaluations proceed without interruption

### Requirement: Explicit Screen Capture Privacy Boundary
The system SHALL require explicit monitor selection or game window targeting when screenshot evidence is enabled, SHALL NOT capture secondary or unrelated desktop monitors by default, and SHALL document that screenshots may contain visible account or character identifiers.

#### Scenario: Default monitor targeting
- **WHEN** screenshot capture is initiated without specific multi-monitor overrides
- **THEN** capture is restricted strictly to the primary monitor or explicitly configured game display index

### Requirement: Atomic Cross-Process Manual Development Markers
The system SHALL provide a CLI command to record manual development markers during a live session without sending input to the game or using shared append-only queue files. The CLI SHALL write markers using a two-stage atomic write pattern (`<marker_id>.tmp` renamed to `<marker_id>.json`) in `runtime/observations/marker_inbox/`. The observer SHALL consume only complete marker files, correlate them with active session and objective state, and handle cases with no active observation session honestly by reporting inactive status.

#### Scenario: Atomic marker creation and consumption
- **WHEN** a user executes `companion observe mark "<note>"` while an observation session is active
- **THEN** the CLI writes a temporary `.tmp` marker file and atomically renames it to `.json`, which the observer consumes, correlates with active state, and appends to `markers.jsonl`

#### Scenario: Concurrent marker submission safety
- **WHEN** two separate CLI commands submit markers simultaneously
- **THEN** each marker uses a distinct UUID filename, preventing write collisions and file corruption

#### Scenario: Incomplete marker write ignored
- **WHEN** a marker `.tmp` file is in the process of being written or an aborted write leaves an unrenamed file
- **THEN** the observer ignores `.tmp` files and processes only complete `.json` marker files

#### Scenario: Marker submitted without active observation session
- **WHEN** a user runs `companion observe mark "<note>"` when no continuous runtime observation session is active
- **THEN** the CLI reports clearly that no active observation session is running rather than indicating successful runtime correlation

### Requirement: Operational Telemetry and Observer Performance Metrics
The observer SHALL collect lightweight operational performance metrics periodically using monotonic clock intervals without high-frequency profiling overhead, tracking loop duration, log poll latency, enqueue latency, observer queue depth, dropped evidence count, writer latency, screenshot capture latency, and observer worker error counts.

#### Scenario: Periodic telemetry flush with latency and queue tracking
- **WHEN** the periodic telemetry interval elapses during continuous runtime
- **THEN** an operational telemetry record is written to the observation trace containing current queue depth, enqueue latency, worker write latency, and cumulative dropped event counts

### Requirement: Bounded Storage, Global Quota, and Boundary Retention Cleanup
The system SHALL isolate all raw observation traces, logs, manifests, and screenshots under gitignored session directories (`runtime/observations/<session_id>/`), enforce maximum file size rotation on JSONL streams, enforce maximum anomaly sample limits per signature, enforce screenshot storage quotas, and enforce a global observation storage quota. Retention pruning SHALL execute strictly at session start, session close, or explicit CLI cleanup commands, evicting oldest sessions deterministically while never deleting the active session, the session being finalized, or the newly closed session until the next boundary, and never deleting report artifacts under `docs/audits/`.

#### Scenario: Stream file size rotation
- **WHEN** an observation JSONL file reaches the configured maximum size threshold (10 MB)
- **THEN** the file is rotated to a sequential numbered segment without losing events or exceeding total session storage limits

#### Scenario: Global quota boundary cleanup
- **WHEN** total storage across all observation sessions exceeds the global quota at session start or close
- **THEN** the oldest unpinned inactive sessions are deleted until storage is within quota, logging all evicted session IDs

#### Scenario: Newly closed session retention immunity
- **WHEN** retention cleanup evaluates storage during or immediately after session close
- **THEN** the session currently being finalized and the newly closed session are protected from eviction, ensuring summaries are preserved for review

#### Scenario: Git exclusion verification
- **WHEN** observation sessions and screenshots are created under `runtime/observations/`
- **THEN** git status remains clean and no observation files appear as untracked files in source control

### Requirement: Post-Session Analysis Package Generation
The system SHALL generate deterministic session summary artifacts at session shutdown (`session_summary.json` and `session_summary.md`) containing session duration, process lifecycle transitions, log records consumed, parsed event distributions, anomaly signature counts, state change tallies, objective stability metrics, notification metrics, dropped event metrics, and potential review candidate categories with evidence references, supporting both cleanly closed and partial/aborted sessions.

#### Scenario: Clean shutdown summary generation
- **WHEN** the continuous runtime session terminates cleanly
- **THEN** the observer aggregates metrics, identifies review candidate categories with concrete evidence IDs, and writes `session_summary.json` and `session_summary.md` to the session directory

#### Scenario: Partial or aborted session summary generation
- **WHEN** post-session analysis is requested on an aborted or incomplete session
- **THEN** the summary generator parses available trace files up to the last valid entry, notes the incomplete status, and produces partial summary metrics without crashing

### Requirement: Deterministic Hermes Review Workflow and Evidence Quality Grading
The system SHALL specify a deterministic post-session review procedure where Hermes parses the session manifest, summary, structured event traces, user markers, and screenshot metadata to produce `DEVELOPMENT_OBSERVATION_REPORT.md` separating OBSERVED FACTS, LIKELY DEFECTS, USABILITY FINDINGS, DATA GAPS, FEATURE OPPORTUNITIES, and NOT ENOUGH EVIDENCE. Every finding SHALL cite specific observation event IDs, occurrence counts, time windows, and corroboration. Findings without reproducibility or clear invariant violations SHALL NOT be classified as LIKELY DEFECTS and SHALL remain classified as NOT ENOUGH EVIDENCE.

#### Scenario: Report synthesis from session evidence
- **WHEN** the review workflow is invoked on a completed observation session package
- **THEN** Hermes generates a structured report where every asserted finding cites concrete observation event IDs, occurrence counts, and marker/screenshot corroboration

#### Scenario: Isolated weak anomaly classified as not enough evidence
- **WHEN** an unparsed log anomaly or transient state oscillation occurs only once without invariant violation or corroborating marker
- **THEN** Hermes classifies the finding as NOT ENOUGH EVIDENCE rather than LIKELY DEFECT

#### Scenario: Missing causal parent surfaced under missing evidence
- **WHEN** a surviving finding relies on an upstream parent event that was dropped due to backpressure
- **THEN** Hermes surfaces the missing parent under MISSING_EVIDENCE and does not promote the finding to LIKELY DEFECT without corroborating evidence
