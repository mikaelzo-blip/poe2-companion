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
The review cursor SHALL maintain:
1. `review_contiguous_frontier`: the highest contiguous sequence for which all preceding evidence has been durably reviewed and accounted.
2. `reviewed_ahead_ranges`: compact array of sequence ranges (`[[start, end], ...]`) for batches that completed review ahead of the contiguous frontier (e.g. prioritized user markers).
3. `review_session_id`: active observation session ID.

When a later high-priority or marker batch finishes review before an earlier pending batch:
- `review_contiguous_frontier` SHALL NOT jump across the unreviewed sequence gap.
- The completed range SHALL be durably recorded in `reviewed_ahead_ranges` alongside canonical `ReviewBatchResult` persistence.
- When earlier pending batches finish review, `review_contiguous_frontier` SHALL advance contiguously through the completed-ahead ranges.
- Upon restart, the review cursor SHALL restore `reviewed_ahead_ranges`, preserving completed-ahead knowledge and preventing completed out-of-order batches from being re-sent to Hermes.

When an evidence batch contains items reviewed where no candidate finding is warranted, the review plane SHALL persist lightweight review-batch metadata recording the completed sequence range so `review_cursor` advances safely without generating fabricated findings.

#### Scenario: Later high-priority marker batch completes first without jumping review frontier
- **WHEN** review frontier is at sequence 100, pending routine batch covers 101..150, and high-priority marker batch 151..175 completes review first
- **THEN** `review_contiguous_frontier` remains at 100, `reviewed_ahead_ranges` records `[[151, 175]]`, and canonical `ReviewBatchResult` for 151..175 is durably stored

#### Scenario: Completion of older missing batch advances frontier through completed-ahead range
- **WHEN** review frontier is at 100 with `reviewed_ahead_ranges = [[151, 175]]`, and pending batch 101..150 finishes review
- **THEN** `review_contiguous_frontier` catches up and advances contiguously to 175, and range `[151, 175]` is absorbed from `reviewed_ahead_ranges`

#### Scenario: Process restart preserves reviewed-ahead ranges and prevents duplicate review requests
- **WHEN** the system restarts with `review_contiguous_frontier = 100` and `reviewed_ahead_ranges = [[151, 175]]`
- **THEN** `reviewed_ahead_ranges` is restored from `hermes_review_cursor.json`, and batch 151..175 is NOT generated as a review request again

#### Scenario: Batch with no findings advances review cursor via review-batch metadata
- **WHEN** Hermes completes a review cycle over 50 routine telemetry records with all 50 evidence items accounted and no findings
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
3. `hermes_reviewed_sequence`: Highest contiguous durably reviewed sequence frontier, displaying `review_lag = reader_latest_sequence - hermes_reviewed_sequence`. Status SHALL expose pending review requests, claimed requests, completed responses, bridge validation errors, and review batch counts.
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

#### Scenario: Live status reports filesystem bridge request and response metrics
- **WHEN** 2 review requests are pending, 1 is claimed, and 12 responses have been validated
- **THEN** live status reports `Review Requests: 2 pending, 1 claimed, 12 completed` with zero bridge errors

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

### Requirement: Filesystem Hermes AI Review Bridge and Immutable Review Request Generation
The companion live analysis layer SHALL decouple evidence processing from external AI providers using a durable filesystem review bridge, communicating with the actual Hermes agent through atomic, immutable request and claim-specific response artifacts without embedding AI provider credentials, client libraries, or LLM APIs in the companion.
For every pending review batch past the review frontier, the companion SHALL write an atomic, immutable review request artifact to `runtime/observations/<session>/live_analysis/review_requests/<review_batch_id>.json` using a temporary file (`.tmp`), flushing via `os.fsync`, and executing an atomic OS rename.
The request artifact SHALL be strictly immutable once published; the system SHALL NOT rewrite or mutate the request JSON file as a shared mutable state file.
The request artifact SHALL contain:
- `schema_version`: "1.0"
- `review_batch_id`: deterministic batch identifier
- `session_id`: active observation session ID
- `sequence_start`: contiguous start sequence
- `sequence_end`: contiguous end sequence
- `evidence_ids`: ordered array of source evidence IDs
- `high_priority_signals`: array of high-priority factual signal summaries
- `marker_refs`: array of manual user marker references
- `objective_refs`: array of objective decision references
- `notification_refs`: array of notification decision references
- `unknown_stale_refs`: array of persistent UNKNOWN/STALE state references
- `anomaly_refs`: array of sanitized parser anomaly references
- `existing_findings`: bounded, sanitized catalogue of existing logical findings for the session (containing `finding_id`, `category`, `classification`, `safe_summary`, `relevant_subject_or_key`, `evidence_count`, and `recent_evidence_refs`) without model scratchpads or chain-of-thought, enabling Hermes to select `UPDATE_FINDING` rather than duplicating findings
- `evidence_locations`: mapping of stream names and event IDs to local file paths and byte offsets
- `privacy_instructions`: explicit instruction forbidding reproduction of private chat, whispers, credentials, or tokens in review responses
- `created_at`: ISO-8601 UTC timestamp
The request artifact SHALL NOT copy unredacted private chat, whispers, or credentials.

The review bridge SHALL decouple transient claim/lease state from the immutable request. Hermes review runs SHALL acquire claims by atomically writing an immutable claim-specific artifact to `runtime/observations/<session>/live_analysis/review_claims/<review_batch_id>.<claim_id>.json` containing `schema_version: "1.0"`, `review_batch_id`, `claim_id`, `review_run_id`, `claimed_at`, and `lease_expires_at`. Claim artifacts SHALL NOT be shared multi-writer files: each Hermes review run SHALL publish its own atomic claim artifact, ensuring durable evidence of claimant identity is never overwritten. If a Hermes run requires heartbeat or lease renewal, it SHALL update only state belonging to its own claim (such as writing to `runtime/observations/<session>/live_analysis/review_claim_status/<review_batch_id>.<claim_id>.json` or an atomic self-owned status file), and SHALL NOT overwrite or alter another claimant's claim file.
The claim lease SHALL use a conservative initial duration (180s) or periodic heartbeat renewal, ensuring that slow provider or model reasoning cycles exceeding 60 seconds do not trigger premature claim expiration or false staleness.
The coordinator SHALL derive request lifecycle status (`PENDING`, `CLAIMED`, `RESPONSE_AVAILABLE`, `COMPLETED`, `FAILED_VALIDATION`, `RETRYABLE`) from coordinator-owned metadata and existing filesystem artifacts, and SHALL NOT mutate the request file.
A `CLAIMED` state alone SHALL NOT advance the review cursor or equate to completed review. If a claim lease expires without a response, the request SHALL be safely reclaimable without erasing old claim provenance.

The companion SHALL enforce a strict coverage invariant: a global observation sequence SHALL belong to AT MOST ONE canonical review request. Immutable review request ranges SHALL NEVER overlap across batches (e.g. 101–150, 151–200; never 101–150 and 140–175). When a high-priority user marker arrives, if its observation sequence already belongs to an existing canonical pending request, the system SHALL elevate the scheduling priority of that existing canonical request and SHALL NOT create an overlapping marker-specific request. If no request has yet been formed for the marker sequence, the companion SHALL form the next canonical non-overlapping request covering it according to deterministic batch partitioning, and mark that request high priority. Mutable scheduling priority (`NORMAL`, `HIGH_MARKER`, `HIGH_ERROR`) SHALL be coordinator-owned metadata stored separately from immutable requests, affecting review selection order without modifying request evidence ranges, review batch IDs, immutable request payloads, or review frontiers. Upon companion restart, the coordinator SHALL reconstruct canonical request coverage from disk before generating new requests, and SHALL NOT generate new requests for sequences already owned by PENDING, CLAIMED, RESPONSE_AVAILABLE, COMPLETED, or reviewed-ahead batches. Completed-ahead requests SHALL remain completed and SHALL NOT be regenerated.

#### Scenario: Atomic review request creation for pending batch
- **WHEN** the local reader contiguous frontier advances ahead of the review cursor
- **THEN** the companion forms a deterministic review batch, writes a `.tmp` file, flushes with fsync, and atomically renames it to `review_requests/<review_batch_id>.json` as an immutable artifact

#### Scenario: Request artifact remains immutable across claim and completion
- **WHEN** Hermes claims a review batch and later submits a completed response
- **THEN** `review_requests/<review_batch_id>.json` content remains bit-for-bit unchanged, transient claim state is recorded in `review_claims/<review_batch_id>.<claim_id>.json`, and completion state is recorded in coordinator metadata and canonical batch results

#### Scenario: Existing findings catalogue provided in review request
- **WHEN** prior batches have generated active session findings F1 and F2
- **THEN** subsequent review requests populate `existing_findings` with bounded summaries and IDs for F1 and F2 without chain-of-thought

#### Scenario: Duplicate batch ID does not create duplicate request artifact
- **WHEN** request generation evaluates an evidence range for which a request with the identical `review_batch_id` already exists
- **THEN** the existing request artifact is preserved without overwrite or duplicate creation

#### Scenario: Stale claim lease recovery with slow-reviewer tolerance
- **WHEN** a review request has been claimed but the reviewer stalls and the claim lease expires past the conservative 180-second window
- **THEN** the companion review bridge marks the request retryable and permits a resuming reviewer to acquire a new claim safely

#### Scenario: Two concurrent review runs create distinct claim artifacts without overwrite
- **WHEN** task A claims a batch with claim ID `clm_A` and task B later claims the same batch with claim ID `clm_B`
- **THEN** both `review_claims/<batch_id>.clm_A.json` and `review_claims/<batch_id>.clm_B.json` exist simultaneously on disk, preserving durable provenance for both claimants

#### Scenario: Marker within existing pending request elevates request priority without overlapping batch
- **WHEN** marker sequence 175 arrives while canonical request covering 151–200 is already pending
- **THEN** the coordinator elevates the scheduling priority of request 151–200 to `HIGH_MARKER` without creating an overlapping marker request

#### Scenario: Marker outside existing coverage creates next canonical non-overlapping batch
- **WHEN** marker sequence 220 arrives when current coverage ends at sequence 200
- **THEN** the coordinator creates the next canonical non-overlapping request covering 201–250 according to deterministic partitioning and marks it `HIGH_MARKER`

#### Scenario: Restart reconstructs canonical request coverage and prevents duplicate request generation
- **WHEN** the companion restarts while request 101–150 is pending and request 151–200 is completed-ahead
- **THEN** restart loads canonical coverage, preserves completed-ahead status for 151–200, keeps request 101–150 discoverable, and refuses to generate duplicate requests for sequences 101–200

#### Scenario: Self-owned lease renewal updates only claimant's own status file
- **WHEN** Hermes task with claim ID `clm_A` renews its claim lease
- **THEN** task A writes only `review_claim_status/<batch_id>.clm_A.json` without modifying or overwriting any other claimant's claim or status file

#### Scenario: Pending review requests survive process restart
- **WHEN** the local analyzer or continuous runtime restarts while review requests remain pending
- **THEN** existing request files in `review_requests/` remain intact and unreviewed sequences are discovered upon resume

### Requirement: Structured Review Response, Ingress Validation, and Concurrency Arbitration
The actual Hermes agent SHALL communicate review findings exclusively by atomically writing a claim-specific structured review response candidate artifact to `runtime/observations/<session>/live_analysis/review_responses/<review_batch_id>.<claim_id>.json` via temporary file, fsync, and atomic rename.
The response candidate artifact SHALL contain:
- `schema_version`: "1.0"
- `review_batch_id`: matching pending request batch ID
- `session_id`: matching observation session ID
- `sequence_start`: matching start sequence
- `sequence_end`: matching end sequence
- `accounted_evidence_ids`: array of evidence IDs durably reviewed and accounted as part of this batch
- `claim_id`: matching the claimant's active claim ID
- `review_run_id`: identifier of the active Hermes review run
- `reviewed_at`: ISO-8601 UTC timestamp
- `operations`: array of finding operations (`CREATE_FINDING`, `UPDATE_FINDING`, `NO_FINDING`)

Finding operations SHALL conform to strict identity and field models:
1. `CREATE_FINDING`: Hermes externalizes `category`, canonical `semantic_issue_key`, `classification`, `safe_summary`, supporting `evidence_refs`, `occurrence_count_delta`, and optional corroboration notes. The companion derives and assigns the stable logical `finding_id`.
2. `UPDATE_FINDING`: Hermes MUST provide an explicit `target_finding_id` referencing an existing logical finding from the session's `existing_findings` catalogue. Hermes MAY provide an updated summary, updated classification, corroboration note, and delta counts. Reworded semantic keys SHALL NOT create duplicate findings.
3. `NO_FINDING`: emitted when evidence is reviewed but indicates no actionable defect or anomaly. Supporting finding `evidence_refs` MAY be empty or a subset, but `accounted_evidence_ids` in the envelope MUST account for all requested evidence.
Hidden chain-of-thought, scratchpads, and raw model thoughts SHALL NOT be persisted in the response file.

The companion review bridge coordinator MUST NOT blindly trust review response files. Before promoting any candidate into a canonical result, the bridge SHALL execute strict ingress validation:
1. Matching request and claim provenance: matching immutable review request exists; matching claim artifact exists at `runtime/observations/<session>/live_analysis/review_claims/<review_batch_id>.<claim_id>.json`; `claim.review_batch_id` matches request; `response.claim_id` matches claim; and `response.review_run_id` matches claim.
2. Schema conformity: matches `ReviewResponseEnvelope` model schema.
3. Batch ID and session match: `review_batch_id` and `session_id` match the expected pending batch and active session.
4. Sequence range match: `sequence_start` and `sequence_end` match the request bounds.
5. Full evidence accounting: `set(response.accounted_evidence_ids) == set(request.evidence_ids)`. If evidence coverage is incomplete (e.g. 10 evidence items requested, but only 2 accounted), the response SHALL be rejected, the cursor SHALL NOT advance, and the request SHALL remain retryable. Finding `evidence_refs` MAY be a subset of `accounted_evidence_ids`. Duplicate accounted evidence IDs SHALL be rejected. Unknown evidence IDs not present in the request SHALL be rejected.
6. Finding identity integrity: for `UPDATE_FINDING`, `target_finding_id` MUST exist in the current session, match compatible categories, and contain no path traversal or arbitrary filesystem characters.
7. Operation and classification validity: all operations belong to `{CREATE_FINDING, UPDATE_FINDING, NO_FINDING}` and classifications match the approved taxonomy enum.
8. Targeted privacy & security validation:
   - Safe summaries and notes SHALL NOT contain directory traversal characters (`..`, absolute paths outside workspace).
   - Targeted detection SHALL reject actual sensitive structures: PoE chat/whisper prefixes (`@From`, `@To`, `From: `, `To: `, `Guild: `, `Party: `, `Trade: `, line-start chat markers `^[@#\$%&]`), credentials (`sk-`, `ghp_`, `Bearer `, `ey...`, passwords, session tokens), secrets, and unbounded raw log reproductions.
   - Text fields SHALL satisfy length bounds: `safe_summary` <= 300 characters, `corroboration_note` <= 500 characters, `semantic_issue_key` <= 100 characters.
   - Broad character blacklists SHALL NOT be used: safe technical text containing percent signs (e.g. `"Flameblast quality remained below 40%"`) or normal punctuation (`!`, `$`, `#`, `&`) SHALL be valid and accepted.

Concurrency Arbitration:
When multiple response candidates exist (e.g. slow task A returns after task B claims the batch), the coordinator SHALL arbitrate deterministically:
- The first valid candidate response promoted to canonical `ReviewBatchResult` (`review_batches/<review_batch_id>.json`) wins.
- The coordinator SHALL distinguish claim lease eligibility for starting/continuing new work from the valid provenance of a response already produced: a stale claim MAY still produce a response, and an otherwise valid completed response SHALL NOT be rejected solely because its lease expired milliseconds before publication, provided no competing candidate has already been promoted.
- Once one valid candidate is promoted to canonical `ReviewBatchResult`, all later or competing candidate responses for that `review_batch_id` SHALL be quarantined or safely ignored without overwriting or corrupting the canonical result. No second candidate MAY change the canonical result.
- If validation fails, `hermes_review_cursor.json` SHALL NOT advance, a bridge error diagnostic SHALL be logged, and the batch SHALL remain retryable.

#### Scenario: Full evidence accounting accepts response with subset finding evidence refs
- **WHEN** a request contains 10 evidence IDs, response lists all 10 in `accounted_evidence_ids`, and finding operation cites 2 in `evidence_refs`
- **THEN** the response passes evidence accounting validation and is promoted to canonical `ReviewBatchResult`

#### Scenario: Incomplete evidence accounting rejects response and holds cursor
- **WHEN** a request contains 10 evidence IDs, but the response lists only 2 in `accounted_evidence_ids`
- **THEN** the bridge rejects the response for incomplete accounting, does not advance `hermes_review_cursor.json`, and retains the request as retryable

#### Scenario: NO_FINDING accepted when all evidence accounted
- **WHEN** a request contains 15 evidence IDs and response contains a single `NO_FINDING` operation with all 15 listed in `accounted_evidence_ids`
- **THEN** the response is accepted, `ReviewBatchResult` records the batch with zero findings, and review cursor advances

#### Scenario: Duplicate or unknown evidence ID in response rejected
- **WHEN** a response contains duplicate evidence IDs in `accounted_evidence_ids` or an ID not present in the request
- **THEN** the bridge rejects the response, logs an ingress validation error, and refuses to advance the cursor

#### Scenario: Corroborating batch updates existing finding by target finding ID
- **WHEN** batch 1 creates finding F1, and batch 2 receives F1 in `existing_findings` and emits `UPDATE_FINDING` with `target_finding_id = F1`
- **THEN** the coordinator updates F1 with new evidence and increments count without creating a duplicate finding F2, even if AI generated phrasing differs

#### Scenario: Update with nonexistent or invalid target finding ID rejected
- **WHEN** a response specifies `UPDATE_FINDING` with a `target_finding_id` not present in active session findings or containing path traversal characters
- **THEN** ingress validation rejects the response, does not advance the cursor, and marks the request retryable

#### Scenario: Unrelated issue legitimately creates second finding
- **WHEN** batch 2 discovers an unrelated defect distinct from F1
- **THEN** Hermes emits `CREATE_FINDING` for the new issue, and the coordinator creates stable finding F2 alongside F1

#### Scenario: First valid candidate response wins concurrent claim race
- **WHEN** task A claims a batch, stalls past lease expiry, task B claims the batch and submits candidate `<batch_id>.<claim_B>.json`, and task A later submits `<batch_id>.<claim_A>.json`
- **THEN** the coordinator promotes candidate B into canonical `ReviewBatchResult`, completes the batch, and safely ignores/quarantines late candidate A without corrupting the canonical result

#### Scenario: Response A validates against claim A and response B validates against claim B
- **WHEN** two distinct Hermes tasks A and B publish response candidates `<batch_id>.clm_A.json` and `<batch_id>.clm_B.json`
- **THEN** the coordinator independently validates candidate A against claim artifact `review_claims/<batch_id>.clm_A.json` and candidate B against `review_claims/<batch_id>.clm_B.json`

#### Scenario: Valid response produced under expired lease wins if no competitor promoted
- **WHEN** task A's claim lease expires shortly before publishing candidate `<batch_id>.clm_A.json`, and no other candidate has yet been promoted
- **THEN** the coordinator distinguishes response provenance from lease eligibility, accepts the valid candidate, and promotes it to canonical `ReviewBatchResult`

#### Scenario: Later valid response cannot replace canonical ReviewBatchResult
- **WHEN** candidate B was already promoted to canonical `ReviewBatchResult`, and candidate A subsequently arrives with valid accounting and schema
- **THEN** candidate A is quarantined/ignored and the canonical `ReviewBatchResult` remains strictly unchanged

#### Scenario: Technical engineering description with percent sign and punctuation accepted
- **WHEN** a response safe summary contains `"Flameblast quality remained below 40% (expected >=50% in maps)!"`
- **THEN** targeted privacy validation accepts the summary without triggering broad character blacklists

#### Scenario: Leaked private tokens or real chat prefixes rejected
- **WHEN** a response summary contains `@From PlayerName: hey` or an API token pattern `«redacted:sk-…»`
- **THEN** the ingress validator rejects the response, logs a privacy validation error, and does not advance the review cursor

### Requirement: Subordinate Review Cursor Ownership and Canonical Batch Result Promotion
The actual Hermes agent SHALL NOT directly write, modify, or delete `hermes_review_cursor.json` or mutate continuous runtime state or `CharacterState`. Hermes SHALL communicate review outcomes strictly by writing its claim-specific candidate file to `review_responses/<review_batch_id>.<claim_id>.json`.
The companion review bridge coordinator SHALL exclusively own `hermes_review_cursor.json` and canonical `ReviewBatchResult` artifacts (`review_batches/<review_batch_id>.json`).
Promotion from response candidate to canonical result SHALL occur strictly after:
1. Candidate file parses completely against `ReviewResponseEnvelope`.
2. All 8 ingress validation rules pass completely (including claim provenance, full evidence accounting, target finding validation, and targeted privacy).
3. Durable `ReviewBatchResult` is committed to `review_batches/<review_batch_id>.json` via atomic `.tmp` -> `fsync` -> rename.
4. Finding operations are idempotently applied to `hermes_findings.jsonl`.
5. Contiguous review frontier advances in `hermes_review_cursor.json` (absorbing any continuous ranges from `reviewed_ahead_ranges`).

#### Scenario: Companion bridge alone promotes candidate and advances cursor
- **WHEN** Hermes writes valid candidate `review_responses/<review_batch_id>.<claim_id>.json`
- **THEN** the coordinator validates the candidate, writes canonical `ReviewBatchResult`, applies findings, and updates `hermes_review_cursor.json`

#### Scenario: Direct external modification of cursor detected and rejected
- **WHEN** an unexpected process or corrupted task modifies `hermes_review_cursor.json` ahead of validated batch results
- **THEN** the bridge verifies that every sequence up to the cursor has a corresponding canonical `ReviewBatchResult`, halting progress if unvalidated sequences are detected

### Requirement: Project-Local Live Observation Hermes Workflow and Write Allowlist
The repository SHALL maintain a project-local Hermes workflow for live development observation (`"Start live development observation"`).
When live observation is active, Hermes SHALL strictly adhere to the Hermes Write Allowlist:
- **Approved Write Allowlist**:
  1. `runtime/observations/<session>/live_analysis/review_claims/<review_batch_id>.<claim_id>.json` (immutable claim artifact)
  2. Optional `runtime/observations/<session>/live_analysis/review_claim_status/<review_batch_id>.<claim_id>.json` (self-owned lease renewal artifact)
  3. `runtime/observations/<session>/live_analysis/review_responses/<review_batch_id>.<claim_id>.json` (review response candidate)
  4. `runtime/observations/<session>/live_analysis/hermes_review_status.json` (Hermes heartbeat/status)
- **Strictly Forbidden Writes**:
  Hermes SHALL NOT edit, create, or delete:
  - companion source (`companion/**`)
  - tests (`tests/**`)
  - OpenSpec artifacts (`openspec/**`)
  - objective rules (`rules/**` or build rules)
  - CharacterState
  - observer evidence (`runtime/observations/<session>/*.jsonl`)
  - reader state (`reader_state.json`)
  - review cursor (`hermes_review_cursor.json`)
- **Approved Read Allowlist**:
  Hermes MAY read:
  - local evidence files (`events.jsonl`, `state_deltas.jsonl`, `objective_traces.jsonl`, etc.) at specified file locations and byte offsets
  - bounded `Client.txt` byte ranges around known event offsets when deeper engine context is required
  - review request files (`review_requests/<review_batch_id>.json`)

When invoked, the actual Hermes agent SHALL:
1. Locate the active observation session descriptor in `runtime/observations/active_session.json` or the newest active session directory.
2. Inspect `live_analysis/review_requests/` for pending requests, prioritizing user manual markers (`USER_MARKER`), runtime `ERROR` records, and objective transition churn.
3. Read `existing_findings` from the request to determine if candidate issues corroborate known findings.
4. Acquire or refresh an immutable claim artifact in `review_claims/<review_batch_id>.<claim_id>.json` (and write to self-owned status if renewing lease).
5. Read associated persisted evidence files and optional bounded `Client.txt` windows.
6. Perform genuine AI reasoning using the active model without delegating to synthetic heuristics.
7. Formulate structured finding operations: emit `UPDATE_FINDING` with `target_finding_id` when corroborating known findings, `CREATE_FINDING` for novel issues, or `NO_FINDING` when clean.
8. Ensure all requested evidence IDs are listed in `accounted_evidence_ids`.
9. Atomically write the candidate response to `live_analysis/review_responses/<review_batch_id>.<claim_id>.json`.
10. Update Hermes review heartbeat in `hermes_review_status.json`.

#### Scenario: Hermes workflow claims and processes marker request within write allowlist
- **WHEN** user submits marker and invokes live observation workflow
- **THEN** Hermes writes `review_claims/<batch_id>.<claim_id>.json`, reads evidence, writes candidate `review_responses/<batch_id>.<claim_id>.json`, updates heartbeat, and touches no code or spec files

#### Scenario: Attempted source or spec modification forbidden by workflow contract
- **WHEN** Hermes identifies a parser defect in `Client.txt` during live review
- **THEN** Hermes records the finding in its structured response for post-session engineering review, and does NOT edit `companion/` or `openspec/` files during active observation

#### Scenario: Bounded raw Client.txt inspection without privacy leakage
- **WHEN** Hermes inspects a bounded range of `Client.txt` to investigate a novel parser anomaly
- **THEN** Hermes reasons over engine debug context, redacts ambient player chat, and outputs a response citing only sanitized signatures and safe summaries

### Requirement: Review Bridge Coordinator Architecture and Elimination of Synthetic AI Heuristics
The system SHALL eliminate synthetic heuristics (`if USER_MARKER: CREATE else NO_FINDING`) from `LiveReviewEngine` by refactoring it into `ReviewBridgeCoordinator`.
The bridge coordinator SHALL manage the deterministic filesystem review lifecycle: generating atomic immutable review requests from unreviewed reader evidence, polling for claim-specific review response candidates, running the 8-point ingress validation gate, arbitrating concurrent candidates, committing canonical `ReviewBatchResult` records, and advancing `hermes_review_cursor.json`.
The system SHALL provide a deterministic test adapter (`TestReviewResponder`) strictly for offline automated testing and CI verification, enabling repeatable tests without invoking external LLMs or embedding fake AI logic in production code.

#### Scenario: Production review bridge coordinates filesystem review lifecycle
- **WHEN** `ReviewBridgeCoordinator` executes during live gameplay
- **THEN** it generates `review_requests/<review_batch_id>.json` and waits for responses from the external Hermes agent without synthesizing fake AI findings

#### Scenario: Offline test adapter simulates responses deterministically for CI
- **WHEN** automated tests execute `ReviewBridgeCoordinator` with `TestReviewResponder`
- **THEN** the adapter generates valid response files deterministically, exercising the full validation, batch result, and cursor advancement pipeline without external AI dependencies
