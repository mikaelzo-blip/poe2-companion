# Tasks: Milestone 9 — Expanded Build Intelligence

## 1. Intelligence Schema & Survival Rules

- [ ] 1.1 Implement `companion/intelligence/schema.py` and `companion/intelligence/survival.py`, and verify with `tests/intelligence/test_survival_rules.py`

## 2. Gear & Troubleshooting Rules

- [ ] 2.1 Implement `companion/intelligence/gear_rules.py` and `companion/intelligence/troubleshooting.py`, and verify with `tests/intelligence/test_gear_and_troubleshooting.py`

## 3. Story Progression & Economy Advisors

- [ ] 3.1 Implement `companion/intelligence/story.py` and `companion/intelligence/economy.py`, and verify with `tests/intelligence/test_story_and_economy.py`

## 4. CLI Subcommands Integration

- [ ] 4.1 Implement `companion intelligence` CLI subcommands (`audit`, `story`, `economy`) in `companion/cli.py`, and verify with `tests/cli/test_m9_cli.py`

## 5. End-to-End Verification & Compliance

- [ ] 5.1 Implement end-to-end integration test in `tests/test_m9_integration.py`
- [ ] 5.2 Execute full regression test suite (`uv run pytest`) and verify 100% pass rate
- [ ] 5.3 Verify static compliance guard (`uv run pytest tests/compliance/test_no_input_guard.py`)
