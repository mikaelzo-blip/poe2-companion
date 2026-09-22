# Tasks

## 1. Vision Domain Models, Privacy, and Budget Tracker

- [x] 1.1 Implement `companion/vision/schema.py`, `companion/vision/privacy.py`, and `companion/vision/budget.py` and verify in `tests/vision/test_budget_and_privacy.py`

## 2. Screen Classifier and Character Panel Parser

- [x] 2.1 Implement `companion/vision/classifier.py` and `companion/vision/parser.py` with multi-capture verification logic, and verify in `tests/vision/test_classifier_and_parser.py`

## 3. Screenshot Cache Policy

- [x] 3.1 Implement `companion/vision/cache.py` with TTL and LRU max-MB enforcement and verify in `tests/vision/test_cache.py`

## 4. CLI Subcommands

- [x] 4.1 Implement `companion vision status` and `companion vision parse-panel` subcommands in `companion/cli.py` and verify in `tests/cli/test_m7_cli.py`

## 5. Verification and Acceptance

- [x] 5.1 Implement end-to-end integration scenario in `tests/test_m7_integration.py` verifying multi-capture corroboration and observation bus emission
- [x] 5.2 Execute full regression suite (`uv run pytest`) and verify 100% pass rate
- [x] 5.3 Verify static compliance guard (`uv run pytest tests/compliance/test_no_input_guard.py`) passes cleanly
