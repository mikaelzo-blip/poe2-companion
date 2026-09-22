# Tasks

## 1. Gear Schema and Deterministic Hasher

- [x] 1.1 Implement `companion/gear/schema.py` and `companion/gear/hasher.py` and verify in `tests/gear/test_schema_and_hasher.py`

## 2. Tooltip Parser and Stability Verification

- [x] 2.1 Implement `companion/gear/tooltip.py` with multi-capture stability gate and stat/mod extraction, and verify in `tests/gear/test_tooltip.py`

## 3. Gear Comparison, TTL Staleness, and Mechanic Conflicts

- [x] 3.1 Implement `companion/gear/evaluator.py`, `companion/gear/advisor.py`, and `companion/gear/conflicts.py`, and verify in `tests/gear/test_evaluator_and_conflicts.py`

## 4. Guided Slot Audit and CLI Subcommands

- [x] 4.1 Implement `companion/gear/audit.py` and `companion gear` subcommands in `companion/cli.py`, and verify in `tests/cli/test_m8_cli.py`

## 5. Verification and Acceptance

- [x] 5.1 Implement end-to-end integration scenario in `tests/test_m8_integration.py` verifying full audit, comparison, and conflict detection pipeline
- [x] 5.2 Execute full regression suite (`uv run pytest`) and verify 100% pass rate
- [x] 5.3 Verify static compliance guard (`uv run pytest tests/compliance/test_no_input_guard.py`) passes cleanly
