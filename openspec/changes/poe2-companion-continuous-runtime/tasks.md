# Tasks

## 1. Runtime Foundation, File Fingerprinting, and Checkpoint Models

- [ ] 1.1 Create `companion/runtime/models.py` defining `SessionLifecycleState` (`IDLE`, `GAME_RUNNING`, `SESSION_ACTIVE`, `GAME_EXITED`), `RuntimeConfig`, `FileFingerprint` (normalized path, created_at, prefix_hash, file_size_at_fingerprint), `RuntimeCheckpoint` (file_fingerprint, stream_epoch, last_offset, last_file_size, updated_at, clean_shutdown, clean_shutdown_at, run_id), `WriterLease` (owner_pid, run_id, acquired_at, last_heartbeat, character_id), `RuntimeStatus`, and `RuntimeEvent` schemas with strict validation; verify unit tests pass with `uv run pytest tests/test_runtime_models.py`.
- [ ] 1.2 Implement `companion/runtime/checkpoint.py` with `FileFingerprint` generator (first 512-byte SHA-256 + normalized path + creation timestamp), 6-case file identity decision engine (normal append preserving epoch, in-place truncation incrementing stream epoch, replacement allocating new epoch, missing file handling, reappearance verification, and ambiguous identity fallback), dirty-on-start checkpoint initialization, and atomic checkpoint save/load; verify unit tests pass with `uv run pytest tests/test_runtime_checkpoint.py`.

## 2. Session Lifecycle, Exit Drain, and Change Detection

- [ ] 2.1 Implement `companion/runtime/lifecycle.py` managing state transitions (`IDLE` -> `GAME_RUNNING` -> `SESSION_ACTIVE` -> `GAME_EXITED`) driven by `ProcessMonitor` and observation events, including a bounded final `Client.txt` log drain upon game process exit before session finalization; verify unit tests pass with `uv run pytest tests/test_runtime_lifecycle.py`.
- [ ] 2.2 Implement `companion/runtime/change_tracker.py` tracking dirty triggers (level, zone, session state, character identity, gear audit) and batch coalescing to consolidate multiple events in a poll batch into at most one objective derivation; verify unit tests pass with `uv run pytest tests/test_runtime_change_tracker.py`.

## 3. Crash Consistency, Stream Generation, and Durable Watermark Idempotency

- [ ] 3.1 Implement stable source stream identity generation (`source_stream_id = file_fingerprint:epoch_N`, `observation_id = source_stream_id:start:end:type`) in observation normalization and update `JourneyHistoryLogger` to deduplicate entries by stable source identity; verify deterministic identity and deduplication with `uv run pytest tests/test_runtime_crash_consistency.py`.
- [ ] 3.2 Update `companion/state/reconciliation.py` to make counted event reconciliation (`death_count`) durable and replay-idempotent across process crashes by maintaining a durable per-counted-effect source watermark (`last_counted_death_stream_id`, `last_counted_death_end_offset` in `death_count.evidence_refs`), replacing magic 100-entry ID windows so batches of >100 death events replayed after a crash are counted exactly once, distinct events advance the watermark and counter, and new stream epochs establish a new watermark; verify with `uv run pytest tests/test_runtime_counted_idempotency.py`.
- [ ] 3.3 Implement bounded safe-zone notification buffering in `companion/runtime/notifications.py` enforcing semantic deduplication by `dedupe_key` (in-place replacement for repeated objectives), maximum queue depth (capping at 20 alerts), and historical notification suppression under `--backfill`; verify unit tests pass with `uv run pytest tests/test_runtime_notification_queue.py`.

## 4. Continuous Runtime Orchestrator Loop, Dirty-on-Start, and Tail Policies

- [ ] 4.1 Implement `companion/runtime/orchestrator.py` executing the deterministic pipeline: dirty-on-start checkpoint persistence (`clean_shutdown = False`, `run_id`) BEFORE any log observation is processed, startup boundary resolution (`clean_shutdown` crash recovery vs clean restart seeking to EOF with unobserved backlog disclosure), startup idle baseline capture, strictly read-only binary log access (`mode="rb"`), canonical public `CharacterStateStore.save_character(state)` invocation, consolidated batch objective derivation, safe-zone notification delivery, deterministic backfill-to-live transition at `startup_backfill_end_offset`, and crash-consistent persistence sequencing (state & history before checkpoint offset); verify unit tests pass with `uv run pytest tests/test_runtime_orchestrator.py`.
- [ ] 4.2 Add signal handling (`SIGINT`/Ctrl+C, `SIGTERM`) in `companion/runtime/orchestrator.py` for graceful shutdown, executing bounded final drain, flushing durable state and history, persisting current checkpoint offset, and only then writing `clean_shutdown = True` and `clean_shutdown_at` before updating lease metadata, releasing the lifetime OS writer lock (`runtime/writer_lease.lock`), and exiting; verify with `uv run pytest tests/test_runtime_shutdown.py`.
- [ ] 4.3 Add structured low-noise console observability (`[SESSION]`, `[ZONE]`, `[LEVEL]`, `[OBJECTIVE]`, `[NOTIFY]`, `[BACKFILL]`, `[CRASH RECOVERY]`), honest startup backlog disclosure, and optional `--verbose` diagnostics; verify console output formatting with `uv run pytest tests/test_runtime_observability.py`.

## 5. Canonical Writer Ownership, Cross-Process Status, and CLI Integration

- [ ] 5.1 Implement `companion/runtime/lease.py` managing OS-backed lifetime single-writer locking on `runtime/writer_lease.lock` using the project's existing Windows `StateLock` mechanism (`msvcrt.locking`) as the sole authority for writer ownership, maintaining diagnostic-only metadata in `runtime/writer_lease.json` (owner_pid, run_id, acquired_at, last_heartbeat, character_id) that cannot independently grant ownership, ensuring atomic lock acquisition eliminates check-then-create races, automatic OS lock release on crash enables immediate recovery without being blocked by dead or reused PIDs, held OS locks cannot be stolen even with stale heartbeats, and wiring atomic writer lock acquisition into all CharacterState-mutating CLI paths (`companion runtime start`, `companion session tail`, `companion state init`) to immediately refuse with `RUNTIME_WRITER_ACTIVE` upon contention while permitting read-only commands without locking; verify with `uv run pytest tests/test_runtime_writer_lease.py`.
- [ ] 5.2 Implement `companion/runtime/status.py` publishing atomic heartbeat file `runtime/runtime_status.json` on each poll tick, probing `runtime/writer_lease.lock` ownership to distinguish metadata claiming ACTIVE vs actual OS writer lock ownership, and reporting STALE / NOT RUNNING when the process is dead, the lock is not held, or heartbeat is older than 10s without sockets or network services; verify status inspection with `uv run pytest tests/test_runtime_status.py`.
- [ ] 5.3 Wire `runtime start` and `runtime status` subcommands into `companion/cli.py` and `companion/__main__.py` with `--runtime`, `--log`, `--char`, `--poll-interval`, `--backfill`, `--verbose`, and `--json` arguments; verify CLI parsing with `uv run pytest tests/test_cli_runtime.py`.

## 6. Deterministic Test Suite and Baseline Compliance

- [ ] 6.1 Implement end-to-end integration and crash-consistency tests in `tests/test_runtime_integration.py` covering:
  - truncation reuses byte offsets but produces NEW event identities carrying incremented `stream_epoch`;
  - replacement with identical-looking prefix cannot reuse old stream epoch;
  - normal append preserves stream epoch;
  - >100 counted death events persisted before checkpoint, replayed, still counted exactly once;
  - multiple distinct death events increment correctly and advance watermark;
  - counted-event watermark changes when stream epoch changes;
  - counter value and event watermark survive restart together;
  - checkpoint and state persisted but checkpoint offset missing/replayed;
  - previous clean checkpoint becomes clean_shutdown=False before first ingestion;
  - crash after ingestion cannot be mistaken for clean shutdown;
  - clean shutdown marker is written only after final durable state/checkpoint;
  - clean shutdown followed by later restart does not replay gap as live notifications;
  - crash restart DOES resume checkpoint offset with at-least-once replay;
  - two runtimes start concurrently: exactly one obtains writer ownership via OS lock;
  - second runtime receives RUNTIME_WRITER_ACTIVE;
  - mutating CLI cannot race runtime writer and is refused with RUNTIME_WRITER_ACTIVE;
  - read-only CLI works while runtime owns writer lock;
  - runtime crash releases OS writer lock automatically;
  - stale metadata with dead/reused PID cannot permanently block new owner;
  - stale metadata cannot grant ownership without OS lock;
  - live OS lock cannot be stolen even with stale heartbeat;
  - graceful shutdown releases writer lock only after final durable checkpoint;
  - no lost update from two concurrent mutators;
  - backfill historical section suppresses notifications;
  - transition from backfill boundary (`startup_backfill_end_offset`) to newly appended live records restores live semantics;
  - runtime uses canonical public CharacterState writer API (`CharacterStateStore.save_character`);
  - multi-event batch coalesces objective reevaluation to at most one run;
  - game exit performs bounded final log drain before finalizing session;
  - repeated queued objective replaces pending entry without growing queue indefinitely;
  - stale runtime status heartbeat (>10s) or dead PID detected as STALE / NOT RUNNING;
  - runtime status reports ACTIVE when foreground process is running and holds lock;
  - live-source file is never opened in write mode (`"rb"` only);
  verify with `uv run pytest tests/test_runtime_integration.py`.
- [ ] 6.2 Implement fault isolation tests in `tests/test_runtime_fault_isolation.py` proving malformed log bytes, temporary file locking, and notification sink exceptions do not crash the runtime loop or corrupt character state; verify with `uv run pytest tests/test_runtime_fault_isolation.py`.
- [ ] 6.3 Run the full test suite with zero warnings and static no-input compliance check, ensuring the existing 464-test baseline is not weakened: verify with `uv run pytest -W error` and `uv run pytest tests/compliance/test_no_input_guard.py`.

## 7. Live UAT Execution (Game Session Verification)

- [ ] 7.1 Execute live session acceptance test with Path of Exile 2: verify companion starts idle and establishes baseline EOF offset; verify game launch is detected within 2 seconds; verify zone change detected and classified; verify level-up handling (if real level-up occurs, confirm verified live provenance and mark LIVE VERIFIED; if no real level-up occurs during session, mark subcheck NOT OBSERVED IN THIS SESSION while deterministic parser tests remain separately PASS); verify combat-zone advisory buffering and town safe-zone flushing without queue growth; verify game exit triggers bounded log drain, session recap, and return to idle; verify clean Ctrl+C shutdown with `clean_shutdown: true` in checkpoint; verify Client.txt integrity (verify read-only binary mode in companion code and controlled offline hash invariance; in live session, permit game append growth, verify companion never opens log in write mode, and record pre/post sizes).
