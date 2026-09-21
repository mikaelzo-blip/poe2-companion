# Milestone 4 Acceptance Report: Objective Engine + CLI v0.1

## Executive Summary
Milestone 4 implements the offline, deterministic Categorical Objective Generation & Ranking Engine and Companion CLI v0.1. The engine synthesizes inputs from M2 (offline build deltas across passives, skills, and equipment), M3 (Level-52 transition state machine and declarative guide rules), and player character state to derive ordered, actionable objectives.

## Key Deliverables & Architecture

### 1. Categorical 8-Tier Priority Ranking
Strict hierarchy without arbitrary numerical scoring or fake confidence metrics:
1. `CRITICAL_MECHANIC_BREAK`: Synergies broken or contradictory setups preventing basic functioning.
2. `HARD_BLOCKER`: Unsatisfied prerequisites on progression transitions (e.g. Level-52 swap blocked).
3. `SURVIVAL_RISK`: Critical defensive deficiencies gated strictly by authoritative, evaluable `USABLE` rules.
4. `TRANSITION_REQUIREMENT`: Active preparation or execution steps for milestone transitions.
5. `CURRENT_PROGRESSION`: Available, level-eligible missing passives, active skills, or core equipment.
6. `STRONG_UPGRADE`: High-impact enhancements (socket links, primary affix upgrades).
7. `OPTIMIZATION`: Secondary quality improvements and stat tuning.
8. `FUTURE_PREPARATION`: Clear isolation of future progression requirements (e.g., Cast on Dodge [58, 100] at level 52).

### 2. Deterministic Tie-Breaking & Deduplication
- Primary sort by priority enum (1..8).
- Secondary tie-breaks: Evidence trustworthiness (`VERIFIED > SINGLE_SOURCE > STALE_OR_UNKNOWN`), horizon (`CURRENT > FUTURE`), cost of ignoring (`HIGH > LOW`), stable lexicographical candidate ID.
- Fallback empty state returns structured `NO_ACTIONABLE_OBJECTIVE`.

### 3. Four-Part Block Template Formatting
Deterministic text formatter rendering:
```
[<PRIORITY_RANK>] <Objective Title>
DO NOW: <Specific concrete action to take>
WHY: <Underlying factual cause and progression impact>
SOURCE: <Source provenance>
```

### 4. CLI v0.1 Subcommands
- `companion objectives list [--id <char_id>] [--runtime <dir>] [--json]`: Lists all active objectives in deterministic priority order.
- `companion objectives next [--id <char_id>] [--runtime <dir>] [--json]`: Emits the single highest-priority actionable objective.
- `companion evaluate <char_json_file> [--out <dest>] [--json]`: Evaluates character state offline, writes `CURRENT_OBJECTIVE.json` atomically, and emits the primary objective.

## Verification & Test Results
- Total Tests in Repository: 321 passing, 0 failing.
- Objective Engine Unit & Golden Tests: 35 tests covering schema, candidate generator, ranking engine, template formatter, CLI subcommands, golden scenarios, and invariants.
- Static No-Input Compliance: 9 passing tests verifying zero prohibited imports or native automation tokens.
- OpenSpec Validation: 10 canonical specifications valid with zero errors.
