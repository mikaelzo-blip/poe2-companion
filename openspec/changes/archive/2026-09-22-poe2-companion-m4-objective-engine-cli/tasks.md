# Tasks: M4 Objective Engine and CLI v0.1

## 1. Objective Domain Schemas and Models

- [x] 1.1 Implement ObjectivePriority (8 tiers), EvidenceTrustworthiness, ObjectiveHorizon, CostOfIgnoring enums in `companion/objectives/schema.py` and verify enum definitions in unit tests
- [x] 1.2 Implement ObjectiveCandidate and ObjectiveEvaluationResult Pydantic models in `companion/objectives/schema.py` and verify serialization roundtrip in unit tests

## 2. Objective Candidate Generator

- [x] 2.1 Implement transition candidate generator in `companion/objectives/generator.py` consuming M3 `Level52TransitionResult` and verify BLOCKED, VERIFYING, PREPARING, READY, and COMPLETE cases in unit tests
- [x] 2.2 Implement build delta candidate generator in `companion/objectives/generator.py` consuming M2 `BuildDeltaResult` (passives, skills, equipment) and verify progression phase mapping in unit tests
- [x] 2.3 Implement uncertainty preservation logic in `companion/objectives/generator.py` ensuring UNKNOWN, STALE, and CONFLICTING_EVIDENCE produce non-corrective audit requests, verified by invariant unit tests
- [x] 2.4 Implement future requirement isolation ensuring Cast on Dodge at level 52 produces FUTURE_PREPARATION rather than a blocker, verified by unit tests
- [x] 2.5 Implement survival risk gating ensuring survival objectives are generated only when backed by authoritative evaluable USABLE rules, verified by unit tests

## 3. Objective Ranking, Tie-Breaking, and Formatting Engine

- [x] 3.1 Implement deterministic categorical sorting and tie-breaking engine in `companion/objectives/engine.py` and verify ordering determinism across identical and varied inputs in unit tests
- [x] 3.2 Implement empty fallback handling returning structured `NO_ACTIONABLE_OBJECTIVE` when no tasks remain, verified by unit tests
- [x] 3.3 Implement deterministic template formatter in `companion/objectives/formatter.py` rendering `[<PRIORITY>]`, `DO NOW:`, `WHY:`, `SOURCE:` and verify template formatting tests pass

## 4. CLI Subcommands and Artifact Output

- [x] 4.1 Implement `companion objectives list` and `companion objectives next` subcommands in `companion/cli.py` and verify human-readable and JSON CLI output in unit tests
- [x] 4.2 Implement `companion evaluate` subcommand in `companion/cli.py` writing `CURRENT_OBJECTIVE.json` atomically and verify artifact persistence in CLI tests

## 5. Golden Scenarios, Invariants, and Regression Verification

- [x] 5.1 Implement golden scenarios and invariant property tests in `tests/objectives/test_golden_objectives.py` and `tests/objectives/test_invariants.py` and verify all tests pass
- [x] 5.2 Execute full regression test suite (`uv run pytest`) and verify all tests pass cleanly
- [x] 5.3 Execute static no-input compliance test suite (`tests/compliance/test_no_input_guard.py`) and verify zero violations
