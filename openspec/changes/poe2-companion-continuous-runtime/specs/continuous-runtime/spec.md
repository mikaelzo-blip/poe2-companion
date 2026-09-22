# Spec Delta: Continuous Runtime

## Purpose

Provides a lightweight, passive, continuous foreground runtime loop that coordinates non-invasive process detection, bounded incremental log tailing with stable stream generation and provenance, idempotent state reconciliation, change-driven objective derivation, bounded safe-zone notification delivery, and crash-consistent checkpoint persistence for an active Path of Exile 2 gaming session without background daemons, network services, or game input.

## ADDED Requirements

### Requirement: Continuous Foreground Runtime Loop
The system SHALL provide a continuous foreground orchestration loop executing a periodic polling cycle: inspecting game process presence, incrementally reading newly appended `Client.txt` lines, normalizing observations, updating character state, deriving objectives on state changes, dispatching notifications, and flushing session history. The loop SHALL run in the terminal foreground, SHALL NOT spawn background daemons or Windows services, and SHALL support clean, graceful shutdown upon receiving `SIGINT` (Ctrl+C) or `SIGTERM`.

#### Scenario: Normal foreground execution cycle
- **WHEN** user starts the continuous runtime in the foreground
- **THEN** the loop executes periodic poll cycles at the configured interval, coordinating process detection, log ingestion, and state updates without detaching into a background daemon

#### Scenario: Graceful shutdown on Ctrl+C
- **WHEN** user issues an interrupt signal (`SIGINT` / Ctrl+C) while the runtime is active
- **THEN** the loop terminates the current cycle, flushes pending state and journey logs to disk, marks checkpoint termination as clean, and exits cleanly with status code 0

#### Scenario: Bounded polling interval prevents busy looping
- **WHEN** the runtime loop executes while the game is idle or running
- **THEN** the loop sleeps for the configured polling interval (defaulting to 1.0 second) between poll cycles, avoiding CPU-spinning or unbounded execution frequency

### Requirement: Session Lifecycle and Bounded Exit Drain
The system SHALL manage game session lifecycles through four explicit discrete states: `IDLE`, `GAME_RUNNING`, `SESSION_ACTIVE`, and `GAME_EXITED`. The runtime SHALL transition to `GAME_RUNNING` when game process detection succeeds, transition to `SESSION_ACTIVE` upon receiving the first game observation or log activity for the active session, transition to `GAME_EXITED` when process detection reports process termination, and return to `IDLE` after finalizing session artifacts and checkpoints. When process termination is detected, the runtime SHALL execute a bounded final log drain on `Client.txt` before finalizing session recaps and checkpoints.

#### Scenario: Process launch initiates session lifecycle
- **WHEN** the runtime detects an active Path of Exile 2 executable while in `IDLE` state
- **THEN** the runtime transitions state to `GAME_RUNNING` and initializes session metadata

#### Scenario: First game observation activates session
- **WHEN** the runtime ingests an area transition or level-up event while in `GAME_RUNNING` state
- **THEN** the runtime transitions state to `SESSION_ACTIVE` and associates active session records

#### Scenario: Process exit performs bounded log drain before finalization
- **WHEN** the monitored game process terminates while in `SESSION_ACTIVE` or `GAME_RUNNING` state
- **THEN** the runtime performs a bounded final read of newly appended `Client.txt` records, persists final state and checkpoint artifacts, records session duration, and transitions to `GAME_EXITED`

#### Scenario: Clean return to idle awaiting subsequent launches
- **WHEN** session finalization completes following game process exit
- **THEN** the runtime resets in-memory active session markers and transitions back to `IDLE` state to monitor for subsequent game launches

### Requirement: Log File Identity, Stream Epoch, and Tail Baselines
The system SHALL maintain a lightweight file fingerprint (combining normalized path, creation metadata where reliable, and initial prefix header bytes) and a durable `stream_epoch` integer in persisted checkpoints to reliably distinguish normal append growth, in-place file truncation, and replaced or rotated log files. Observation source stream identity SHALL be constructed as `file_fingerprint_id:epoch_N`. When in-place file truncation is detected (same fingerprint but file size less than saved offset), the runtime SHALL increment `stream_epoch`, reset the read offset to 0, and persist the new epoch in the checkpoint so newly generated observation identities never collide with pre-truncation observations. When file replacement is detected, the runtime SHALL initialize a new stream epoch. If the log file is temporarily missing, the runtime SHALL enter a recoverable unavailable state and re-fingerprint upon file reappearance. If file identity cannot be resolved unambiguously, the runtime SHALL conservatively allocate a new stream epoch and re-anchor its read boundary.

#### Scenario: Normal append preserves stream epoch
- **WHEN** the log file matches the persisted fingerprint and its current size is greater than or equal to the saved offset
- **THEN** the runtime preserves the existing stream epoch and continues reading from the persisted byte offset

#### Scenario: In-place truncation increments stream epoch and generates distinct identities
- **WHEN** the log file matches the persisted fingerprint but its current size is strictly less than the persisted byte offset
- **THEN** the runtime increments `stream_epoch`, resets its read offset to 0, persists the new epoch in the checkpoint, and ensures subsequent events at offset 0 produce distinct observation identities from pre-truncation events

#### Scenario: Replaced file with identical prefix cannot reuse old stream epoch
- **WHEN** a newly created or rotated `Client.txt` is detected at the same path with matching header bytes but distinct file creation or inode metadata
- **THEN** the runtime treats the file as a replacement, allocates a new stream epoch, and re-anchors the read boundary safely according to active runtime mode

#### Scenario: Missing log file enters recoverable polling state
- **WHEN** `Client.txt` is temporarily missing or unreadable during a polling tick
- **THEN** the runtime logs a recoverable warning, retains the existing checkpoint unchanged, and polls again on the subsequent tick without crashing

#### Scenario: Reappearing log file is re-fingerprinted before resume
- **WHEN** `Client.txt` reappears after being reported missing
- **THEN** the runtime executes a complete fingerprint check against the persisted checkpoint before resuming read operations

#### Scenario: Ambiguous identity conservatively creates new stream generation
- **WHEN** file metadata or header bytes cannot be verified unambiguously
- **THEN** the runtime conservatively allocates a new stream epoch, logs an operational warning, and re-anchors the read boundary rather than blindly seeking to an obsolete byte offset

### Requirement: Crash Consistency, Durable Idempotency, and Checkpoint Semantics
The system SHALL implement an at-least-once log consumption model with idempotent state reconciliation, durable counted-event watermark tracking, and deterministic dirty-on-start checkpoint sequencing. Every consumed log observation SHALL possess a stable source identity incorporating stream epoch (`source_stream_id:start_offset:end_offset:event_type`). The pipeline SHALL execute in strict sequential order: read bounded batch -> normalize observations with stable source identity -> reconcile character state idempotently -> append/deduplicate durable journey events -> compute consolidated objective/notification side effects -> persist state via canonical public store API -> persist checkpoint offset, file fingerprint, stream epoch, and termination status ONLY after durable state and history writes succeed.

Before processing ANY new log observation, runtime startup SHALL resolve its startup boundary and recovery policy, acquire runtime writer ownership, and durably persist checkpoint metadata with `clean_shutdown = False`. Only AFTER that durable write succeeds MAY the ingestion loop process log records. If the runtime terminates unexpectedly, `clean_shutdown` remains `False`, ensuring the subsequent startup executes crash-recovery semantics. On graceful shutdown, the runtime SHALL execute a bounded final log drain, durably persist `CharacterState` and journey history, persist the final checkpoint offset, and only then update the checkpoint with `clean_shutdown = True` and `clean_shutdown_at`. If writing the clean termination marker fails, the next startup SHALL conservatively treat the state as unclean crash recovery.

Non-idempotent counters (specifically `death_count`) SHALL be made durable and replay-idempotent by maintaining a durable per-counted-effect source watermark (`last_counted_death_stream_id` and `last_counted_death_end_offset` in `death_count.evidence_refs`) persisted atomically with the counter value within canonical `CharacterState`. Replaying an event whose end offset is less than or equal to the watermark for the same source stream SHALL be a no-op leaving the counter unchanged. When a new death observation with an end offset strictly greater than the watermark arrives from the same stream, the reconciler SHALL apply the event exactly once, increment the counter, and advance the watermark to the new event end offset. When a new stream epoch arrives, the reconciler SHALL establish a new counted-event watermark for that epoch. Naturally idempotent replacements (such as zone, act, and process state) and monotonic values (such as character level) SHALL NOT use unnecessary watermark machinery.

The checkpoint SHALL record lifecycle termination metadata (`clean_shutdown: bool`, `clean_shutdown_at: str | None`, `run_id: str`) to distinguish unclean crashes from clean graceful shutdowns. On startup following an unclean shutdown, the runtime SHALL resume from the saved checkpoint offset with at-least-once replay. On startup following a clean shutdown while the game is already running, normal live mode SHALL seek to the current EOF and skip the offline backlog as unobserved to prevent alert storms. If the companion starts before game launch, an idle baseline EOF SHALL be established.

#### Scenario: Runtime startup marks checkpoint dirty before first consumed event
- **WHEN** the runtime initializes following a previous clean checkpoint
- **THEN** the runtime durably persists the checkpoint with `clean_shutdown = False` before ingesting or processing any log observation from `Client.txt`

#### Scenario: Runtime crash after ingestion leaves checkpoint unclean for recovery
- **WHEN** the runtime crashes or is terminated after ingesting observations
- **THEN** `clean_shutdown` remains `False` in the checkpoint, requiring the next startup to execute crash-recovery semantics

#### Scenario: Graceful shutdown marks clean only after final state and checkpoint persistence
- **WHEN** the runtime executes graceful shutdown on interrupt signal
- **THEN** the runtime drains remaining records, persists durable `CharacterState` and history, persists the current checkpoint offset, and only then writes `clean_shutdown = True` and `clean_shutdown_at`

#### Scenario: Batch of >100 death events replayed after crash is counted exactly once
- **WHEN** a batch containing over 100 death observations is applied, character state with watermark is persisted, a crash occurs before checkpoint persistence, and the entire batch is replayed from the prior checkpoint
- **THEN** all replayed death observations have end offsets less than or equal to the durable watermark for that stream, leaving the total death count unchanged without double-counting

#### Scenario: Distinct death events advance watermark and increment counter
- **WHEN** multiple distinct death log records with strictly increasing byte offsets are processed within a source stream
- **THEN** each distinct death observation increments the death counter by one and advances the durable source watermark to that observation's end offset

#### Scenario: Counted-event watermark updates on stream epoch change
- **WHEN** a log file truncation or replacement triggers a new stream epoch and subsequent death events arrive in the new epoch
- **THEN** the reconciler establishes a new counted-event watermark for the new stream epoch and increments the counter appropriately

#### Scenario: Counter value and event watermark survive process restart together
- **WHEN** character state is saved with an incremented death count and updated watermark, and the process restarts
- **THEN** reloading `CharacterState` restores both the counter value and the exact source watermark atomically

#### Scenario: Clean shutdown followed by restart while game running skips backlog
- **WHEN** the runtime starts after a previous clean shutdown (`clean_shutdown = True`) and Path of Exile 2 is already running
- **THEN** normal live mode seeks to the current EOF of `Client.txt`, logs the offline backlog as unobserved, and suppresses live notifications for events occurring during the offline gap

#### Scenario: Companion starts before game captures launch records from idle baseline
- **WHEN** the runtime starts in `IDLE` state before Path of Exile 2 is launched
- **THEN** the runtime records an initial baseline EOF offset and consumes all log records written after that baseline when the game launches

#### Scenario: Checkpoint never advances past failed durable persistence
- **WHEN** an error occurs while writing character state or appending journey history entries during a poll batch
- **THEN** the runtime aborts the batch before saving the checkpoint, ensuring the checkpoint offset does not advance past unpersisted state changes

#### Scenario: Replay of identical observation preserves deduplicated journey history
- **WHEN** an observation with a previously recorded stable source identity is processed again during replay or backfill
- **THEN** the journey history logger identifies the existing entry by source identity and avoids writing a duplicate line

### Requirement: Canonical Single-Writer Lease Ownership and State Persistence
The continuous runtime SHALL act as the single canonical state writer during an active session and SHALL establish exclusive writer ownership by acquiring and holding an exclusive OS file lock (`runtime/writer_lease.lock`) for the entire lifetime of the continuous runtime process, utilizing the project's existing Windows `StateLock` mechanism (`msvcrt.locking` with non-blocking exclusive lock). The OS lock SHALL serve as the sole authority for writer ownership; diagnostic metadata (`runtime/writer_lease.json` recording owner PID, run ID, acquired timestamp, heartbeat timestamp, and target character ID) SHALL NOT independently grant writer ownership.

When multiple processes attempt to acquire writer ownership concurrently, acquisition SHALL be atomic: exactly one process SHALL acquire the OS lock on `runtime/writer_lease.lock`, and the competing process SHALL immediately fail lock acquisition and refuse execution with `RUNTIME_WRITER_ACTIVE` without check-then-create races. All CharacterState-mutating CLI commands (`companion runtime start`, `companion session tail`, `companion state init`) SHALL participate in this writer-ownership contract and SHALL attempt exclusive acquisition of `runtime/writer_lease.lock` before performing any read-modify-write operation on `CharacterState`. If the continuous runtime holds the lock, the mutating command SHALL refuse execution with `RUNTIME_WRITER_ACTIVE` without altering disk state. Read-only inspection commands (`state inspect`, `objectives list`, `intelligence audit`, `gear status`, `runtime status`) and unrelated stores that do not mutate `CharacterState` SHALL NOT acquire the writer lock and SHALL remain fully permitted without contention.

Crash recovery SHALL rely on automatic OS lock release: when a runtime process crashes or terminates unexpectedly, the operating system SHALL automatically release `runtime/writer_lease.lock`. A subsequent process MAY acquire the OS lock immediately even if stale metadata in `runtime/writer_lease.json` contains an old, dead, or reused PID. After acquiring the OS lock, the new owner SHALL inspect any stale metadata for diagnostics, log recovery details, and replace the metadata with its own run ID and owner PID. Stale metadata SHALL NOT grant ownership without the OS lock, and stale metadata SHALL NOT permanently block a new owner. If `runtime/writer_lease.lock` is actively held by an existing process, the lock SHALL NOT be stolen, preempted, or deleted regardless of heartbeat staleness or elapsed time.

During graceful runtime shutdown, the shutdown sequence SHALL execute strictly in order: bounded final log drain -> persist durable `CharacterState` and journey history -> persist final checkpoint offset -> mark `clean_shutdown = True` and `clean_shutdown_at` in checkpoint -> update final lease metadata if needed -> release lifetime OS writer lock (`runtime/writer_lease.lock`) -> exit process. The runtime SHALL NOT delete or release the writer lock before final durable state and checkpoint work is complete. The runtime SHALL interact with state storage exclusively through the public `CharacterStateStore.save_character(state)` API without calling private store persistence methods.

#### Scenario: Concurrent runtimes attempt start with atomic OS lock exclusivity
- **WHEN** two continuous runtime processes attempt to start concurrently for the same runtime workspace
- **THEN** exactly one runtime process acquires `runtime/writer_lease.lock`, while the competing runtime immediately fails lock acquisition and exits with error code `RUNTIME_WRITER_ACTIVE` without check-then-create race conditions

#### Scenario: Mutating CLI command participates in writer lease and is refused during active runtime
- **WHEN** a CLI command attempting to mutate `CharacterState` (`companion session tail` or `companion state init`) executes while an active continuous runtime holds `runtime/writer_lease.lock`
- **THEN** the mutating command fails to acquire `runtime/writer_lease.lock` before reading or modifying state, and halts immediately with `RUNTIME_WRITER_ACTIVE` error without modifying character state files

#### Scenario: Read-only inspection allowed while runtime writer lock is held
- **WHEN** a read-only command (`companion state inspect`, `companion objectives list`, or `companion runtime status`) executes while the continuous runtime holds the lifetime OS writer lock
- **THEN** the command successfully inspects and displays current state without contention, lock errors, or mutator refusal

#### Scenario: Runtime crash releases OS writer lock automatically
- **WHEN** an active continuous runtime process crashes or is killed unexpectedly while holding `runtime/writer_lease.lock`
- **THEN** the operating system automatically releases the file lock on `runtime/writer_lease.lock`, allowing a subsequent runtime or mutator to acquire writer ownership immediately upon restart

#### Scenario: Stale metadata with dead or reused PID cannot block new writer owner
- **WHEN** a previous runtime crashed leaving stale `runtime/writer_lease.json` metadata containing a terminated or OS-reused PID, and a new runtime process starts
- **THEN** the new process successfully acquires `runtime/writer_lease.lock`, inspects stale metadata for diagnostic logging, and replaces `runtime/writer_lease.json` with new owner metadata without being blocked by the stale PID

#### Scenario: Stale metadata cannot grant ownership without OS lock
- **WHEN** a process inspects `runtime/writer_lease.json` containing metadata indicating an active writer but the corresponding OS lock `runtime/writer_lease.lock` is not held
- **THEN** the metadata alone does not grant ownership, and the inspecting process recognizes that writer ownership requires holding `runtime/writer_lease.lock`

#### Scenario: Live OS lock cannot be stolen even with stale heartbeat
- **WHEN** an active continuous runtime holds `runtime/writer_lease.lock` but experiencing a temporary delay causes its heartbeat in `runtime/writer_lease.json` to exceed the staleness threshold
- **THEN** competing processes attempting to acquire writer ownership are blocked by the OS lock, and the active lease is not stolen or overridden

#### Scenario: Graceful shutdown releases writer lock only after final durable checkpoint
- **WHEN** the continuous runtime executes graceful shutdown upon receiving an interrupt signal
- **THEN** the runtime executes a bounded final drain, persists `CharacterState` and journey history, saves the final checkpoint offset, marks `clean_shutdown = True`, and only then releases `runtime/writer_lease.lock` before process exit

#### Scenario: No lost update from two concurrent mutators
- **WHEN** two mutator processes attempt concurrent read-modify-write operations on `CharacterState`
- **THEN** canonical single-writer locking on `runtime/writer_lease.lock` prevents concurrent mutation transactions, guaranteeing zero lost updates

#### Scenario: Runtime persists state through canonical public store interface
- **WHEN** character state is modified during a poll batch
- **THEN** the orchestrator invokes `CharacterStateStore.save_character(state)` to execute atomic file replacement, rolling backup updates, and lock management

### Requirement: Historical Backfill to Live Boundary
The system SHALL provide an explicit `--backfill` CLI option with a deterministic transition boundary to live gameplay. Upon launch with `--backfill`, the runtime SHALL record `startup_backfill_end_offset` equal to the file size of `Client.txt` at startup. For log records between byte 0 and `startup_backfill_end_offset`, the runtime SHALL parse lines, update state, and record journey history using original log timestamps while strictly suppressing live notification delivery. Once the read offset reaches `startup_backfill_end_offset`, the runtime SHALL transition to LIVE mode, restoring normal safe-zone notification delivery and live console event alerting for subsequent newly appended records.

#### Scenario: Backfill suppresses notifications up to deterministic boundary
- **WHEN** user starts the continuous runtime with the `--backfill` option
- **THEN** the runtime captures `startup_backfill_end_offset`, processes historical records up to that offset with original timestamps, and suppresses live notification delivery

#### Scenario: Backfill transition to live restores live alerting for new records
- **WHEN** the backfill read offset reaches `startup_backfill_end_offset` and new records are subsequently appended by the game
- **THEN** the runtime transitions to live mode and delivers safe-zone notifications for newly appended progression events according to standard live alerting policies

### Requirement: Batch Coalescing and Change-Driven Objective Derivation
The system SHALL process log batches as atomic reconciliation units: after reconciling all valid observations in a poll batch, the runtime SHALL derive a consolidated state-change set and execute at most one objective derivation cycle for the resulting state. If a poll cycle yields zero state changes, the runtime SHALL NOT recompute objectives, SHALL NOT rewrite `CURRENT_OBJECTIVE.json`, and SHALL NOT submit alerts to the notification manager.

#### Scenario: Multi-event batch coalesces objective derivation and notifications
- **WHEN** a single poll batch ingests multiple log events (such as multiple area transitions or level progression records)
- **THEN** the runtime reconciles all events into character state first, executes at most one consolidated objective evaluation, and emits only the final actionable notification

#### Scenario: State change triggers objective reevaluation and notification
- **WHEN** an ingested log event in a poll batch modifies character level or current zone
- **THEN** the runtime executes the objective pipeline, updates `CURRENT_OBJECTIVE.json`, and dispatches the top actionable objective to the notification manager

#### Scenario: Idle poll without state change suppresses objective reevaluation
- **WHEN** a poll cycle processes no new log events or only non-state log lines
- **THEN** the runtime skips objective reevaluation, avoids writing `CURRENT_OBJECTIVE.json`, and emits zero notifications

### Requirement: Bounded Safe-Zone Notification Delivery
The system SHALL enforce bounded in-memory queue management for safe-zone notification buffering. The notification queue SHALL be semantically deduplicated by objective and advisory identity (`dedupe_key`), ensuring that repeated identical pending objectives replace existing pending entries rather than accumulating without bound. In combat zones, non-critical alerts SHALL be buffered and flushed upon transition to a recognized town or hideout.

#### Scenario: Repeated objective replaces pending safe-zone entry
- **WHEN** a new objective derivation produces an advisory with an identical deduplication key to an already queued safe-zone alert
- **THEN** the notification queue replaces the existing entry or updates its payload without growing the queue length

#### Scenario: Combat zone buffers non-critical advisory until safe-zone entry
- **WHEN** an objective update produces a non-critical advisory while character is in a hostile area
- **THEN** the notification manager buffers the advisory without delivering to sinks until a subsequent zone transition to a recognized town or hideout occurs

#### Scenario: Safe-zone transition flushes deduplicated queue
- **WHEN** character transitions from a combat area to a recognized safe zone
- **THEN** the notification manager flushes all buffered alerts, delivering each deduplicated alert to active sinks and resetting the queue

### Requirement: Character Identity and Uncertainty Preservation
The system SHALL maintain character identity integrity and preserve uncertainty states. If the active character cannot be resolved from explicit CLI configuration or authoritative log evidence, the runtime SHALL retain character identity as `UNKNOWN`, SHALL NOT guess character names from weak heuristics or partial class matches, and SHALL NOT assign observations to incorrect character records. Observation uncertainty states (`UNKNOWN`, `STALE`, `CONFLICTING_EVIDENCE`) SHALL NOT be converted into corrective build advice or assumed build deficits.

#### Scenario: Unresolved character identity preserved as UNKNOWN
- **WHEN** log events occur but no active character is configured and log lines contain no resolvable character name
- **THEN** the runtime records observations to session history under `UNKNOWN` character identity without mutating existing named character profiles

#### Scenario: Confirmed character level-up updates matching profile
- **WHEN** a level-up event is parsed for character name matching the active character configuration
- **THEN** the runtime updates the active character state with verified provenance

### Requirement: Fault Isolation and Strictly Read-Only Access
The system SHALL enforce error boundaries around external and transient operations and SHALL access game log files strictly in read-only binary mode (`"rb"`). The runtime SHALL NOT open `Client.txt` in write, append, or update mode. Malformed log lines, temporary file locking on `Client.txt`, transient notification sink errors, or process polling exceptions SHALL be caught, logged as structured warnings, and isolated without crashing the continuous runtime loop or corrupting stored `CharacterState`.

#### Scenario: Malformed log line does not crash runtime
- **WHEN** `Client.txt` contains a corrupted byte sequence or malformed text line
- **THEN** the log reader decodes with replacement, discards or logs the line, and continues normal loop execution

#### Scenario: Notification sink error does not crash runtime
- **WHEN** a delivery sink raises an unhandled exception during notification dispatch
- **THEN** the notification manager captures the error, isolates the failure to the faulty sink, and allows the runtime loop to proceed unimpeded

#### Scenario: Read-only file access never opens log in write mode
- **WHEN** the runtime opens `Client.txt` for polling, tailing, or fingerprinting
- **THEN** the file access mode is strictly read-only binary (`"rb"`), ensuring zero modification to the game log file

### Requirement: Runtime Status File and Observability Contract
The system SHALL provide local CLI subcommands `companion runtime start` and `companion runtime status`. The continuous runtime SHALL periodically update a local atomic heartbeat file (`runtime/runtime_status.json`) recording process PID, lifecycle state, active session ID, game presence, last consumed offset, last heartbeat timestamp, and known character ID. The status command SHALL inspect this file, probe `runtime/writer_lease.lock` to determine whether the OS writer lock is actually owned, verify whether the recorded runtime PID is actively running, detect stale heartbeats, and report accurate operational status without requiring IPC sockets or background network services. The system SHALL distinguish between metadata claiming ACTIVE status and actual OS writer lock ownership; status metadata SHALL NOT control mutation safety.

#### Scenario: Foreground start displays structured lifecycle events
- **WHEN** user executes `companion runtime start` and game events occur
- **THEN** concise structured status lines are printed to the console indicating session lifecycle, zone changes, level changes, and notification dispatches

#### Scenario: Runtime status inspects active heartbeat file
- **WHEN** user executes `companion runtime status` while the continuous runtime is active
- **THEN** the command reads `runtime/runtime_status.json`, confirms the runtime PID is alive, verifies the writer lock is owned, and displays active lifecycle state and metrics

#### Scenario: Runtime status detects stale or terminated runtime process
- **WHEN** user executes `companion runtime status` when the runtime process has terminated unexpectedly or its heartbeat timestamp is older than the staleness threshold
- **THEN** the command reports the runtime status as NOT RUNNING or STALE alongside last known operational details

#### Scenario: Runtime status distinguishes metadata active from lock ownership
- **WHEN** `companion runtime status` inspects a runtime environment where `runtime_status.json` or `writer_lease.json` claims active status but `runtime/writer_lease.lock` is not held
- **THEN** the status command reports the runtime as STALE or NOT RUNNING based on lock and process reality rather than relying blindly on stale JSON metadata
