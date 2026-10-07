# Tasks

## 1. Engine Timeout and Recovery (`path-of-building-2-mcp`)

- [x] 1.1 Fix missing `import time` and define `EngineTimeoutError(EngineError)` in `server/pob_mcp/engine.py` and verify with python syntax check
- [x] 1.2 Implement reader thread + `queue.Queue` with `call_timeout` in `PobEngine.call()` and verify timeout raises `EngineTimeoutError`, terminates subprocess, and releases lock
- [x] 1.3 Implement `restart()` and `ensure_alive()` on `PobEngine` and verify with unit tests in `path-of-building-2-mcp`

## 2. Session Health Tracking and Auto-Recovery (`poe2-companion`)

- [x] 2.1 Add `is_healthy` and `unhealthy_reason` state attributes to `Pob2EquipmentSession` in `companion/equipment/pob2_equipment_advisor.py` and verify initialization defaults
- [x] 2.2 Wrap simulation calls to handle `EngineError`: mark session unhealthy, abort without auto-retry, and verify with unit tests
- [x] 2.3 Implement single-restart recovery (`_recover_session()`) on subsequent calls when session is unhealthy and verify recovery re-imports baseline XML
- [x] 2.4 Replace `except Exception: pass` in simulation `finally` blocks with logger warnings and degrade session health on restore failure
- [x] 2.5 Expose engine health in `get_dashboard_status()` and `/api/status` endpoint in `companion/dashboard_api.py` and `companion/dashboard_server.py` and verify endpoint response

## 3. Unified Verdict Merge and Slot Path Consolidation (`poe2-companion`)

- [x] 3.1 Implement canonical `merge_verdicts(policy_verdict, tactical_verdict)` in `companion/equipment/tactical_advisor.py` and verify unit tests
- [x] 3.2 Refactor weapon path in `companion/dashboard_api.py` to use `merge_verdicts()` and preserve tactical veto
- [x] 3.3 Refactor ring path in `companion/dashboard_api.py` to use `merge_verdicts()` and preserve tactical veto
- [x] 3.4 Refactor generic slot path in `companion/dashboard_api.py` to use `merge_verdicts()`, eliminating the override divergence
- [x] 3.5 Build comprehensive 3x9 verdict matrix test suite across all 3 paths in `tests/unit/equipment/test_verdict_consolidation_matrix.py` and verify all tests pass

## 4. Verification and Regression Testing

- [x] 4.1 Run full companion test suite (`uv run pytest`) and verify 100% pass rate
- [x] 4.2 Verify no regression across existing dashboard API, live watcher, and equipment integration tests
