# Tasks

## 1. Sensing: Process Presence and Read-Only Log Tailer

- [x] 1.1 Implement `companion/sensing/process_presence.py` with `ProcessMonitor` detecting game states and verify in `tests/sensing/test_process_presence.py`
- [x] 1.2 Implement `companion/sensing/client_log.py` with `ClientLogTailer`, chunking, rotation reset, and chat discarding, and verify in `tests/sensing/test_client_log.py`

## 2. Observation Event Bus

- [x] 2.1 Implement `companion/observations/schema.py` and `companion/observations/bus.py` with typed events and publish/subscribe dispatch, and verify in `tests/observations/test_bus.py`

## 3. State Reconciliation and Journey History

- [x] 3.1 Extend `CharacterState` in `companion/state/schema.py` with live session tracking fields (`current_zone`, `death_count`, `session_active`, `last_observed_at`) and verify in `tests/state/test_live_fields.py`
- [x] 3.2 Implement `companion/state/reconciliation.py` and `companion/state/staleness.py` to reconcile observation events into `CharacterState` and verify in `tests/state/test_reconciliation.py`
- [x] 3.3 Implement `companion/state/history.py` appending normalized events to `runtime/journey_history.jsonl` with chat drop invariant verification in `tests/state/test_history.py`

## 4. CLI Subcommands

- [x] 4.1 Implement `companion session status`, `companion session tail`, and `companion journey list` in `companion/cli.py` and verify in `tests/cli/test_session_cli.py`

## 5. Verification and Acceptance

- [x] 5.1 Implement end-to-end live session integration tests in `tests/test_m5_integration.py` and verify all scenarios pass
- [x] 5.2 Execute full regression suite (`uv run pytest`) and verify all tests pass cleanly
- [x] 5.3 Verify static compliance guard (`uv run pytest tests/compliance/test_no_input_guard.py`) passes cleanly
