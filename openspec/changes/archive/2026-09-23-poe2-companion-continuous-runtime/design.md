# Design: Continuous Foreground Runtime for PoE2 Companion

## Context

The PoE2 Hermes Companion currently possesses individually verified modules for process detection (`companion.sensing.process_presence`), incremental byte-exact log tailing (`companion.sensing.client_log`), provenanced character state reconciliation (`companion.state.reconciliation`), objective derivation (`companion.objectives.runner`), safe-zone notification filtering (`companion.notifications.manager`), and append-only journey logging (`companion.state.history`). However, these operations are only callable via ad-hoc batch CLI subcommands (`evaluate`, `session tail`, `session status`).

This design establishes a single, passive, continuous foreground runtime orchestrator (`companion.runtime.orchestrator`) that connects these modules into an end-to-end event-driven loop while maintaining strict no-input compliance, zero background daemonization, robust crash-consistency semantics, resilient file identity tracking with durable stream epochs, and canonical single-writer state persistence.

See `proposal.md` for high-level motivation and `specs/continuous-runtime/spec.md` for formal behavioral contracts.

## Goals / Non-Goals

**Goals:**
- Provide a simple local foreground command (`companion runtime start`) that monitors an active PoE2 session until interrupted with `Ctrl+C`.
- Orchestrate a deterministic, single-threaded pipeline: process polling -> log tailing -> normalization with stable stream generation -> idempotent reconciliation with durable counter protection -> batch change coalescing -> objective derivation -> safe-zone notification dispatch -> state persistence via canonical public store API -> checkpoint persistence.
- Implement an explicit crash-consistency model based on simple at-least-once log consumption with idempotent state reconciliation, durable counted-event deduplication, and ordered checkpoint sequencing.
- Assign stable source identities to consumed observations derived from immutable log provenance and durable stream epochs (`file_fingerprint_id:epoch_N:start_offset:end_offset:event_type`) to prevent identity collisions after log truncation and eliminate duplicate journey history entries on replay.
- Implement a lightweight `Client.txt` file fingerprint (combining creation metadata, normalized path, and prefix header hash) and a 6-case decision table to reliably discriminate normal growth, file truncation, replaced/rotated files, missing files, reappearance, and ambiguous identities.
- Distinguish unclean crash recovery (resumes from checkpoint with at-least-once replay) from clean shutdown restart (anchors boundary at current EOF when game is running to prevent replaying offline gap as live alerts).
- Provide a deterministic historical `--backfill` to live boundary: capture `startup_backfill_end_offset` at launch, suppress notifications during historical replay (bytes 0 -> `startup_backfill_end_offset`), and restore normal live alerting for records appended past the boundary.
- Preserve canonical M1 single-writer architecture: runtime calls the public `CharacterStateStore.save_character(state)` API rather than private persistence methods.
- Implement batch coalescing to evaluate objectives at most once per poll batch and bounded exit log draining when the game process terminates.
- Implement a bounded safe-zone notification queue enforcing semantic deduplication keyed by objective identity to eliminate memory leaks during extended combat.
- Provide a local cross-process runtime status contract (`companion runtime status`) using an atomic heartbeat file (`runtime/runtime_status.json`) with PID liveness and staleness checks without sockets or HTTP servers.
- Preserve 100% compliance with read-only invariants: zero synthetic keyboard/mouse inputs, zero hooks, zero memory inspection, zero live process injection, and strictly read-only binary file access (`"rb"`).
- Ensure fault isolation: transient log parsing or notification sink errors must not crash the loop or corrupt character state.

**Non-Goals:**
- No background daemon services, Windows services, Docker containers, Redis, or microservices.
- No distributed two-phase commit (2PC) or fake database transaction engines.
- No crash-persistent exactly-once notification delivery (notification delivery across process crashes is best-effort and deduplicated during active runtime).
- No continuous automated screenshot capture, OCR, or computer vision in the background loop (MSS remains manual/opt-in).
- No full-file hashing of multi-megabyte `Client.txt` files on every poll tick.
- No GGG official OAuth/API live syncing (remains externally blocked; mock adapter remains test-only).
- No cross-process IPC or network server (status is read directly from local files in `runtime/`).
- No automatic character guessing or merging across differing character names.

## Proposed Architecture

```
+---------------------------------------------------------------------------------------------------+
|  Companion Runtime Loop [Held Lifetime Lock: runtime/writer_lease.lock (OS StateLock authority)]  |
|                         [Diagnostic Metadata: runtime/writer_lease.json (PID, RunId, Heartbeat)]  |
|                                                                                                   |
|  +--------------------+   ProcessTransition (with Bounded Exit Drain)  +------------------------+ |
|  |   ProcessMonitor   | ---------------------------------------------> | SessionLifecycleManager| |
|  +--------------------+                                                +------------------------+ |
|                                                                                     |             |
|  +--------------------+       Raw Lines with Byte Offsets                           v             |
|  |  ClientLogTailer   | ---------------------------------------------> +------------------------+ |
|  | (FileFingerprint,  |                                                | Observation Normalizer | |
|  |  StreamEpoch,      |                                                | (Stable Stream Gen ID: | |
|  |  ReadOnly 'rb')    |                                                |  fingerprint:epoch:    | |
|  +--------------------+                                                |  start:end:type)       | |
|                                                                        +------------------------+ |
|                                                                                     |             |
|                                                                            ObservationEvents      |
|                                                                            (Idempotent Batch)     |
|                                                                                     v             |
|                                                                        +------------------------+ |
|                                                                        | Provenanced Reconciler | |
|                                                                        | (Monotonic Levels,     | |
|                                                                        |  Durable Death Dedupe) | |
|                                                                        +------------------------+ |
|                                                                                     |             |
|                                                                        Consolidated State Delta   |
|                                                                                     v             |
|                                                                        +------------------------+ |
|                                                                        |  StateChangeTracker    | |
|                                                                        |  (Batch Coalescing)    | |
|                                                                        +------------------------+ |
|                                                                           /                  \    |
|                                                                 (If State Changed)       (No Chg) |
|                                                                       /                        \  |
|                                                                      v                          v |
|                                                      +------------------------+               [Skip]|
|                                                      |  ObjectiveRunner (M4)  |                   |
|                                                      +------------------------+                   |
|                                                                   |                               |
|                                                         TopActionableObjective                    |
|                                                                   v                               |
|                                                      +------------------------+                   |
|                                                      |  NotificationManager   |                   |
|                                                      |  (Bounded Queue,       |                   |
|                                                      |   Keyed Dedupe,        |                   |
|                                                      |   Backfill Suppress)   |                   |
|                                                      +------------------------+                   |
|                                                                   |                               |
|                                                         Console / Memory Sink                     |
|                                                                   v                               |
|                     Durable Step 1: State & Journey Flush                                         |
|                     +----------------------------------------------------+                        |
|                     | CharacterStateStore.save_character(state)          |                        |
|                     | JourneyHistoryLogger.record_event() (Deduplicated) |                        |
|                     +----------------------------------------------------+                        |
|                                              |                                                    |
|                                              | (Only after Step 1 succeeds)                       |
|                                              v                                                    |
|                     Durable Step 2: Checkpoint & Status Flush                                     |
|                     +----------------------------------------------------+                        |
|                     | RuntimeCheckpointStore                             |                        |
|                     | (Offset + Fingerprint + StreamEpoch + CleanShutdown|                        |
|                     | RuntimeStatusStore (Heartbeat, PID, Lifecycle)     |                        |
|                     +----------------------------------------------------+                        |
+---------------------------------------------------------------------------------------------------+
```

## Decisions

### Decision 1: Foreground Orchestrator Process Model & Signal Handling
- **Approach**: The runtime executes as a single-threaded foreground process in the user's terminal (`companion runtime start`), blocking the calling shell until `Ctrl+C` (SIGINT/SIGTERM) is received.
  - A signal handler flags `self._shutdown_requested = True`.
  - The loop finishes the current batch's durable persistence, executes a bounded exit drain, durably persists `CharacterState` and journey history, flushes the final checkpoint offset, marks the checkpoint with `clean_shutdown = True` and `clean_shutdown_at = datetime.now(timezone.utc).isoformat()`, updates final lease metadata if needed, releases the lifetime OS writer lock (`runtime/writer_lease.lock`), and exits with code 0. If the process crashes at any point prior to this, the OS automatically releases the writer lock, `clean_shutdown` remains `False`, and the next startup enters crash recovery. The writer lock is never deleted or released before final durable state and checkpoint work is complete.
  - Synchronous 1.0s polling interval during active sessions, backing off to 2.0s during `IDLE` state.
- **Rationale**: Keeps execution completely transparent, easy to start, observe, and terminate without orphan background processes, Windows service registration, or IPC complexities.
- **Alternatives Considered**:
  - *Background daemon/service*: Rejected. Complex to inspect, risks orphaned zombie processes, and violates the zero-daemon CLI architectural invariant.
  - *Asyncio event loop*: Rejected. The workload is strictly sequential, local I/O-bound (polling a local file and process table), and already written with synchronous Pydantic and standard library APIs. Plain synchronous iteration with `time.sleep()` is simpler, fully deterministic, and easier to test.

### Decision 2: Stream Generation, Stable Source Identity, and Durable Idempotency
- **Approach**:
  - **The Truncation Identity Hazard**:
    The previous observation identity concept `file_id:start_byte_offset:end_byte_offset:event_type` is insufficient after in-place truncation. If `Client.txt` is truncated in-place (e.g., cleared by the game engine or user):
    - Normalized path remains identical.
    - Windows creation time (`st_ctime`) remains identical.
    - Prefix header hash remains identical once the engine writes the standard initialization header.
    - Byte offsets restart from zero (`0`).
    Without a stream generation marker, a brand-new post-truncation event at offset 100-200 would produce the exact same identity as an old event from before truncation, causing incorrect deduplication and history corruption.
  - **Durable Stream Epoch & Generation Model**:
    Introduce a persistent `stream_epoch: int = 1` stored in `RuntimeCheckpoint`.
    ```text
    source_stream_id = f"{file_fingerprint_id}:epoch_{stream_epoch}"
    observation_identity = f"{source_stream_id}:{start_offset}:{end_offset}:{event_type}"
    ```
    - Normal append: preserves existing `stream_epoch`.
    - Truncation detected (`size < checkpoint.last_offset`): increment `stream_epoch += 1`, reset read offset to 0, persist new epoch in checkpoint.
    - Replacement/rotation detected: new fingerprint and new `stream_epoch = 1` (or incremented epoch).
    - Even if byte offsets restart from 0, every event in the new generation carries `epoch_2`, guaranteeing unique observation identities that never collide with `epoch_1`.
  - **Durable Counted-Event Watermark (Replacing Bounded ID Window)**:
    Reconciling `CharacterState` must be provably idempotent for every event type across crash replays.
    - *Why the 100-Entry ID Window Was Defective and Removed*:
      The prior design stored the latest 100 death observation IDs in `death_count.evidence_refs`. This fails to guarantee replay idempotency: if a single batch (e.g. during rapid gameplay, lag spike, or backfill) contains > 100 death observations, all deaths are counted and canonical state is persisted. If a crash occurs before the runtime checkpoint is saved, the prior checkpoint replays the entire batch. The earliest death IDs have already fallen out of the 100-entry sliding window and are counted again, causing counter drift and double-counting.
    - *Durable Source Watermark Design*:
      Because `Client.txt` observations are processed strictly sequentially within a stable source stream (`source_stream_id`), state reconciliation tracks a durable per-counted-effect source watermark:
      ```text
      last_counted_death_stream_id: str
      last_counted_death_end_offset: int
      ```
      This watermark is stored within `state.death_count.evidence_refs` (e.g., `[f"watermark:{source_stream_id}:{end_offset}"]`) and persisted atomically as part of the same canonical `CharacterState` file save.
    - *Deterministic Watermark Rules*:
      1. **Same source stream (`event.source_stream_id == watermark_stream_id`)**:
         - If `event.end_offset <= watermark_end_offset`: The event was already counted. Treat as replay/no-op and return state unchanged.
         - If `event.end_offset > watermark_end_offset`: The event is new. Increment counter (`deaths + 1`), advance watermark to `event.end_offset`, and record update.
      2. **New stream epoch or replacement (`event.source_stream_id != watermark_stream_id`)**:
         - Establish a new counted-event watermark for that stream, increment counter (`deaths + 1`), and advance watermark to `event.end_offset`.
      3. **Atomicity**:
         - The counter value and its counted-event watermark MUST be persisted atomically as part of the same canonical `CharacterState` save. If a crash occurs after saving state but before saving checkpoint, replaying 1, 10, or 500 records results in all replayed events having `end_offset <= watermark_end_offset`, guaranteeing zero counter increase on replay.
  - **Inspection of Other CharacterState Effects**:
    - `level`: Monotonic comparison (`new_level > state.level.value`). Naturally idempotent.
    - `current_zone`, `current_act`, `equipped_weapon_set`, `session_active`: Value overwrites. Naturally idempotent.
    - `resistances`, `attributes`: Dictionary value replacements. Naturally idempotent.
    - `resources` (gold, gcp): Currently defaults; not parsed from `Client.txt`.
    - `death_count` is the sole non-idempotent additive counter derived from `Client.txt`; no other fields require watermark machinery.
  - **Deduplicated Journey History**:
    `JourneyHistoryLogger` verifies whether `entry_id` (derived from stable source identity `observation_identity`) already exists in recent history before appending. Replaying already-consumed records does NOT duplicate history lines.
  - **Strict Persistence Sequencing**:
    1. Read bounded log batch.
    2. Normalize observations with stable stream generation (`source_stream_id`).
    3. Reconcile character state idempotently in memory (with counted-event watermark checks).
    4. Append and deduplicate durable journey events to disk.
    5. Compute consolidated objective derivation and notification side effects.
    6. Persist `CharacterState` atomically via canonical public API `CharacterStateStore.save_character(state)`.
    7. Persist `RuntimeCheckpoint` (offset, file fingerprint, stream epoch, clean shutdown status) ONLY after durable state and history writes succeed.
  - **Crash Semantics**:
    If a crash occurs after step 6 but before step 7:
    The checkpoint on disk still holds the earlier byte offset and `clean_shutdown = False`. On restart, the runtime resumes from that offset. When replaying the batch, state reconciliation checks the durable watermark, recognizes the already-applied counted events, applies monotonic updates, and leaves character state perfectly consistent. Journey history deduplicates by entry ID. Step 7 then succeeds on the next flush, advancing the checkpoint.
- **Rationale**: Solves the truncation collision defect and guarantees non-idempotent counter replay safety regardless of batch size with zero external dependencies and zero schema bloat.
- **Alternatives Considered**:
  - *Magic fixed-size 100-entry ID window*: Rejected. Does not guarantee replay idempotency if batches exceed 100 events.
  - *Unbounded event-ID set in state*: Rejected. Causes unbounded memory and JSON storage growth over time.
  - *Full event-sourcing reconstruction from byte 0 on every startup*: Rejected. Excessively slow on large history logs and couples state availability to entire log file history.
  - *Arbitrary database engine*: Rejected. Unnecessary complexity for desktop companion.

### Decision 3: File Identity Fingerprinting & Decision Table
- **Approach**:
  The checkpoint file `runtime/session_checkpoint.json` stores a lightweight `FileFingerprint` alongside `stream_epoch` and read offset:
  - `path`: str (normalized path)
  - `created_at`: float (file birth/creation time via `st_ctime` on Windows)
  - `prefix_hash`: str (SHA-256 hash of the initial 512 bytes of `Client.txt`)
  - `stream_epoch`: int (durable generation counter, default: 1)
  - `last_offset`: int (last acknowledged byte offset)
  - `last_file_size`: int (last observed total file size)
  - `updated_at`: str (ISO 8601 timestamp)
  - `clean_shutdown`: bool (termination status)
  - `clean_shutdown_at`: str | null (timestamp of clean graceful exit)

#### File Identity Decision Table

| # | Condition | Classification | Action Taken | Stream Epoch | Read Offset Action |
|---|---|---|---|---|---|
| 1 | Same fingerprint (`prefix_hash` & `st_ctime` match) AND `current_size >= last_offset` | **Normal Append Growth** | Consume new bytes incrementally | Retain same `stream_epoch` | Continue reading from `last_offset` |
| 2 | Same fingerprint (`prefix_hash` & `st_ctime` match) AND `current_size < last_offset` | **In-place Log Truncation** | Log warning; create new stream generation | Increment `stream_epoch += 1` | Reset read offset to 0; stream from beginning |
| 3 | Different fingerprint at same path (`prefix_hash` differs OR `st_ctime` indicates new file) | **File Replacement / Rotation** | Log rotation event; re-anchor boundary | Allocate new `stream_epoch = 1` (or increment) | Re-anchor boundary safely according to mode (0 for backfill, EOF for live start) |
| 4 | File missing / inaccessible / temporarily locked by game | **File Temporarily Unavailable** | Log structured recoverable warning; enter degraded polling state | Retain checkpoint unchanged | Do NOT advance offset; retry on next poll tick |
| 5 | File reappears after being missing | **File Reappearance** | Read initial header and stat; compare against checkpoint fingerprint | If fingerprint matches: retain epoch. If differs: new epoch | If matches: resume from `last_offset`. If differs: treat as replacement (#3) |
| 6 | Ambiguous identity (header read fails, partial initial bytes, or inconsistent filesystem metadata) | **Ambiguous / Degraded Identity** | Conservative safety fallback; treat as new stream generation | Allocate new `stream_epoch += 1` | Do NOT blindly seek to old offset; re-anchor boundary safely |

- **Windows Behavior & Fallback**: On Windows NTFS/FAT filesystems, `os.stat().st_ino` (inode number) is 0 or unreliable across volume mounts and mapped drives. Therefore, the fingerprint primary key relies on `st_ctime` (creation timestamp) combined with the SHA-256 hash of the first 512 bytes. In Path of Exile 2, the first 512 bytes contain the static engine initialization header (`... [INFO Client ...]`) which never changes during append growth, but differs completely when the log file is recreated or replaced.
- Full multi-megabyte file hashing is strictly avoided on every poll tick. Prefix hashing occurs only once on file open / rotation check.
- **Rationale**: Prevents seek-to-garbage corruption and guarantees unambiguous observation identities even when files are truncated or replaced in-place.

### Decision 4: Checkpoint Termination Semantics: Dirty-on-Start vs Clean Restart
- **Approach**:
  A checkpoint records explicit lifecycle metadata to distinguish:
  - **UNCLEAN / CRASHED Runtime** (`clean_shutdown == False`, `run_id`, `clean_shutdown_at == None`):
    The previous companion process crashed, was terminated via SIGKILL, lost power, or experienced an unhandled exception before graceful shutdown.
  - **CLEAN Graceful Shutdown** (`clean_shutdown == True`, `run_id`, `clean_shutdown_at` recorded):
    The user stopped the companion intentionally via `Ctrl+C` (SIGINT/SIGTERM), triggering graceful termination.
  - **Dirty-on-Start Lifecycle Invariant**:
    Before the runtime processes ANY new log observation from `Client.txt`:
    1. Resolve startup boundary and recovery policy (Case A, B, or C).
    2. Take exclusive runtime writer lease ownership (`runtime/writer_lease.json`).
    3. Durably persist checkpoint metadata with:
       ```python
       clean_shutdown = False
       clean_shutdown_at = None
       run_id = uuid.uuid4().hex
       ```
    Only AFTER this durable write succeeds may the ingestion loop begin processing records.
    Therefore:
    previous clean checkpoint -> runtime starts -> immediately becomes durable UNCLEAN/RUNNING state -> process observations.
    If the process then crashes at any point during observation processing:
    `clean_shutdown` remains `False` on disk -> next startup cannot mistake it for a clean shutdown and executes crash-recovery semantics.
  - **Graceful Shutdown Ordering**:
    On receiving `SIGINT` (Ctrl+C) or `SIGTERM`:
    1. Bounded final log drain: Read trailing records from `Client.txt`.
    2. Durable state and history: Persist `CharacterState` via `store.save_character()` and append deduplicated journey logs.
    3. Durable current checkpoint offset: Persist current byte offset, stream epoch, and fingerprint.
    4. Only then mark clean shutdown: Update checkpoint with `clean_shutdown = True` and `clean_shutdown_at = datetime.now(timezone.utc).isoformat()`.
    5. Release runtime writer lease: Unlink `runtime/writer_lease.json`.
    If the final clean-marker write fails or crashes, the next startup conservatively treats the state as unclean crash recovery.
  - **Startup Boundary Behaviors**:
    1. **Case A: Unclean / Crash Restart (`clean_shutdown == False`)**:
       - If a valid compatible checkpoint exists (matching fingerprint and valid offset):
         - Resume directly from `last_offset`.
         - Execute at-least-once replay of uncheckpointed log lines.
         - Rely on idempotent state reconciliation (monotonic level, durable watermark on `death_count`, overwrite on zone) and journey history deduplication.
         - Log: `[CRASH RECOVERY] Unclean shutdown detected. Resuming from checkpoint offset {last_offset} with at-least-once replay.`
    2. **Case B: Clean Shutdown, Later Normal Start (`clean_shutdown == True`)**:
       - The companion was intentionally stopped. The player may have continued playing for hours or resumed days later.
       - Records written while the companion was stopped MUST NOT be silently replayed as live gameplay events.
       - If Path of Exile 2 is ALREADY RUNNING when the companion restarts:
         - Normal live mode seeks to current EOF of `Client.txt`.
         - The gap is explicitly skipped as unobserved backlog to prevent alert storms: `[STARTUP] PoE2 already running after clean shutdown. Seeking to current EOF ({current_eof}); {gap_bytes} bytes of offline backlog skipped to prevent alert storms.`
         - Pre-startup offline records do NOT generate present-tense live notifications.
         - If the user explicitly wants to process the offline backlog, they can run `companion runtime start --backfill`.
       - If Path of Exile 2 is NOT RUNNING when the companion restarts:
         - Runtime enters `IDLE` state.
         - Captures current EOF as idle baseline.
         - Consumes all records written after that baseline when the game launches (Case C).
    3. **Case C: Companion Starts Before Game (Idle Baseline)**:
       - Whether following clean shutdown or initial install, if the game process is not running, runtime enters `IDLE` state.
       - An idle baseline EOF offset and file fingerprint are established at current EOF.
       - When the game subsequently launches, all records written after that baseline are captured (ensuring launch-time zone transitions and level-ups are never skipped).
  - **Rationale**: Cleanly resolves the tension between crash recovery (which must replay to prevent data loss) and intentional restarts (which must not alert on ancient offline gameplay), with guaranteed crash detection via dirty-on-start sequencing.

### Decision 5: Historical Backfill to Live Boundary
- **Approach**:
  When invoked with `companion runtime start --backfill`:
  1. At startup, the runtime captures a deterministic boundary:
     `startup_backfill_end_offset = file_size(Client.txt)`
  2. **Phase 1: Historical Replay (Byte 0 -> `startup_backfill_end_offset`)**:
     - Tailer streams from byte 0 up to `startup_backfill_end_offset`.
     - Observations are reconciled into `CharacterState` and recorded to `JourneyHistory` using original log timestamps.
     - Live notifications are strictly **SUPPRESSED** (`suppress_notifications = True`). Sinks are not flooded with obsolete alerts from past sessions.
     - Console logs structured catch-up progress: `[BACKFILL] Catching up historical log (0 -> {startup_backfill_end_offset} bytes)...`
  3. **Phase 2: Live Transition Boundary**:
     - Once read offset reaches `startup_backfill_end_offset`:
       - The runtime logs: `[BACKFILL] Historical catch-up complete at offset {startup_backfill_end_offset}. Transitioning to LIVE mode.`
       - Runtime transitions to `LIVE` mode (`suppress_notifications = False`).
     - Any records appended AFTER `startup_backfill_end_offset`:
       - Processed with normal live gameplay notification semantics.
       - Emits safe-zone advisories, console alerts, and active session metrics.
- **Rationale**: Eliminates alert storms while providing a seamless, deterministic transition from historical catch-up to active session monitoring.

### Decision 6: Canonical Single-Writer Lease Ownership and State Persistence
- **Approach**:
  - **The Race and Lost-Update Hazards of Metadata Leases and Short File Locks**:
    1. *Short file locks around physical saves*: `CharacterStateStore.save_character()` employs `StateLock` around physical file serialization and `os.replace()`. However, a short file lock only around atomic file replacement is NOT sufficient to prevent lost updates if two independent processes execute `read state -> mutate in memory -> save state`. Process 2 can read state while Process 1 is mutating, and overwrite Process 1's saved state based on a stale read.
    2. *Metadata-only lease files*: A lease design relying solely on creating/reading `runtime/writer_lease.json` with owner PID and heartbeat does NOT prove atomic exclusive ownership. Two runtime processes can race: Process A sees no lease file, Process B sees no lease file, Process A writes its lease, Process B writes its lease, and both believe they own `CharacterState` mutation (check-then-create race).
  - **OS-Backed Lifetime Writer Lock Authority**:
    To guarantee atomic single-writer exclusivity without check-then-create races, the continuous runtime establishes exclusive writer ownership using an OS-backed file lock:
    - Path: `runtime/writer_lease.lock`
    - Implementation: Reuses the project's existing Windows `StateLock` mechanism (`companion.state.lock.StateLock` using Windows `msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)` on byte 0 of non-empty lock file).
    - Lifecycle: The OS lock is acquired exclusively at startup and HELD continuously for the entire lifetime of the foreground runtime process.
    - **The OS lock is the sole authority for writer ownership.**
  - **Separation of Ownership Authority vs Diagnostic Metadata**:
    - `runtime/writer_lease.lock`: The sole authority for writer ownership. Holding this OS lock proves exclusive mutation rights.
    - `runtime/writer_lease.json`: Metadata ONLY. Contains human-readable diagnostics and operational telemetry:
      ```python
      class WriterLease(BaseModel):
          owner_pid: int
          run_id: str
          acquired_at: str
          last_heartbeat: str
          character_id: str | None = None
      ```
    - The JSON metadata MUST NOT independently grant writer ownership. A process possessing or reading `writer_lease.json` does not own writer rights unless it holds `writer_lease.lock`.
  - **Atomic Acquisition and Concurrent-Start Behavior**:
    When two runtime processes race to start:
    1. Runtime A attempts to acquire `runtime/writer_lease.lock` via `StateLock.acquire()`.
    2. Runtime B attempts to acquire `runtime/writer_lease.lock` via `StateLock.acquire()`.
    3. The Windows kernel atomically grants the byte lock to exactly one process (e.g. Runtime A).
    4. Runtime B's lock acquisition fails immediately, raising `StateLockError`.
    5. Runtime B catches `StateLockError`, leaves disk state untouched, and immediately halts with error code `RUNTIME_WRITER_ACTIVE` (e.g. `Error: Continuous runtime writer lock is actively held. CharacterState mutation refused [RUNTIME_WRITER_ACTIVE].`).
    Zero check-then-create race can occur.
  - **Crash Recovery and PID-Reuse Robustness**:
    Do not rely on PID liveness alone as the authority for lease ownership; PID reuse occurs on Windows after a process crashes.
    - *Automatic OS Release*: When a continuous runtime process crashes, terminates via SIGKILL, or is killed in Task Manager, the Windows operating system automatically closes all open file descriptors and releases the byte lock on `runtime/writer_lease.lock` immediately.
    - *Safe Reacquisition*: A subsequent runtime process or mutator can acquire `runtime/writer_lease.lock` immediately even if stale `writer_lease.json` metadata on disk still contains an old, terminated, or reused PID.
    - *Post-Acquisition Diagnostic Handling*:
      1. Attempt and obtain `runtime/writer_lease.lock`. Only after the OS lock is successfully acquired:
      2. Inspect any stale metadata in `runtime/writer_lease.json` for diagnostics and audit logging (e.g., logging `[LEASE] Acquired writer lock; replacing previous stale lease metadata from PID {stale.owner_pid}, run_id {stale.run_id}.`).
      3. Overwrite `runtime/writer_lease.json` with the new owner's `run_id`, `owner_pid`, `acquired_at`, and `last_heartbeat`.
      4. Stale JSON metadata is never treated as active ownership.
    - *Protection Against Lock Theft*:
      If `runtime/writer_lease.lock` is actively held by an OS process, another process cannot acquire it. The lock SHALL NOT be stolen, preempted, or deleted merely because a heartbeat timestamp in `writer_lease.json` appears stale. Heartbeat timestamps and PIDs are for human observability; the OS lock is the immutable authority.
    - *StateLock Lifetime Safety*: `companion.state.lock.StateLock` holds a standard non-blocking Windows file lock (`LK_NBLCK`). Holding this descriptor open across the process lifetime is safe, resource-light (one file descriptor), requires zero background threads or polling, and introduces zero heavy dependencies (no server, socket, database, or distributed lock engine).
  - **Mutating CLI Commands Participation**:
    All `CharacterState`-mutating CLI paths in the codebase must participate in the exact same writer-ownership contract before executing read-modify-write:
    1. `companion runtime start`: Continuous foreground runtime loop (holds lifetime lock).
    2. `companion session tail` (`handle_session_tail`): Polling log tailer that mutates active `CharacterState`.
    3. `companion state init` (`handle_state_init`): Creates and initializes a character state file.
    - *Mutator Invariant*: Before performing `read state -> mutate in memory -> save state`, any mutating CLI command must attempt exclusive acquisition of the canonical writer lease lock (`runtime/writer_lease.lock`).
    - If the continuous runtime holds the lifetime lock, the mutating command's acquisition immediately fails (`StateLockError`), and the command refuses execution with `RUNTIME_WRITER_ACTIVE` without altering character state.
    - A mutator must NOT merely inspect `writer_lease.json` before mutating; the OS lock itself must be checked and acquired atomically.
    - Read-only commands (`companion state inspect`, `companion objectives list`, `companion objectives evaluate`, `companion session status`, `companion session recap`, `companion intelligence audit`, `companion gear status`, `companion runtime status`) do not mutate `CharacterState`, do not acquire `writer_lease.lock`, and remain fully permitted without contention or lock errors.
  - **Shutdown and Release Ordering**:
    Graceful runtime shutdown executes in strict deterministic sequence:
    1. Bounded final log drain: Read trailing records from `Client.txt`.
    2. Durable state and history: Persist `CharacterState` via `store.save_character()` and append deduplicated journey history.
    3. Durable checkpoint offset: Persist current byte offset, stream epoch, and fingerprint.
    4. Mark clean shutdown: Update checkpoint with `clean_shutdown = True` and `clean_shutdown_at = datetime.now(timezone.utc).isoformat()`.
    5. Update final lease metadata: Update or unlink `runtime/writer_lease.json`.
    6. Release lifetime OS writer lock: Release byte 0 lock and close descriptor on `runtime/writer_lease.lock`.
    7. Exit process with code 0.
    Under NO circumstances may the writer lock be deleted or released before final durable state, history, and checkpoint work are complete. If a crash occurs at any step, the OS automatically releases the lock, `clean_shutdown` remains `False`, and the next startup enters crash recovery.
  - **Status Semantics (Metadata Active vs Lock Owned)**:
    `companion runtime status` may read `runtime_status.json` and `writer_lease.json` for human-readable diagnostics (PID, heartbeat, session duration, character ID). However, it must explicitly probe `runtime/writer_lease.lock` (attempting a non-blocking test acquire or OS handle check) to distinguish:
    - *Metadata claims ACTIVE, and OS lock is owned*: Runtime is actively running.
    - *Metadata claims ACTIVE, but OS lock is NOT owned*: Previous runtime crashed or was terminated. Report status as `NOT RUNNING` or `STALE` with last recorded metadata details.
    Status metadata does NOT control mutation safety; mutation safety is strictly enforced by `runtime/writer_lease.lock`.
  - **Public Persistence API Invariant**:
    The continuous runtime interacts with state storage exclusively through the public `CharacterStateStore.save_character(state: CharacterState) -> Path` API, never calling private store internals (such as `_atomic_write`).
- **Rationale**: Provides provable single-writer exclusivity, eliminates check-then-create and read-modify-write races, ensures crash resilience without PID reuse hazards, and maintains zero external servers, sockets, databases, or distributed dependencies.

### Decision 7: Batch Coalescing and Bounded Exit Drain
- **Approach**:
  - **Batch Coalescing**: A single poll batch may ingest multiple log records (e.g., rapid zone transitions, multiple level-ups, or backlog consumption).
    - The pipeline ingests all lines in the batch, normalizes observations, and reconciles character state in memory.
    - `StateChangeTracker` aggregates all dirty triggers across the batch into a single consolidated delta set.
    - At most ONE objective derivation cycle is executed for the resulting state, and only the final actionable notification is emitted.
    - This eliminates notification storms during backlog catchup.
  - **Bounded Exit Drain**: When `ProcessMonitor` detects that the game process transitioned from `RUNNING` to `EXITED`:
    - The runtime does NOT immediately finalize the session.
    - It executes a bounded final read of `Client.txt` (a single poll pass with bounded line limit, e.g. 500 lines) to consume any final zone transitions or character exit logs flushed by the game right before closing.
    - It completes state reconciliation, flushes durable state and checkpoint, generates session recap metrics, and transitions to `GAME_EXITED`, then returns cleanly to `IDLE`.
    - It does not spin or block waiting for EOF.
- **Rationale**: Prevents losing the final zone transition or session duration boundary when the game process terminates, while preventing notification chatter during multi-record batches.

### Decision 8: Bounded and Deduplicated Safe-Zone Notification Queue
- **Approach**: Prevent unbounded in-memory accumulation in `NotificationManager` while characters spend extended periods in hostile combat zones:
  - **Semantic Deduplication**: Alerts in `_safe_zone_queue` are keyed by their semantic `dedupe_key` (derived from objective candidate ID or advice category, e.g., `passive:heavy_projectiles`).
  - **In-Place Replacement**: When a new advisory is dispatched with a `dedupe_key` that matches an already queued alert, the manager updates the existing pending alert in place (updating message/priority) rather than appending an identical duplicate.
  - **Hard Depth Limit**: The queue enforces a maximum capacity (default: 20 alerts). If the queue is full and a novel non-critical alert arrives, the oldest lowest-priority non-critical alert is dropped with a structured log warning.
- **Rationale**: Guarantees bounded memory consumption during marathon combat sessions without losing the most up-to-date guidance.

### Decision 9: Cross-Process Runtime Status via Local Atomic Heartbeat File
- **Approach**: `companion runtime status` operates strictly without network servers, background daemons, or socket IPC.
  - The running foreground orchestrator maintains an atomic status file: `runtime/runtime_status.json`.
  - On every poll tick, the orchestrator writes:
    - `runtime_pid`: int
    - `lifecycle_state`: str (`IDLE`, `GAME_RUNNING`, `SESSION_ACTIVE`, `GAME_EXITED`)
    - `session_id`: str | null
    - `game_process_running`: bool
    - `game_pid`: int | null
    - `last_heartbeat`: str (ISO 8601 timestamp)
    - `last_consumed_offset`: int
    - `active_character_id`: str | null (only if explicitly known)
    - `started_at`: str (ISO 8601 timestamp)
  - When `companion runtime status` is invoked from another terminal:
    - It reads `runtime/runtime_status.json` and `runtime/writer_lease.json`.
    - It probes `runtime/writer_lease.lock` (attempting a non-blocking test acquire or OS handle check) to verify if the OS writer lock is actually owned.
    - It verifies whether `runtime_pid` is actively running (using standard OS process existence check `os.kill(pid, 0)` on POSIX or `OpenProcess` / `psutil` on Windows).
    - It checks if `last_heartbeat` is fresh (within a 10.0-second staleness window).
    - If the PID is dead, the heartbeat is stale, or the OS lock is not owned despite active metadata, it reports status as `NOT RUNNING` or `STALE` with last recorded details.
    - If no status file exists, it reports `NOT RUNNING`.
- **Rationale**: Delivers instant, accurate cross-process status inspection with zero architectural overhead and zero risk of orphaned sockets or background daemon processes, distinguishing metadata claims from real OS lock ownership.

### Decision 10: Strictly Read-Only Game Log Access and Error Isolation
- **Approach**:
  - Game log access is strictly read-only binary (`mode="rb"`).
  - The runtime never opens `Client.txt` with write, append, or update flags (`"w"`, `"a"`, `"+"`, `"r+"`).
  - Error boundaries wrap all external boundaries:
    - Malformed log lines: Decoded with replacement, invalid lines skipped without raising exceptions.
    - Transient file locking: Windows file sharing conflicts caught and retried on the next poll cycle.
    - Faulty notification sinks: Exceptions in delivery sinks caught, logged as structured warnings, and isolated from the orchestrator loop.
- **Rationale**: Preserves 100% safety with respect to game files and ensures high availability during hours-long gaming sessions.

## Checkpoint, Fingerprint & Writer Lease Schema

```python
class FileFingerprint(BaseModel):
    """Lightweight file identity descriptor for Client.txt."""
    model_config = ConfigDict(frozen=True)

    path: str
    created_at: float
    prefix_hash: str  # SHA-256 of first 512 bytes
    file_size_at_fingerprint: int


class RuntimeCheckpoint(BaseModel):
    """Crash-consistent durable runtime checkpoint."""
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    file_fingerprint: FileFingerprint
    stream_epoch: int = 1
    last_offset: int
    last_file_size: int
    updated_at: str
    clean_shutdown: bool = False
    clean_shutdown_at: str | None = None
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


class WriterLease(BaseModel):
    """Diagnostic metadata descriptor for runtime/writer_lease.json.

    Authority for writer ownership is held strictly by the OS file lock
    on runtime/writer_lease.lock (StateLock). This JSON model contains
    diagnostic telemetry only and does not grant ownership independently.
    """
    model_config = ConfigDict(frozen=True)

    owner_pid: int
    run_id: str
    acquired_at: str
    last_heartbeat: str
    character_id: str | None = None
```

## Observability & CLI Design

### CLI Commands
```bash
# Start foreground continuous runtime
companion runtime start [--runtime runtime] [--log path/to/Client.txt] [--char character_id] [--poll-interval 1.0] [--backfill] [--verbose]

# Inspect current runtime status across files
companion runtime status [--runtime runtime] [--json]
```

### Console Event Formatting
Normal execution uses clear, structured prefix tags:
```text
[2026-09-23 18:30:00] [RUNTIME] Starting PoE2 Companion continuous loop (PID: 14200)
[2026-09-23 18:30:00] [RUNTIME] Idle. Waiting for PoE2 process... (baseline log offset: 1048576, epoch: 1)
[2026-09-23 18:30:05] [SESSION] PoE2 process detected: PathOfExileSteam.exe (PID: 28412)
[2026-09-23 18:30:06] [ZONE] Entered area "The Riverbank" (Area Level 11) [COMBAT]
[2026-09-23 18:32:10] [LEVEL] Character 'BOMSHAK' reached Level 12!
[2026-09-23 18:32:10] [OBJECTIVE] [CURRENT_PROGRESSION] Allocate passive node 'Heavy Projectiles'
[2026-09-23 18:32:10] [NOTIFY] Queued advisory in combat zone: Allocate passive node 'Heavy Projectiles'
[2026-09-23 18:35:40] [ZONE] Entered area "Clearfell Encampment" [SAFE ZONE]
[2026-09-23 18:35:40] [NOTIFY] Delivered 1 buffered advisory: Allocate passive node 'Heavy Projectiles'
[2026-09-23 18:45:00] [SESSION] PoE2 process exited. Performing final log drain...
[2026-09-23 18:45:01] [SESSION] Session finalized. Duration: 15m 0s.
[2026-09-23 18:45:01] [RUNTIME] Idle. Waiting for PoE2 process...
^C
[2026-09-23 18:50:00] [RUNTIME] Shutting down gracefully... Checkpoint saved at byte 1052300 (epoch: 1, clean_shutdown: true).
```

## Risks / Trade-offs

- **[Risk]** In-place file truncation resets byte offsets to 0, colliding with old observation IDs.
  -> **Mitigation**: Durable `stream_epoch` increments on truncation, guaranteeing all new events carry a new generation identity (`epoch_2`) that never collides with pre-truncation events.
- **[Risk]** Crash occurs after state update but before checkpoint persistence, replaying counted events.
  -> **Mitigation**: Canonical `CharacterState` records observation IDs in `death_count.evidence_refs`; replayed death observations are recognized and leave death count unchanged.
- **[Risk]** Log file rotated or replaced at same path with size larger than previous offset.
  -> **Mitigation**: Lightweight `FileFingerprint` (creation time + prefix hash) detects file replacement and resets starting boundary safely rather than seeking blindly.
- **[Risk]** Offline gap between clean shutdown and restart treated as live gameplay.
  -> **Mitigation**: `clean_shutdown` flag distinguishes clean shutdown from crash recovery; clean restart with game running seeks to current EOF and logs backlog as unobserved.
- **[Risk]** Backfill floods user with obsolete alerts.
  -> **Mitigation**: Deterministic `startup_backfill_end_offset` boundary suppresses notifications during catch-up and transitions to live alerting only for records appended afterward.
- **[Risk]** Safe-zone notification queue grows without bound during long combat zones.
  -> **Mitigation**: Bounded queue with semantic deduplication by `dedupe_key` and hard capacity cap (max 20 alerts) with oldest non-critical eviction.
- **[Risk]** Game exit occurs while trailing log lines are incomplete or delayed.
  -> **Mitigation**: Bounded exit drain executes a single pass bounded poll; does not block or spin indefinitely.

## Test Plan

The implementation will be verified via automated unit and integration tests using deterministic test harnesses, preserving the existing 464-test baseline and introducing deterministic coverage for all crash, replay, and file identity scenarios:

1. **Stream Generation, File Identity & Decision Table Tests**:
   - `test_runtime_checkpoint_file_identity_normal_growth`: Matching fingerprint and grown file size preserves `stream_epoch` and resumes from saved offset.
   - `test_runtime_truncation_reuses_byte_offsets_with_new_event_identities`: Checkpoint at byte 5000, file truncated in-place to 500 bytes; verify `stream_epoch` increments to 2, read offset resets to 0, and new observations at byte 100 carry `epoch_2` distinct from pre-truncation `epoch_1` observations.
   - `test_runtime_replacement_with_identical_prefix_cannot_reuse_old_stream_epoch`: Create rotated `Client.txt` with identical prefix bytes but distinct creation timestamp; verify tailer detects replacement and allocates a new stream epoch rather than reusing the old epoch.
   - `test_runtime_missing_log_file_enters_recoverable_state`: Simulate missing log file during poll cycle; verify loop logs warning, retains checkpoint unchanged, and recovers when file reappears.
   - `test_runtime_reappearing_file_refingerprints_before_resume`: File reappears after being missing; verify tailer computes fresh fingerprint and matches checkpoint before resuming.
   - `test_runtime_ambiguous_identity_conservatively_starts_new_generation`: Provide ambiguous/unreadable file header; verify runtime conservatively creates new stream epoch and re-anchors boundary safely.

2. **Crash Consistency, Durable Counted-Event Watermark & Persistence Sequencing Tests**:
   - `test_runtime_greater_than_100_death_events_replayed_counted_once`: Ingest a batch containing >100 death observations, persist state with durable watermark, simulate crash before checkpoint save; restart runtime, replay entire batch from prior checkpoint, and verify character `death_count` matches exact single count and does not increment again.
   - `test_runtime_multiple_distinct_death_events_increment_correctly`: Process multiple distinct death records with strictly increasing byte offsets; verify character `death_count` increments correctly for each distinct event (e.g. 0 -> 1 -> 2 -> 3) and advances durable watermark.
   - `test_runtime_counted_event_watermark_updates_on_stream_epoch_change`: Checkpoint and character state have watermark for `epoch_1`; truncation triggers `epoch_2`; death events in `epoch_2` establish new watermark for `epoch_2` and increment counter correctly.
   - `test_runtime_counter_and_watermark_survive_restart_together`: Save `CharacterState` with incremented counter and updated watermark; reload state and verify both counter value and source watermark are preserved atomically together.
   - `test_runtime_checkpoint_never_advances_on_persistence_failure`: Inject persistence failure in `CharacterStateStore.save_character()`; verify runtime aborts batch before saving checkpoint, ensuring checkpoint offset does not advance past unpersisted state changes.
   - `test_runtime_checkpoint_state_persisted_but_checkpoint_offset_missing_replayed`: Simulate state write success followed by checkpoint write crash; verify replay succeeds without state divergence or duplicate journey history entries.
   - `test_runtime_uses_canonical_public_state_writer_api`: Verify orchestrator invokes `CharacterStateStore.save_character()` and does not call private methods (such as `_atomic_write`).

3. **Checkpoint Dirty-on-Start, Termination & Startup Tail Baseline Tests**:
   - `test_runtime_startup_marks_clean_shutdown_false_before_ingestion`: Start runtime with prior clean checkpoint; verify checkpoint on disk immediately records `clean_shutdown = False` before first log observation is ingested or processed from `Client.txt`.
   - `test_runtime_crash_after_ingestion_cannot_be_mistaken_for_clean`: Simulate ingestion of records followed by process crash without graceful shutdown; verify subsequent startup detects `clean_shutdown = False` and enforces crash recovery.
   - `test_runtime_clean_shutdown_marker_written_only_after_final_state_and_checkpoint`: Trigger graceful shutdown; verify sequencing: drain -> state/history save -> checkpoint offset save -> `clean_shutdown = True` marker.
   - `test_runtime_clean_shutdown_followed_by_restart_skips_gap_as_unobserved`: Stop runtime cleanly (`clean_shutdown = True`), append 10 lines while companion is stopped, restart runtime with game running; verify runtime seeks to current EOF, skips gap, logs unobserved backlog, and emits zero live notifications for the gap.
   - `test_runtime_crash_restart_resumes_checkpoint`: Stop runtime uncleanly (`clean_shutdown = False`), restart runtime; verify runtime resumes from checkpoint offset with at-least-once replay.
   - `test_runtime_startup_before_game_captures_launch_records`: Start runtime in IDLE before game launch; append lines during simulated game launch; verify records written after idle baseline are captured.

4. **Canonical Single-Writer Lease Ownership & Concurrency Tests**:
   - `test_runtime_concurrent_start_atomic_ownership_one_winner`: Two continuous runtimes attempt start concurrently; exactly one process acquires `runtime/writer_lease.lock`.
   - `test_runtime_concurrent_start_second_returns_runtime_writer_active`: The competing second runtime process fails OS lock acquisition and immediately returns `RUNTIME_WRITER_ACTIVE` without mutating state.
   - `test_runtime_mutating_cli_cannot_race_runtime_writer`: While continuous runtime holds the writer lock, mutating CLI commands (`companion session tail`, `companion state init`) attempt acquisition of `runtime/writer_lease.lock`, fail immediately, and refuse execution with `RUNTIME_WRITER_ACTIVE`.
   - `test_runtime_read_only_cli_works_while_writer_lock_held`: Read-only CLI commands (`companion state inspect`, `companion objectives list`, `companion runtime status`) execute without lock contention or mutator refusal while runtime owns writer lock.
   - `test_runtime_crash_releases_os_writer_lock`: Runtime process crashes or terminates unexpectedly; verify OS releases byte lock on `runtime/writer_lease.lock` immediately, allowing subsequent process to acquire writer ownership.
   - `test_runtime_stale_metadata_with_dead_or_reused_pid_cannot_block_new_owner`: Stale `runtime/writer_lease.json` containing dead or OS-reused PID cannot permanently block new owner once OS lock is acquired.
   - `test_runtime_stale_metadata_cannot_grant_ownership_without_os_lock`: Metadata alone without holding `runtime/writer_lease.lock` cannot grant writer ownership.
   - `test_runtime_live_os_lock_cannot_be_stolen_even_with_stale_heartbeat`: An actively held OS lock cannot be stolen, preempted, or deleted even if heartbeat timestamp in `writer_lease.json` appears stale.
   - `test_runtime_graceful_shutdown_releases_writer_lock_only_after_final_checkpoint`: Verify graceful shutdown releases `runtime/writer_lease.lock` strictly after final durable checkpoint and state persistence succeed.
   - `test_runtime_no_lost_update_from_concurrent_mutators`: Two concurrent mutator processes executing read-modify-write on `CharacterState` are serialized by `runtime/writer_lease.lock`, guaranteeing zero lost updates.

5. **Historical Backfill to Live Boundary Tests**:
   - `test_runtime_backfill_historical_section_suppresses_notifications`: Run with `--backfill`; verify records between byte 0 and `startup_backfill_end_offset` update state and history with original timestamps while zero notifications are delivered to sinks.
   - `test_runtime_backfill_transition_to_live_restores_live_semantics`: Verify that once read offset reaches `startup_backfill_end_offset`, newly appended records transition to LIVE mode and trigger standard safe-zone notification delivery.

6. **Batch Coalescing & Exit Drain Tests**:
   - `test_runtime_multi_event_batch_coalesces_objectives`: Ingest batch containing 5 rapid zone and level events; verify state reconciles all 5 events but objective runner is invoked at most once for the batch.
   - `test_runtime_game_exit_performs_bounded_drain`: Simulate game process termination; verify runtime performs final log read, consumes trailing records, persists final state/checkpoint, and transitions to IDLE.

7. **Notification Queue Boundedness Tests**:
   - `test_runtime_notification_queue_semantic_deduplication`: Dispatch repeated identical advisories in combat zone; verify safe-zone queue length remains 1 (replaces pending entry).
   - `test_runtime_notification_queue_max_capacity_bounded`: Dispatch 25 distinct advisories in combat zone; verify queue is capped at max depth (20) without unbounded memory growth.

8. **Cross-Process Runtime Status Tests**:
   - `test_runtime_status_active_heartbeat`: Start runtime loop; verify `runtime/runtime_status.json` written with live PID, heartbeat, and offset; verify `runtime status` reports active.
   - `test_runtime_status_stale_heartbeat_or_dead_pid`: Mock status file with terminated PID or heartbeat older than 10s; verify `runtime status` reports NOT RUNNING / STALE.

9. **Read-Only Invariant & Fault Isolation Tests**:
   - `test_runtime_client_log_never_opened_in_write_mode`: Verify code inspection and runtime probes confirm file is opened strictly in `"rb"` mode.
   - `test_runtime_malformed_log_resilience`: Insert null bytes and corrupt UTF-8 sequences; verify runtime survives and parses subsequent valid lines.
   - `test_runtime_sink_exception_resilience`: Install faulty notification sink that raises `RuntimeError`; verify runtime logs warning and completes tick.
   - `test_runtime_graceful_shutdown_signal`: Trigger SIGINT via flag; verify loop exits cleanly with status 0, `clean_shutdown = True`, and persisted checkpoint.

10. **Baseline & Static Compliance**:
   - Full test suite passes: `uv run pytest -W error`.
   - Static AST check passes: `uv run pytest tests/compliance/test_no_input_guard.py`.

## Live Acceptance Plan

Following implementation, live acceptance will be performed against an active Path of Exile 2 gaming session:
1. Launch companion runtime in terminal (`python -m companion runtime start`). Verify `[RUNTIME] Idle. Waiting for PoE2 process...` with recorded baseline log offset and stream epoch.
2. Launch Path of Exile 2. Verify runtime detects process within 2 seconds: `[SESSION] PoE2 process detected`.
3. Enter character select and enter zone (e.g. "The Riverbank"). Verify zone change detected and classified.
4. Level-up verification:
   - If a character level-up occurs during the live session: verify level-up is parsed with class token, state updated, and `CURRENT_OBJECTIVE.json` updated with verified live provenance. Mark live level-up subcheck `LIVE VERIFIED`.
   - If no character level-up occurs during the session: mark the live level-up subcheck as `NOT OBSERVED IN THIS SESSION` without fabricating a pass, while deterministic real-log-shaped parser tests remain separately `PASS`.
5. Verify notification queued while in combat zone without duplicate queue growth.
6. Portal to town/encampment. Verify buffered notification delivered.
7. Exit Path of Exile 2. Verify bounded log drain occurs, session duration is recorded, and runtime returns to `IDLE`.
8. Relaunch Path of Exile 2. Verify clean session resumption from checkpoint without replaying historical events.
9. Press `Ctrl+C` in companion terminal. Verify clean exit, checkpoint saved with `clean_shutdown: true`, and no hanging processes.
10. `Client.txt` integrity verification:
    - Companion read-only invariant: Verify code access mode is strictly `"rb"` and confirm in controlled offline test that `Client.txt` hash remains identical when external writer is idle.
    - Live session: Permit legitimate file growth caused by Path of Exile 2 appending lines. Prove companion process holds only read-only file handles and never opens `Client.txt` in write/append/update mode (`"w"`, `"a"`, `"+"`, `"r+"`). Record pre/post file sizes to confirm expected game append growth.

## Open Questions

- *None* (all core requirements, stream generations, crash recovery semantics, file identity decision table, backfill boundaries, and single-writer contracts are established and grounded in existing verified project modules).
