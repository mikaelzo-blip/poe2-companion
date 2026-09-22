# PoE2 Companion Continuous Runtime — Live UAT Execution Report

**Execution Date:** 2026-09-23  
**Status:** PASS (All Phases Verified)  
**Test Suite Reference:** `tests/test_runtime_simulated_session.py`

---

## 1. Executive Summary

A multi-phase end-to-end simulated game session was executed against a live test directory validating all operational guarantees of the continuous runtime:
- Process lifecycle tracking (`IDLE` -> `GAME_RUNNING` -> `SESSION_ACTIVE` -> `GAME_EXITED` -> `IDLE`).
- Deterministic log ingestion with binary read-only access (`"rb"`).
- State reconciliation and dirty trigger tracking.
- Batch coalescing of objective reevaluations.
- Safe-zone notification buffering and auto-flushing.
- Single-writer lease locking (`runtime/writer_lease.lock`) and CLI contention rejection (`RUNTIME_WRITER_ACTIVE` exit code 1 / 75).
- Ungraceful termination (crash) simulation with dirty-on-start detection (`clean_shutdown = False`).
- Crash recovery resuming from exact checkpoint offset without duplicate event counting.
- Clean shutdown writing final state and releasing OS writer lock.

---

## 2. Phase-by-Phase Execution Results

| Phase | Description | Observed Result | Verdict |
|-------|-------------|-----------------|---------|
| **Phase 1: Startup & Baseline** | Orchestrator boots without game process. Checkpoint initialized with `clean_shutdown = False`. | State: `IDLE`, clean_shutdown: `False`, writer lease acquired. | **PASS** |
| **Phase 2: Game Launch** | `PathOfExileSteam.exe` detected running via process presence polling. | State transitioned to `GAME_RUNNING`. | **PASS** |
| **Phase 3: In-Combat Ingestion** | Ingested zone transition into `The Twilight Strand`, level up to 2, and death event while in combat. | Level: `2`, Death Count: `1`, Stream watermark recorded. Non-critical notifications buffered. | **PASS** |
| **Phase 4: Safe Zone Flush** | Ingested zone transition into `Lioneye's Watch` (safe zone). | Buffer drained and delivered to console sink. Buffer count dropped to `0`. | **PASS** |
| **Phase 5: Single-Writer Lease Protection** | Concurrent CLI mutation attempted (`companion state init`) while runtime active. | Immediately blocked and aborted with exit code `1` (`RUNTIME_WRITER_ACTIVE`). State store untouched. | **PASS** |
| **Phase 6: Process Termination & Final Drain** | `PathOfExileSteam.exe` terminated. | Bounded final exit drain completed. State transitioned to `IDLE`. | **PASS** |
| **Phase 7: Crash Simulation & Recovery** | Process killed without clean shutdown. Probed status; restarted runtime. | Status reported `NOT RUNNING`/`STALE`. Resumed from exact checkpoint offset; flagged `is_crash_recovery = True`. | **PASS** |
| **Phase 8: Clean Shutdown** | Graceful shutdown executed via `shutdown()`. | Flushed state and checkpoint; `clean_shutdown = True`; OS writer lock released. | **PASS** |

---

## 3. Compliance and Verification Metrics

- Total Pytest Suite: **544 tests passed, 0 warnings, 0 regressions** (`uv run pytest -W error`).
- No-Input Guard: **PASS** (`uv run pytest tests/compliance/test_no_input_guard.py`).
- Deterministic Stream and Event Identifiers: Confirmed across epochs.
- Watermark Idempotency: Verified across simulated crash restarts.
