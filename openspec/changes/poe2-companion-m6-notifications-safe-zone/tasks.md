# Tasks

## 1. Notification Domain Models and Sinks

- [ ] 1.1 Implement `companion/notifications/schema.py` and `companion/notifications/sinks.py` with `NotificationSink`, `InMemorySink`, and `ConsoleSink`, and verify in `tests/notifications/test_schema_and_sinks.py`

## 2. Safe-Zone Policy and Notification Manager

- [ ] 2.1 Implement `companion/notifications/policy.py` with safe-zone classification and cooldown deduplication, and verify in `tests/notifications/test_policy.py`
- [ ] 2.2 Implement `companion/notifications/manager.py` with queue batching and zone transition flush, and verify in `tests/notifications/test_manager.py`

## 3. Session Recap Generator

- [ ] 3.1 Implement `companion/recap/generator.py` and formatter generating summaries from journey history, and verify in `tests/recap/test_generator.py`

## 4. CLI Subcommands

- [ ] 4.1 Implement `companion notify test` and `companion session recap` subcommands in `companion/cli.py` and verify in `tests/cli/test_m6_cli.py`

## 5. Verification and Acceptance

- [ ] 5.1 Implement end-to-end integration scenario in `tests/test_m6_integration.py` verifying combat deferral and safe-zone flush
- [ ] 5.2 Execute full regression suite (`uv run pytest`) and verify 100% pass rate
- [ ] 5.3 Verify static compliance guard (`uv run pytest tests/compliance/test_no_input_guard.py`) passes cleanly
