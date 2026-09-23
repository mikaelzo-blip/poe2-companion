# Spec Delta: Development Observation Mode

## Purpose

Enables non-intrusive, privacy-safe, read-only collection, deterministic local live analysis, and post-session packaging of development evidence during live gameplay without modifying continuous runtime behavior, game state, or objective priority rules.

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

### Requirement: Authoritative Marker IPC and Persisted Marker Evidence
The system SHALL provide a CLI command to record manual development markers during a live session without sending input to the game or using shared append-only queue files. The marker input path SHALL operate as an atomic IPC mechanism: `companion observe mark "<note>"` writes a temporary file (`runtime/observations/marker_inbox/<marker_id>.tmp`) and atomically renames it to `<marker_id>.json`. The continuous runtime `DevelopmentObserver` SHALL drain only complete `.json` marker files, ignore incomplete `.tmp` files, correlate markers with active session state, and persist normalized marker evidence envelopes into `markers.jsonl`. Shared append-only JSONL files SHALL NOT be used as cross-process IPC. Live analysis readers and Hermes SHALL consume the persisted marker evidence produced by the observer. If no continuous runtime observation session is active, the CLI SHALL report inactive status honestly.

#### Scenario: Atomic marker creation and observer ingestion
- **WHEN** a user executes `companion observe mark "<note>"` while an observation session is active
- **THEN** the CLI writes a `.tmp` file and atomically renames it to `.json` in `marker_inbox/`, which the observer consumes, correlates with active state, and persists to `markers.jsonl`

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

### Requirement: Real Gameplay Observation Acceptance and Optional Endurance
A development-observation acceptance session SHALL contain at least 30 minutes of continuous real gameplay observation within one session; shorter sessions SHALL NOT be combined. A 60–120 minute endurance/stability soak MAY be conducted for deeper long-duration testing but SHALL NOT be mandatory for development-observation acceptance. Duration alone SHALL NOT grant acceptance: the final manifest SHALL be `CLOSED`, the summary terminal status and embedded manifest SHALL agree with the final manifest, observer health SHALL be `HEALTHY`, persisted plus dropped event counts SHALL equal the sequence high watermark, pending event count SHALL be zero, all sequence gaps and worker failures SHALL be resolved, privacy audit SHALL pass, and raw artifacts SHALL remain local and gitignored. A naturally absent death, level-up, objective transition, notification, or zone count SHALL be marked `NOT OBSERVED` without invalidating observer acceptance. Development recommendations requiring unobserved events SHALL remain `NOT ENOUGH EVIDENCE`, independently of observer acceptance.

#### Scenario: Continuous session meets technical gates
- **WHEN** one real gameplay session lasts at least 30 continuous minutes and all lifecycle, accounting, integrity, health, privacy and locality checks pass
- **THEN** observer acceptance passes regardless of how many particular gameplay events naturally occurred

#### Scenario: Duration passes but integrity or privacy fails
- **WHEN** a session lasts at least 30 minutes but its summary contradicts its manifest, health fails, sequence accounting fails, pending events remain, a worker failure is unresolved, or privacy/locality audit fails
- **THEN** observer acceptance fails despite meeting the duration minimum

#### Scenario: Accepted observer lacks feature-specific evidence
- **WHEN** a technically accepted session contains no evidence needed for a gear-development recommendation
- **THEN** observer acceptance remains passed while the gear-development conclusion remains `NOT ENOUGH EVIDENCE`

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

### Requirement: Durable Stream Identity, Safe Rotation Traversal, and Gap Detection
The incremental stream reader SHALL read observation JSONL evidence incrementally without re-reading entire trace files, maintaining per-stream read cursors and byte offsets. For each stream, the cursor SHALL persist stream name, segment filename/identity, `byte_offset`, `last_processed_sequence`, and updated timestamp. Segment identity SHALL be validated using sequence bounds and segment metadata without full-file hashing. The reader SHALL consume only complete newline-terminated records, wait safely on partial writes without JSON decode errors, traverse rotated segment files sequentially without skipping records or entering infinite loops, and validate sequence continuity across segments. If a rotated segment unexpectedly disappears or stream identity is ambiguous, the reader SHALL NOT advance blindly, SHALL record `ANALYST_STREAM_GAP`, and SHALL preserve the last safe cursor. Active observation sessions SHALL be protected from retention deletion.

#### Scenario: Incremental reading of newly appended JSONL records
- **WHEN** new observation envelopes are appended to an active JSONL stream
- **THEN** the analyst reads only unread bytes starting from its recorded byte offset, parses the newly arrived records, and advances its stream offset without re-scanning previously read lines

#### Scenario: Safe waiting on partial or incomplete trailing record
- **WHEN** an observation writer is in the middle of writing a record and a trailing newline is missing at the read boundary
- **THEN** the analyst leaves the byte cursor before the partial record, yields execution without raising a JSON decode error, and reads the complete record on the subsequent cycle after the newline is flushed

#### Scenario: Traversal across rotated JSONL segments with sequence validation
- **WHEN** an active stream rotates from `events.jsonl` to `events.1.jsonl` upon reaching the file size limit
- **THEN** the incremental reader detects the segment boundary, completes reading any final bytes from the rotated segment, transitions to the new segment at offset 0, and validates monotonic sequence progression

#### Scenario: Missing or ambiguous segment raises explicit stream gap
- **WHEN** a rotated segment file is unexpectedly missing from the session directory or filename numbering is discontinuous
- **THEN** the reader stops advancing, records an `ANALYST_STREAM_GAP` diagnostic, and preserves the last safe cursor position without data corruption

### Requirement: Crash-Consistent Local Ingestion, Contiguous Reader Frontier, and Multi-Stream Accounting
The local incremental reader SHALL execute under an at-least-once input and idempotent derived output contract: (1) read complete new observation records, (2) derive deterministic local signals and review bundles, (3) persist derived outputs durably to `local_signals.jsonl`, and (4) only after successful persistence, atomically advance `reader_cursor`.
The system SHALL explicitly distinguish physical per-stream read positions (`byte_offset`, `last_processed_sequence`) from the global contiguous analyzed frontier (`contiguous_frontier`). `reader_latest_sequence` SHALL strictly denote the highest contiguous global observation sequence for which all evidence up to N is safely accounted for by the local analysis layer, and SHALL NOT represent the highest sequence number ever observed or a per-stream byte cursor.
Because observation sequences are interleaved across multiple typed streams (`events`, `state_deltas`, `objective_traces`, `notification_traces`, `telemetry`, `markers`), a stream MAY advance physically ahead of the global contiguous frontier. To guarantee crash safety without a database, the reader state in `reader_state.json` SHALL persist compact `accounted_ahead_ranges` (`[[start, end], ...]`) alongside per-stream byte offsets. On crash and restart, the reader SHALL reconstruct all ahead sequence knowledge from `reader_state.json`, ensuring that no un-frontiered evidence is skipped or lost and duplicate replays remain safe.
The bounded read-ahead window (max 1000 ahead sequences) SHALL NOT silently discard ahead sequence knowledge upon reaching capacity. When ahead sequences reach the configured capacity bound, the local reader SHALL apply a deterministic saturation pause policy: it SHALL stop additional read-ahead on ahead streams, SHALL keep the safe contiguous frontier unchanged, SHALL wait for the lagging stream to emit `frontier + 1` (or for durable drop metadata/gap resolution), and SHALL expose `ANALYST_READ_AHEAD_SATURATED`. Saturation SHALL pause only the local analyzer and SHALL NOT block `ContinuousRuntimeOrchestrator` or `DevelopmentObserver`. When the missing sequence arrives, saturation SHALL clear and reading SHALL resume through the retained ahead range.
Sequence gaps SHALL be accounted for according to strict gap semantics:
1. Temporarily not yet read: the contiguous frontier SHALL NOT advance.
2. Explicitly dropped by observer: a sequence range SHALL be treated as accounted only when proved by durable drop metadata in `session_manifest.json` (`dropped_sequence_ranges`) or explicit observer drop tombstones.
3. `ANALYST_STREAM_GAP` or missing segment: the reader SHALL NOT advance through the gap, SHALL halt contiguous frontier progress, and SHALL report a degraded gap state.
4. Duplicate sequence: duplicate records SHALL be deduplicated and SHALL NOT alter or corrupt the frontier.
Derived local signals SHALL possess a deterministic `local_signal_id` computed from signal type, session ID, and relevant source observation event IDs or sequence ranges. If a crash or interruption occurs after output persistence but before cursor advancement, replayed records SHALL yield identical signal identities, preventing duplicate logical signals without relying on unbounded in-memory caches. If output persistence fails, segment parsing fails materially, or `ANALYST_STREAM_GAP` occurs, `reader_cursor` SHALL strictly remain at the last safely processed contiguous sequence.

#### Scenario: Missing sequence holds contiguous reader frontier
- **WHEN** the local reader processes sequences 1, 2, 4, and 5 while sequence 3 has not yet arrived or been accounted for
- **THEN** `reader_latest_sequence` remains at 2 and does not advance to 5

#### Scenario: Arrival of missing sequence advances reader frontier through buffered sequences
- **WHEN** missing sequence 3 arrives and is safely processed after sequences 4 and 5 were buffered
- **THEN** the reader contiguous frontier advances from 2 through 5

#### Scenario: Highest seen sequence never substitutes for contiguous frontier
- **WHEN** an observation stream emits sequence 100 while an interleaved stream has processed only up to sequence 94 with sequence 95 pending
- **THEN** `reader_latest_sequence` remains 94 and reader lag reflects the gap against the observer high watermark

#### Scenario: Stream A read ahead with stream B missing frontier sequence preserves ahead state across crash
- **WHEN** Stream A reads ahead to sequence 100 while Stream B has emitted only up to sequence 94, state is persisted with `contiguous_frontier = 94` and `accounted_ahead_ranges = [[96, 100]]`, and the process crashes
- **THEN** upon restart the reader restores both physical stream positions and `accounted_ahead_ranges`, losing no ahead evidence and waiting for sequence 95 without skipping records

#### Scenario: Per-stream physical cursor ahead of global frontier reconstructs safely on restart
- **WHEN** physical per-stream byte cursors have moved beyond the global contiguous frontier before an unexpected shutdown
- **THEN** restart reconstructs the ahead state from `reader_state.json` and stream files, allowing safe continuation or deterministic replay without advancing the contiguous frontier prematurely

#### Scenario: Read-ahead capacity saturation pauses reading safely without discarding evidence
- **WHEN** the volume of sequences read ahead across streams reaches the configured bound (1000 items) while the contiguous frontier remains held by a missing sequence
- **THEN** the reader stops additional read-ahead, holds `contiguous_frontier` unchanged, retains all ahead sequence knowledge without dropping records, and flags `ANALYST_READ_AHEAD_SATURATED`

#### Scenario: Saturation does not block continuous runtime or observer
- **WHEN** the local live reader enters `ANALYST_READ_AHEAD_SATURATED` state due to a lagging stream
- **THEN** the continuous runtime and `DevelopmentObserver` writer proceed completely unimpeded without queue backpressure or frame stalling

#### Scenario: Arrival of missing sequence clears saturation and advances frontier through retained ahead range
- **WHEN** the missing sequence holding the frontier arrives while the reader is saturated
- **THEN** the reader incorporates the missing sequence, advances `contiguous_frontier` through the retained ahead range, clears `ANALYST_READ_AHEAD_SATURATED`, and resumes normal stream intake

#### Scenario: Duplicate sequence does not corrupt frontier
- **WHEN** an observation record with an already-processed sequence number is read again
- **THEN** the reader deduplicates the record and leaves the contiguous frontier unchanged

#### Scenario: Explicitly dropped sequence accounted via durable metadata advances frontier
- **WHEN** sequence 95 is missing from stream files but is recorded in the session manifest's `dropped_sequence_ranges`
- **THEN** the reader accounts sequence 95 as dropped and advances the contiguous frontier past 95 to 100

#### Scenario: Analyst stream gap prevents frontier advancement
- **WHEN** a missing stream segment causes an `ANALYST_STREAM_GAP` condition at sequence 200
- **THEN** the reader frontier halts strictly before sequence 200 and reports a degraded gap state

#### Scenario: Crash after signal persistence replayed idempotently
- **WHEN** a local data plane crash occurs after appending a signal to `local_signals.jsonl` but before `reader_cursor` is updated
- **THEN** on subsequent startup the replayed observation records generate the identical `local_signal_id`, resulting in no duplicate logical signal in analysis state

#### Scenario: Signal persistence failure holds reader cursor at safe position
- **WHEN** an I/O exception occurs while attempting to write derived signals to disk
- **THEN** `reader_cursor` does not advance, retaining its position at the last safely committed sequence

#### Scenario: Incomplete trailing record holds reader cursor before boundary
- **WHEN** a stream segment ends with an incomplete line missing a trailing newline
- **THEN** the reader does not consume the partial line and leaves `reader_cursor` strictly before the partial record

### Requirement: Crash-Consistent Hermes AI Review and Deduplicable Finding Evolution
The Hermes AI review layer SHALL execute an explicit crash-consistent pipeline: (1) determine the next pending evidence window past contiguous `review_cursor`, (2) compute a deterministic `review_batch_id` from structured evidence, (3) check whether a completed review result for `review_batch_id` already exists on disk, (4) execute AI reasoning only if no completed batch result exists, (5) durably persist structured batch outcome to `live_analysis/review_batches/<review_batch_id>.json` and journal finding updates to `hermes_findings.jsonl`, and (6) only after successful persistence, atomically advance `hermes_review_cursor.json`.
Before invoking Hermes AI, the system SHALL derive a deterministic `review_batch_id` from structured evidence: `hash(session_id + contiguous_start_sequence + contiguous_end_sequence + ordered source evidence IDs)`. The batch ID SHALL NOT depend on model-generated text, thoughts, or formatting.
Before advancing `review_cursor`, the review plane SHALL persist a durable structured review result in `runtime/observations/<session>/live_analysis/review_batches/<review_batch_id>.json` written atomically via temporary file and rename. The batch result SHALL record `review_batch_id`, sequence bounds, reviewed evidence IDs, finding operations (`CREATE`, `UPDATE`, `NO_FINDING`), canonical finding keys, timestamp, and review status. Hidden chain-of-thought SHALL NOT be persisted.
On Hermes resume, if the next pending deterministic `review_batch_id` already has a valid completed durable review result, the system SHALL NOT invoke AI again; instead, it SHALL replay and apply that durable structured result idempotently, deduplicate finding revisions using `review_batch_id`, and advance `review_cursor` safely.
Each finding revision produced by a review batch SHALL remember its source `review_batch_id`. Applying the SAME `review_batch_id` twice SHALL produce no duplicate revision, no doubled `occurrence_count`, and no duplicated `evidence_refs`.
Logical finding identity SHALL be decoupled into two distinct concepts:
1. Stable Logical Finding Key / ID: A deterministic identifier derived from session ID, finding category, and normalized subject / semantic issue key (e.g. `find:{session_id}:{category}:{semantic_issue_key}`, such as `notification:late-delivery:<objective-or-advisory-key>`, `unknown-persistence:<field>`, `objective-churn:<objective-key>`, `parser-gap:<signature>`). The finding ID SHALL remain stable while the same underlying issue is corroborated, and SHALL NOT be derived from the complete mutable evidence set.
2. Mutable Evidence Set and Revision: Evidence references, occurrence counts, corroborations, and lifecycle statuses SHALL be mutable, growing attributes of the logical finding.
When new corroborating evidence arrives in a NEW review batch, the system SHALL update the existing finding matching the semantic issue key (appending evidence references, incrementing occurrence count, and evolving lifecycle status, such as from `WATCHING` to `CORROBORATED`), preserving its original finding ID and incrementing revision once. Unrelated semantic issues SHALL produce distinct finding IDs.

#### Scenario: Deterministic review batch ID derived from structured evidence
- **WHEN** an unreviewed evidence window with sequences 101..150 and evidence IDs [evt_1, evt_2] is prepared for Hermes review
- **THEN** the system computes a deterministic `review_batch_id` from the session ID, sequence bounds, and evidence IDs prior to invoking the AI provider

#### Scenario: Exact review batch replay returns same finding ID without duplicate
- **WHEN** Hermes review replays an evidence batch after a crash before cursor advance
- **THEN** the re-evaluated findings resolve to the identical finding ID F1 and do not emit a duplicate finding record

#### Scenario: Completed batch result prevents duplicate AI re-invocation after crash
- **WHEN** a review batch result `<review_batch_id>.json` was durably persisted but a crash occurred before `review_cursor` advanced
- **THEN** on resume the system detects the completed batch result, skips the AI provider invocation, applies the structured outcome idempotently, and advances `review_cursor`

#### Scenario: Applying same review batch twice preserves revision and occurrence count
- **WHEN** finding application is executed twice with the identical `review_batch_id`
- **THEN** the second execution detects the already-applied `review_batch_id`, producing zero duplicate revisions, no increment to `occurrence_count`, and no duplicate entries in `evidence_refs`

#### Scenario: New corroborating evidence updates existing finding without changing finding ID
- **WHEN** a subsequent review batch provides new corroborating evidence B for an existing finding F1 created from evidence A with matching semantic issue key
- **THEN** Hermes updates finding F1 by appending evidence reference B, updating occurrence count, and preserving finding ID F1

#### Scenario: Unrelated semantic issue creates distinct finding ID
- **WHEN** Hermes reviews evidence representing a different semantic issue key within the same session
- **THEN** Hermes creates a new finding F2 with a distinct logical finding ID

#### Scenario: Finding lifecycle evolution preserves finding ID
- **WHEN** a finding advances from `WATCHING` to `CORROBORATED` upon receiving corroborating evidence
- **THEN** the finding record updates its status to `CORROBORATED` while retaining the identical finding ID

#### Scenario: Review output persistence failure holds review cursor
- **WHEN** persisting evaluated findings or review batch result fails due to an I/O error
- **THEN** `hermes_review_cursor.json` does not advance, and the batch remains unreviewed for retry

### Requirement: Contiguous Review Cursor Semantics and Review-Batch Accounting
The review cursor in `hermes_review_cursor.json` SHALL strictly denote that all reviewable evidence up to sequence N has completed durable Hermes review accounting over a contiguous sequence range, and SHALL NOT represent merely that evidence was read into memory or the highest sequence observed.
The review cursor SHALL advance only over a contiguous reviewed/accounted range. Evidence beyond the frontier MAY be staged or prefetched internally, but SHALL NOT become the durable review frontier until any preceding sequence gap is fully resolved.
When an evidence batch contains items reviewed where no candidate finding is warranted, the review plane SHALL persist lightweight review-batch metadata recording the completed sequence range so `review_cursor` advances safely without generating fabricated findings.

#### Scenario: Gap in reviewed sequences holds review cursor at contiguous frontier
- **WHEN** Hermes completes review for sequences 1..100 and 102..120 while sequence 101 remains pending review
- **THEN** `review_cursor` remains at sequence 100 and does not advance to 120

#### Scenario: Completion of pending sequence advances review cursor through accounted range
- **WHEN** pending sequence 101 finishes durable review accounting after sequences 102..120 were accounted
- **THEN** `review_cursor` advances from 100 through 120

#### Scenario: Batch with no findings advances review cursor via review-batch metadata
- **WHEN** Hermes completes a review cycle over 50 routine telemetry records with no anomalies or findings
- **THEN** a review-batch record is committed and `hermes_review_cursor.json` advances by 50 events without emitting empty or fake finding records

#### Scenario: Partial batch failure holds review cursor
- **WHEN** review processing fails halfway through an evidence batch
- **THEN** `hermes_review_cursor.json` remains at the sequence watermark of the last fully accounted batch

### Requirement: Heartbeat-Based Hermes Review Liveness and Telemetry Isolation
Hermes review liveness SHALL be recorded in `runtime/observations/<session_id>/live_analysis/hermes_review_status.json` containing `review_run_id`, `started_at`, `last_heartbeat`, `last_reviewed_sequence`, and `state` (`ACTIVE`, `IDLE`, `STOPPED`, `FAILED`). Hermes review status SHALL be evaluated as `ACTIVE` only while an active review task is updating its heartbeat timestamp within an established freshness window (30s). If the heartbeat becomes stale or absent, status SHALL be reported honestly as `OFFLINE / INACTIVE / STALE`. Liveness SHALL NOT be inferred merely from the presence of `hermes_review_cursor.json` or existing findings. The heartbeat artifact SHALL serve strictly as telemetry and SHALL NOT act as an exclusive filesystem lock or impede runtime and local reader operations.

#### Scenario: Fresh heartbeat reports Hermes active
- **WHEN** Hermes review executes and updates `hermes_review_status.json` with a timestamp within 30 seconds
- **THEN** live status reports Hermes review status as `ACTIVE`

#### Scenario: Stale heartbeat reports Hermes offline without inferring from cursor file
- **WHEN** `hermes_review_cursor.json` exists but `hermes_review_status.json` has a heartbeat timestamp older than 30 seconds
- **THEN** live status reports Hermes review as `OFFLINE / STALE` and does not claim Hermes is active

#### Scenario: Provider failure updates heartbeat status without impacting runtime
- **WHEN** an AI provider rejection causes the review loop to exit with state `FAILED`
- **THEN** `hermes_review_status.json` records `state: FAILED` while continuous runtime and local data plane continue operating normally

### Requirement: Decoupled Ingestion and Review Dual-Cursor Model
The system SHALL decouple evidence consumption into two independent cursors: a collection reader cursor (`reader_cursor` in `reader_state.json`) tracking how far the local incremental reader has safely parsed and indexed evidence, and a Hermes AI review cursor (`review_cursor` in `hermes_review_cursor.json`) tracking how far Hermes has reviewed and synthesized findings. Both cursors SHALL be durably persisted with atomic writes and updated timestamps. Upon restart or crash recovery, each cursor SHALL resume independently without re-processing earlier events or resetting the other plane's state.

#### Scenario: Dual-cursor tracking and honest review lag reporting
- **WHEN** the local reader processes event sequence 7995 while Hermes has completed review up to event sequence 7600
- **THEN** the system tracks `reader_cursor.sequence = 7995` and `review_cursor.sequence = 7600`, accurately reporting a review lag of 395 events

#### Scenario: Independent crash recovery of reader and review cursors
- **WHEN** Hermes review terminates mid-session while local reading continues
- **THEN** the local reader continues advancing `reader_cursor`, and upon Hermes re-invocation, Hermes resumes directly from `review_cursor` (7600) without re-reading the entire session or corrupting `reader_cursor`

### Requirement: Local Live Analysis Data Plane Isolation
The system SHALL provide a deterministic, read-only local process (`companion observe analyze-live`) that executes independently of external AI availability. The local data plane SHALL identify active observation sessions, incrementally ingest newly appended evidence, manage durable reader cursors across rotated segments, maintain correlation indexes, track UNKNOWN persistence durations and churn metrics, surface new evidence bundles requiring review, and continue or recover independently of Hermes model context. The local data plane SHALL NOT modify `CharacterState`, objectives, game runtime, gameplay inputs, or code.

#### Scenario: Local analysis data plane executes independently of AI availability
- **WHEN** continuous runtime and observer are active but Hermes AI review is not running
- **THEN** `companion observe analyze-live` ingests new evidence, updates `reader_state.json` and `local_signals.jsonl`, and tracks UNKNOWN persistence without blocking or error

#### Scenario: Local analysis tracks UNKNOWN persistence and churn metrics
- **WHEN** a CharacterState attribute remains UNKNOWN for N consecutive seconds or events
- **THEN** the local data plane updates its correlation index and emits an objective factual observation into `local_signals.jsonl`

#### Scenario: Strict read-only isolation with zero runtime or state mutation
- **WHEN** the local data plane executes analysis sweeps
- **THEN** no CharacterState mutations, objective rule modifications, or game inputs are performed

### Requirement: Separation of Deterministic Local Signals and AI Development Findings
The system SHALL separate factual deterministic local signals from interpretive AI development findings. The local data plane MAY emit structured factual observations into `local_signals.jsonl` (including persistent UNKNOWN state, repeated objective reevaluation, notification queuing patterns, anomaly signature repetition, marker arrivals, worker errors, and missing correlations). The local data plane SHALL NOT autonomously assert `LIKELY_DEFECT`, `FEATURE_OPPORTUNITY`, or architectural recommendations without mechanical proof of invariant violation. Interpretive development findings SHALL be generated exclusively by the Hermes AI review plane and recorded in `hermes_findings.jsonl` using the conservative lifecycle (`WATCHING` -> `POSSIBLE_PATTERN` -> `CORROBORATED` -> `LIKELY_DEFECT` / `USABILITY_SIGNAL` / `DATA_GAP` / `NOT_ENOUGH_EVIDENCE`).

#### Scenario: Local data plane emits factual signal without speculative defect classification
- **WHEN** an unparsed log anomaly repeats 5 times during gameplay
- **THEN** the local data plane logs an objective frequency signal in `local_signals.jsonl` but does not classify it as `LIKELY_DEFECT`

#### Scenario: Hermes reviews corroborated signals and updates findings lifecycle
- **WHEN** Hermes reviews an unparsed log anomaly signal that is corroborated by a player marker citing missing skill UI
- **THEN** Hermes correlates the marker and log evidence, evaluates development implications, and records a structured finding in `hermes_findings.jsonl` transitioning status to `CORROBORATED`

### Requirement: High-Priority Marker Escalation Across AI Availability
A persisted marker in `markers.jsonl` SHALL become a high-priority candidate for Hermes AI review. If Hermes is actively running, it SHALL review the marker promptly and correlate nearby causal evidence. If Hermes is offline, the marker reference SHALL be retained in local analysis state as pending review. When Hermes resumes, pending markers SHALL be reviewed before routine low-value telemetry. No marker SHALL be lost or skipped due to Hermes unavailability.

#### Scenario: Marker prioritized immediately during active Hermes session
- **WHEN** a player records a manual marker while Hermes live review is actively running
- **THEN** Hermes reviews the marker on its next cycle, queries preceding state deltas and objective decisions via `correlation_refs`, and generates an enriched candidate finding linking the user observation to system state

#### Scenario: Offline Hermes retains pending marker and prioritizes it upon resume
- **WHEN** a player records a manual marker while Hermes is offline
- **THEN** the local data plane indexes the marker as pending review, and when Hermes is subsequently invoked, Hermes reviews the pending marker before processing routine telemetry

### Requirement: Live Analysis Journal Layout, Privacy Redaction, and Raw Client.txt Inspection Policy
The system SHALL persist live analysis artifacts under `runtime/observations/<session_id>/live_analysis/`, specifically separating `reader_state.json`, `local_signals.jsonl`, `hermes_review_cursor.json`, `hermes_findings.jsonl`, `hermes_review_status.json`, and `review_batches/<review_batch_id>.json`. Hidden chain-of-thought SHALL NOT be persisted. Hermes findings SHALL record only finding ID, classification, safe summary, evidence refs, frequency, corroboration, uncertainty, missing evidence, and updated timestamp. Hermes live review SHALL be permitted to inspect raw local files within the session folder and `Client.txt` via bounded offset or timestamp windows around known events, but SHALL NOT perform full-file rescans of `Client.txt` on polling cycles. Raw private chat, whispers, credentials, or tokens SHALL NOT be reproduced in live findings, journals, or reports; if sensitive text is encountered locally, findings SHALL redact the sensitive text and reference sanitized event IDs or signature hashes instead.

#### Scenario: Structured finding journal without hidden chain of thought
- **WHEN** Hermes writes an evaluated finding to `hermes_findings.jsonl`
- **THEN** the entry contains only structured finding metadata, classifications, citations, and safe summaries without internal scratchpad or raw model thoughts

#### Scenario: Sensitive text encountered in local evidence is redacted in findings
- **WHEN** local raw inspection encounters a log line containing sensitive private text or whispers
- **THEN** the analyst redacts the private text from `hermes_findings.jsonl`, referencing only the safe `event_id` and normalized pattern hash

#### Scenario: Bounded window inspection of Client.txt around marker timestamp
- **WHEN** Hermes requires raw context to investigate an anomaly associated with a marker
- **THEN** Hermes reads only a bounded byte range in `Client.txt` around the marker timestamp rather than scanning the entire file

### Requirement: Zero-Interference Runtime Isolation and Prohibition of Live Code Modification
The live analyst and Hermes review routines SHALL operate strictly read-only on already-persisted evidence and SHALL NOT block `Client.txt` ingestion, `CharacterState` reconciliation, objective evaluation, notification delivery, checkpointing, or runtime shutdown. An analyst failure or pause SHALL NOT crash or delay the continuous runtime. During live gameplay, Hermes SHALL NOT modify production code, tests, OpenSpec artifacts, build rules, or `CharacterState`. Any bug fixes, schema changes, or rule modifications SHALL occur strictly after session termination and engineer review.

#### Scenario: Continuous runtime remains unaffected when live analyst terminates unexpectedly
- **WHEN** the live analyst script or Hermes process encounters an exception and terminates mid-gameplay
- **THEN** the continuous runtime continues ingesting logs, updating character state, evaluating objectives, and delivering notifications without error or latency degradation

#### Scenario: Live gameplay prohibits self-modifying code execution
- **WHEN** an active observation session is running
- **THEN** Hermes and automated analyst tools are restricted to read-only observation and journal updates, withholding code or configuration patches until gameplay concludes

### Requirement: Non-Intrusive Multi-Tier Live Observation Status UX
The system SHALL provide a lightweight, read-only terminal status command (`companion observe live-status` or `companion observe status --live`) that reports three distinct sequence watermarks and two distinct lag metrics based strictly on contiguous frontiers, NEVER on maximum-seen sequences across interleaved streams:
1. `observer_latest_sequence`: Highest sequence produced/accounted by the continuous runtime observer.
2. `reader_latest_sequence`: Highest contiguous safely analyzed sequence frontier, displaying `reader_lag = observer_latest_sequence - reader_latest_sequence`. When the read-ahead buffer reaches capacity, status SHALL expose reader saturation state (`ANALYST_READ_AHEAD_SATURATED`).
3. `hermes_reviewed_sequence`: Highest contiguous durably reviewed sequence frontier, displaying `review_lag = reader_latest_sequence - hermes_reviewed_sequence`. Status SHALL expose pending and completed review batch counts.
If Hermes is offline, stopped, or has a stale heartbeat, status SHALL display Hermes as `OFFLINE / INACTIVE / STALE` and SHALL NOT claim "Hermes LIVE" merely because the local data plane is running.

#### Scenario: Querying live analyst status with separate reader and review lags
- **WHEN** an engineer runs `companion observe live-status` with observer at 8000, reader contiguous frontier at 7995, and Hermes review contiguous frontier at 7600
- **THEN** the CLI clearly displays observer sequence 8000, reader sequence 7995 (reader lag 5), and Hermes reviewed sequence 7600 (review lag 395)

#### Scenario: Lag values computed using contiguous frontiers rather than maximum seen sequence
- **WHEN** the observer has produced up to sequence 8000, the reader has observed records up to sequence 7998 across streams but sequence 7990 is pending (contiguous frontier at 7989), and review has accounted up to sequence 7950
- **THEN** live status displays reader sequence 7989 with reader lag 11 (8000 - 7989) and Hermes review sequence 7950 with review lag 39 (7989 - 7950), refusing to use the maximum seen sequence 7998 for lag calculation

#### Scenario: Live status exposes reader saturation state and review batch counts
- **WHEN** the local reader has paused due to reaching read-ahead capacity and 4 review batches have completed with 1 pending
- **THEN** live status reports reader state as `ANALYST_READ_AHEAD_SATURATED` and review metrics as `Batches: 4 completed, 1 pending` alongside sequence frontiers

#### Scenario: Honest live status reporting when Hermes review is offline
- **WHEN** `companion observe live-status` is run while the local data plane is active but Hermes review heartbeat is stale
- **THEN** the CLI reports observation and local analysis metrics while explicitly indicating that Hermes review is OFFLINE/STALE, without displaying "Hermes LIVE"

### Requirement: AI Provider Failure Isolation and Seamless Review Recovery
The system SHALL isolate continuous runtime execution, `DevelopmentObserver` persistence, and the local analysis data plane from AI provider rejections, network errors, rate limits, and Hermes task interruptions. An AI provider failure SHALL NOT cause continuous runtime crashes, observer health degradation, or raw evidence loss.
The review layer SHALL handle failures deterministically across four explicit failure and crash recovery cases:
- Case A: If the AI provider fails before a durable review batch result exists, `review_cursor` SHALL remain unchanged, no completed batch result SHALL be recorded, and AI review SHALL retry on the next invocation.
- Case B: If a durable review batch result exists but a crash occurs before finding application completes, resumption SHALL load the deterministic batch result, idempotently finish applying finding operations without re-invoking AI, and advance `review_cursor`.
- Case C: If finding application has completed but a crash occurs before `review_cursor` advances, resumption SHALL detect the existing batch result, verify finding revisions without duplication, and catch up `review_cursor`.
- Case D: If review completes with `NO_FINDING`, the durable batch result SHALL record `NO_FINDING`, enabling `review_cursor` to advance safely without repeated AI calls or fake finding emission.
Upon provider recovery or subsequent Hermes invocation, Hermes SHALL resume processing unreviewed evidence from the review cursor without requiring a full-session reread.

#### Scenario: AI provider outage leaves continuous runtime and observer unaffected
- **WHEN** an AI provider rejects an API request or encounters a rate-limit error during live Hermes review
- **THEN** continuous runtime, log tailing, state reconciliation, and raw observer persistence continue uninterrupted, and `reader_cursor` continues tracking new evidence

#### Scenario: Case A provider failure before durable review batch result leaves cursor unchanged
- **WHEN** an AI provider call times out or fails before `<review_batch_id>.json` is written
- **THEN** `review_cursor` remains unchanged, no batch result file is marked completed, and the batch remains pending for retry

#### Scenario: Case B durable review batch result exists resumes application without AI call
- **WHEN** `<review_batch_id>.json` is safely committed but the process crashes midway through updating `hermes_findings.jsonl`
- **THEN** upon restart Hermes reads the completed batch result, finishes applying finding operations without making another AI API call, and advances `review_cursor`

#### Scenario: Case C completed finding application with crash before cursor catches up idempotently
- **WHEN** all finding updates from a review batch are journaled to disk but a crash occurs before `hermes_review_cursor.json` is updated
- **THEN** on resume the system encounters the completed batch result, detects that finding revisions are already applied (avoiding duplicate revisions or double counts), and advances `review_cursor` to the batch end sequence

#### Scenario: Case D review completed with NO_FINDING advances cursor without repeated AI review
- **WHEN** Hermes reviews an evidence batch and finds no anomalies or defects warranting findings
- **THEN** the durable batch result records `NO_FINDING` and `review_cursor` advances across the batch sequence range without re-invoking AI on subsequent runs

#### Scenario: Hermes resumes from preserved review cursor after provider outage without full reread
- **WHEN** Hermes is re-invoked after an AI provider outage or task termination
- **THEN** Hermes loads `hermes_review_cursor.json`, ingests only evidence past the recorded sequence watermark, processes pending markers, and avoids re-reading already-reviewed session evidence

### Requirement: Immediate Analysis Inception and Acceptance Duration Decoupling
Real-time development analysis SHALL initiate immediately at minute 0 upon observation session creation and SHALL build live findings continuously throughout gameplay. The requirement for at least 30 minutes of continuous real gameplay SHALL apply solely as the threshold for development-observation acceptance qualification and SHALL NOT delay or postpone the commencement of live analysis.

#### Scenario: Live findings generated in early session minutes before 30-minute mark
- **WHEN** an observation session has been running for 5 minutes and an anomaly occurs with a player marker
- **THEN** the live analyst evaluates the anomaly and registers a candidate finding immediately, without waiting for the 30-minute acceptance duration to elapse

#### Scenario: Session duration qualifies dataset acceptance independently of early findings
- **WHEN** a session completes 32 continuous minutes of gameplay with continuous live analysis
- **THEN** the session qualifies for technical development-observation acceptance review based on meeting the >=30-minute duration rule and integrity gates
