# Milestone 5 Acceptance Report: Process/Session + Client.txt + Reconciler/History

## Executive Summary
Milestone 5 adds safe, live game session context to the PoE2 Hermes Companion. It introduces process presence detection (`ProcessMonitor`), a stream-safe read-only `Client.txt` log tailer (`ClientLogTailer`) with rotation handling and strict chat discarding, a decoupled in-memory observation bus (`ObservationBus`), a state reconciler (`reconcile_observation`) updating `CharacterState` facts with per-field provenance metadata, and an append-only, privacy-sanitized `journey_history.jsonl` logger.

## Deliverables & Architecture
- **Process Presence**: `companion/sensing/process_presence.py` monitors game executables (`PathOfExileSteam.exe`, `PathOfExile.exe`) across `IDLE`, `RUNNING`, and `TERMINATED` states using standard library tools without elevated permissions or hooking.
- **Client.txt Tailer**: `companion/sensing/client_log.py` reads appended bytes, handles chunking and incomplete trailing lines, detects file shrinkage/rotation, and extracts zone entries, level-up milestones, and death events.
- **Privacy Invariant**: All chat lines (`@From`, `@To`, `$`, `#`, `%`) are filtered and discarded before disk emission or history logging.
- **Observation Event Bus**: `companion/observations/schema.py` & `companion/observations/bus.py` provide typed pub/sub event distribution.
- **State Reconciliation & Staleness**: `companion/state/reconciliation.py` & `companion/state/staleness.py` map game observations to verified `CharacterState` facts and check age staleness.
- **Journey History**: `companion/state/history.py` appends clean structured records to `runtime/journey_history.jsonl`.
- **CLI Commands**:
  - `companion session status`: Reports active process state and character session context.
  - `companion session tail`: Tails game logs and reconciles state.
  - `companion journey list`: Lists historical milestone journey entries.

## Verification & Metrics
- Unit & Integration Test Suite: 345 passing tests (0 failures, 100% pass rate).
- No-Input Static Guard: 9 passing compliance tests, 0 input automation violations.
- Canonical Specifications: 12 passing specs validated under `openspec validate --specs`.
- Archival: OpenSpec change `poe2-companion-m5-session-log-reconciler` archived to `openspec/changes/archive/2026-09-22-poe2-companion-m5-session-log-reconciler`.
