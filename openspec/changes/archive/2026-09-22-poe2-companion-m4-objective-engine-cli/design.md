# Design: M4 Objective Engine and CLI v0.1

## Context

The companion has established:
1. Source snapshot validation and normalization (M0).
2. Crash-safe single-writer character state persistence under schema 3.0 (M1, M3).
3. Deterministic offline build deltas, progression phase, and variant resolution (M2).
4. Declarative guide rule evaluation and persistent Level-52 transition state machine (M3).

Downstream consumers (CLI now, session monitor and notifications in M5/M6) need a synthesized, actionable stream of player objectives. This design defines the objective candidate model, the ranking and tie-breaking engine, deterministic template formatting, and the lightweight CLI subcommands.

## Goals / Non-Goals

**Goals:**
- Provide a pure, deterministic `ObjectiveEngine` function: `evaluate_objectives(delta: BuildDeltaResult, transition: Level52TransitionResult | None, character_state: CharacterState, rules: list[GuideRule] | None = None) -> ObjectiveEvaluationResult`.
- Enforce the exact 8-tier categorical priority hierarchy:
  `CRITICAL_MECHANIC_BREAK > HARD_BLOCKER > SURVIVAL_RISK > TRANSITION_REQUIREMENT > CURRENT_PROGRESSION > STRONG_UPGRADE > OPTIMIZATION > FUTURE_PREPARATION`.
- Deterministic 4-level tie-breaking and stable secondary sorting ensuring identical input produces byte-identical output.
- Strict preservation of uncertainty: `UNKNOWN`, `STALE`, `CONFLICTING_EVIDENCE` never produce corrective advice.
- Strict isolation of future requirements: Cast on Dodge at level 52 evaluates as `FUTURE_PREPARATION`, never a current blocker.
- Clean handling of high-end unselected variant: generates a target-selection objective rather than assuming `LVL85`.
- Provide CLI subcommands `companion objectives list`, `companion objectives next`, and `companion evaluate <path>`.
- Emit atomic `CURRENT_OBJECTIVE.json` artifact for external integration.
- Comply strictly with no-input guard and zero-daemon architecture.

**Non-Goals:**
- Continuous background monitoring or daemon loop (deferred to M5).
- Game log tailing or OS window capture (M5, M7).
- Desktop notification dispatch or safe-zone queuing (M6).
- AI/LLM narrative generation or variable text synthesis.
- Numerical scoring or artificial confidence percentages.

## Decisions

### 1. Objective Domain Models
Create `companion/objectives/schema.py`:
- `ObjectivePriority` (IntEnum, 1 to 8):
  1 = `CRITICAL_MECHANIC_BREAK`
  2 = `HARD_BLOCKER`
  3 = `SURVIVAL_RISK`
  4 = `TRANSITION_REQUIREMENT`
  5 = `CURRENT_PROGRESSION`
  6 = `STRONG_UPGRADE`
  7 = `OPTIMIZATION`
  8 = `FUTURE_PREPARATION`
- `EvidenceTrustworthiness` (IntEnum, 1 to 3):
  1 = `VERIFIED`
  2 = `SINGLE_SOURCE`
  3 = `STALE_OR_UNKNOWN`
- `ObjectiveHorizon` (IntEnum, 1 to 2):
  1 = `CURRENT`
  2 = `FUTURE`
- `CostOfIgnoring` (IntEnum, 1 to 2):
  1 = `HIGH`
  2 = `LOW`
- `ObjectiveCandidate`:
  - `id: str` (stable identifier, e.g. `transition:level52:weapon_swap_blocked`)
  - `priority: ObjectivePriority`
  - `title: str`
  - `action: str` (DO NOW text)
  - `rationale: str` (WHY text)
  - `source: str` (SOURCE text)
  - `evidence_trust: EvidenceTrustworthiness`
  - `horizon: ObjectiveHorizon`
  - `cost_of_ignoring: CostOfIgnoring`
  - `is_corrective: bool = False` (flags whether this instructs game state modification vs audit/verification)
  - `metadata: dict[str, Any]`
- `ObjectiveEvaluationResult`:
  - `character_id: str`
  - `character_level: int | None`
  - `primary_objective: ObjectiveCandidate | None`
  - `all_objectives: list[ObjectiveCandidate]`
  - `status: str` (`ACTIONABLE` or `NO_ACTIONABLE_OBJECTIVE`)

*Alternative considered*: Floating point score `priority_score: float`. Rejected per Blueprint v2 and user prompt: numerical scoring introduces fake precision and non-deterministic floating-point comparisons.

### 2. Candidate Generation Rules
Create `companion/objectives/generator.py`:
- **Transition Mapping (M3)**:
  - `BLOCKED`: Emits `HARD_BLOCKER` objective identifying unsatisfied blockers.
  - `VERIFYING`: Emits `TRANSITION_REQUIREMENT` (or audit item), `is_corrective=False`, asking player to verify weapon sets/gear.
  - `PREPARING`: Emits `TRANSITION_REQUIREMENT` informing player of upcoming swap.
  - `READY`: Emits `TRANSITION_REQUIREMENT` indicating player can execute swap.
  - `TRANSITIONING`: Emits `TRANSITION_REQUIREMENT` detailing steps in progress.
  - `COMPLETE`: Emits ZERO transition objectives.
- **Progression Mapping (M2)**:
  - High-end unselected variant (`TargetVariantResolution.status == UNRESOLVED`): Emits `CURRENT_PROGRESSION` or `HARD_BLOCKER` target-selection need (`"Select target variant: ENDGAME, MAGEBLOOD, or DOT_CAP"`).
  - Missing passives (`DeltaStatus.MISSING`): Emits `CURRENT_PROGRESSION` (`"Allocate passive node <id>"`).
  - Unknown passives (`DeltaStatus.UNKNOWN`): Emits audit task (`"Verify passive tree allocations"`), `is_corrective=False`.
  - Missing skills (`DeltaStatus.MISSING`): Emits `CURRENT_PROGRESSION` (`"Equip required skill <gem>"`).
  - Missing equipment (`DeltaStatus.MISSING`): Emits `CURRENT_PROGRESSION` or `STRONG_UPGRADE`.
  - Future requirements (e.g. `Cast on Dodge` with interval `[58, 100]` at level 52): Emits `FUTURE_PREPARATION`, never a blocker.
  - Conflicts: Emits `CRITICAL_MECHANIC_BREAK` or audit task for conflicted source metadata.
- **Survival Risks**:
  - Only generated when backed by an authoritative evaluable `USABLE` rule. Never fabricated without an underlying rule.

### 3. Tie-Breaking and Sorting Engine
Create `companion/objectives/engine.py`:
- Sort tuple:
  `(candidate.priority.value, candidate.evidence_trust.value, candidate.horizon.value, candidate.cost_of_ignoring.value, candidate.id)`
- Deduplication: By `candidate.id` preserving the highest rank.
- Determinism: Python sorting is stable; tie-break includes `candidate.id` ensuring total ordering.

### 4. Template Formatting & CLI Subcommands
Create `companion/objectives/formatter.py`:
- Formats `ObjectiveCandidate` into standard template:
  ```text
  [<PRIORITY>] <title>
  DO NOW: <action>
  WHY: <rationale>
  SOURCE: <source>
  ```
- In `companion/cli.py`:
  - Add `objectives` subparsers for `list` and `next`.
  - Add `evaluate` subparser accepting character JSON path.
  - Atomically save `CURRENT_OBJECTIVE.json` via `atomic_write_file`.

## Risks / Trade-offs

- **[Risk] State loading mismatch if CLI run against un-migrated character state**:
  → *Mitigation*: CLI uses `CharacterStateStore.load_character`, which automatically runs migration (up to v3.0).
- **[Risk] Missing target build when evaluating standalone character**:
  → *Mitigation*: Evaluator resolves build snapshot from `character.build_progression.get('target_build')` or loads default normalized build from source directory.
- **[Risk] Accidental generation of corrective advice for UNKNOWN states**:
  → *Mitigation*: Strict invariant property tests verifying that any candidate derived from `UNKNOWN`, `STALE`, or `CONFLICTING_EVIDENCE` has `is_corrective=False` and DO NOW text focused exclusively on audit/observation.
