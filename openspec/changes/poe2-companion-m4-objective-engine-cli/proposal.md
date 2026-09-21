# Proposal: M4 Objective Engine and CLI v0.1

## Why

Following the completion of M2 (Offline Build Brain) and M3 (Rules Engine & Level-52 Transition State Machine), the companion has authoritative factual evaluations of build deltas, progression phase, guide rules, and transition state. However, the system currently lacks an objective synthesis layer to translate these raw technical deltas into prioritized, actionable guidance for the player.

Building Milestone 4 delivers this deterministic Objective Engine and lightweight CLI v0.1. It generates categorized, tie-broken player objectives strictly consuming M2 and M3 outputs without numerical scoring or artificial confidence percentages, and surfaces them through clear CLI commands and a deterministic `CURRENT_OBJECTIVE.json` artifact.

## What Changes

- **Categorical Priority Hierarchy**: Implements strict 8-tier categorical objective ranking:
  1. `CRITICAL_MECHANIC_BREAK` (e.g. broken build synergy or weapon configuration)
  2. `HARD_BLOCKER` (e.g. blocked level-52 transition from verified unsatisfied blocker)
  3. `SURVIVAL_RISK` (critical defenses; only generated when backed by authoritative rules, never fabricated)
  4. `TRANSITION_REQUIREMENT` (preparing or pending transition actions)
  5. `CURRENT_PROGRESSION` (eligible skill/passive/gear progression for current phase)
  6. `STRONG_UPGRADE` (high-impact equipment/passive upgrades)
  7. `OPTIMIZATION` (secondary refinements)
  8. `FUTURE_PREPARATION` (planning upcoming progression milestones)
- **Deterministic Tie-Breaking & Deduplication**:
  - Secondary sorting: `VERIFIED > SINGLE_SOURCE > STALE/UNKNOWN`, `CURRENT > FUTURE`, `HIGH_COST_OF_IGNORING > LOW`, `OLDER_UNRESOLVED_CRITICAL > NEW_MINOR`.
  - Stable deterministic sorting by priority rank, evidence status, target level, and stable identifier.
  - Deterministic deduplication ensuring identical inputs yield identical output.
- **Uncertainty & Preservation Invariants**:
  - `UNKNOWN`, `STALE`, and `CONFLICTING_EVIDENCE` states NEVER generate corrective advice; they generate structured verification needs.
  - `FUTURE` requirements (including Cast on Dodge at level 52) NEVER evaluate as current blockers.
  - Unresolved high-end variant produces a target-selection/verification need, never an implicit assumption of `LVL85`.
  - M3 `VERIFYING` produces audit/verification work; `BLOCKED` produces factual transition objective; `COMPLETE` produces no historical transition objective.
  - In the absence of actionable objectives, returns structured `NO_ACTIONABLE_OBJECTIVE`.
- **Deterministic Template Output & CURRENT_OBJECTIVE.json**:
  - Formats objectives using deterministic structured templates (`[PRIORITY]`, `DO NOW`, `WHY`, `SOURCE`) without LLM hallucination.
  - Emits `CURRENT_OBJECTIVE.json` with full machine-readable metadata.
- **Lightweight CLI v0.1**:
  - Subcommands under `companion objectives` (`list`, `next`) and `companion evaluate`.
  - Supports formatted human-readable output and `--json` flag.
  - Pure offline execution: strictly no background daemon, no network calls, and passing static no-input compliance.

## Capabilities

### New Capabilities
- `objective-engine`: Deterministic objective candidate generation consuming M2 + M3 outputs, strict 8-tier categorical ranking without numerical scoring or fake confidence, deterministic tie-breaking, uncertainty preservation, and structured `NO_ACTIONABLE_OBJECTIVE`.
- `companion-cli`: Lightweight CLI v0.1 subcommands (`companion objectives list`, `companion objectives next`, `companion evaluate`) supporting human-readable and structured JSON output, producing `CURRENT_OBJECTIVE.json` without background daemons.

### Modified Capabilities
*(None. Existing canonical specs for `build-delta`, `build-eligibility-progression`, `target-resolution`, `level52-transition`, `rule-evaluation`, `character-state`, `source-ingestion`, and `no-input-compliance` remain authoritative and unchanged.)*

## Impact

- **New Code**: Adds `companion/objectives/` module containing candidate generator, ranking engine, template formatter, and model definitions.
- **CLI Extensions**: Expands `companion/cli.py` with `objectives` and `evaluate` subcommands.
- **Dependencies**: Zero new dependencies. Uses existing Python standard library and Pydantic.
- **Safety & Compliance**: Strictly no-input compliant; captures no gameplay input; produces purely read-only advice.
