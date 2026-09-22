# Tasks: Milestone 10 — Official API + Deeper PoB2

## 1. OAuth PKCE & User-Agent Enforcement

- [x] 1.1 Implement `companion/api/oauth.py` with PKCE challenge generation, User-Agent enforcement, and `EXTERNALLY_BLOCKED` detection, and verify with `tests/api/test_oauth.py`

## 2. 4xx Circuit Breaker & Resilience

- [x] 2.1 Implement `companion/api/circuit_breaker.py` with 4xx tripping, cooldown timer, and state transitions, and verify with `tests/api/test_circuit_breaker.py`

## 3. Official API Schema & Mock Adapter

- [x] 3.1 Implement `companion/api/schema.py`, `companion/api/client.py`, and `companion/api/mock_adapter.py`, and verify with `tests/api/test_client_and_schema.py`

## 4. Deeper PoB2 Comparison & Patch Drift

- [x] 4.1 Implement `companion/api/pob2_comparator.py` and CLI subcommands in `companion/cli.py`, and verify with `tests/api/test_pob2_and_cli.py`

## 5. End-to-End Verification & Compliance

- [x] 5.1 Implement end-to-end integration test in `tests/test_m10_integration.py`
- [x] 5.2 Execute full regression test suite (`uv run pytest`) and verify 100% pass rate
- [x] 5.3 Verify static compliance guard (`uv run pytest tests/compliance/test_no_input_guard.py`)
