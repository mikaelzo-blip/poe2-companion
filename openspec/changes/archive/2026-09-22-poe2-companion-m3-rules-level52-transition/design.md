# Design: Milestone 3 — Rule Evaluation and Persistent Level-52 Transition

## Context

Milestone 2 introduced the offline Build Brain, providing pure, deterministic delta calculation (`BuildDeltaResult`), eligibility checking (`EligibilityState`), progression phase resolution (`ProgressionPhase`), and observation coverage policy (`ObservationCoverage`). However, M2 does not evaluate gameplay rules (e.g. from written guides or declarative rule files) and does not model progression transitions that persist across levels and sessions.

The Level-52 weapon swap (transitioning from single-weapon leveling to dual weapon set: Staff in set 1, Crossbow in set 2) is Path of Exile 2's primary build milestone for the Fubgun Flameblast Oil Grenade build. Because players may level past 52 while offline, launch the companion for the first time at high levels (e.g. level 60), or encounter requirements that unlock at higher levels (such as Cast on Dodge at level 58), the companion requires an explicit rule evaluation engine and a persistent, crash-safe transition state machine.

Critically, the `.build` skill structure does not provide a trustworthy weapon-set assignment field. M3 must not fabricate skill weapon-set assignments (e.g., claiming "Flameblast belongs to weapon set X") without an observable and usable source basis. Furthermore, completion represents the historical transition itself rather than requiring the entire current build to match the level-52 snapshot exactly.

See `proposal.md` for motivation and `specs/` for behavioral requirements.

## Goals / Non-Goals

**Goals:**
- Implement an explicit, lightweight declarative rule schema and evaluator supporting 6 semantic result states: `PASS`, `FAIL`, `UNKNOWN`, `NOT_APPLICABLE`, `STALE`, and `CONFLICTING_EVIDENCE`.
- Implement an explicit `TransitionRuleRole` enum (`BLOCKING_REQUIREMENT`, `COMPLETION_EVIDENCE`, `ADVISORY`, `PREPARATION`), decoupled from requirement type, observability methods, rule name, or source type.
- Enforce source verification trust: rules marked `PENDING_SOURCE_VERIFICATION` evaluate conservatively as `UNKNOWN`, cannot produce `PASS` or `FAIL`, cannot independently produce `BLOCKED` or prove `COMPLETE`, and are not counted as unsatisfied authoritative blockers so they never deadlock `READY`. `UNAVAILABLE` rules also cannot gate transitions.
- Implement a 7-state persistent Level-52 transition state machine: `NOT_RELEVANT`, `PREPARING`, `VERIFYING`, `BLOCKED`, `READY`, `TRANSITIONING`, `COMPLETE`.
- Prohibit invented pre-52 preparation level thresholds (no arbitrary 45, 50, 51 thresholds). Characters below level 52 evaluate to `NOT_RELEVANT` unless an applicable `USABLE` rule with role `PREPARATION` exists.
- Implement tri-state requirement readiness (`SATISFIED`, `UNSATISFIED`, `UNKNOWN`), where only `USABLE` rules with role `BLOCKING_REQUIREMENT` gate blocking/readiness.
- Support transition status flags `transition_pending` and `missed_transition` as deterministically derived current-condition outputs rather than independently mutable persisted state, preventing drift.
- Model completion via explicit `USABLE` `COMPLETION_EVIDENCE` rules without requiring exact equality to the entire level-52 snapshot and without inferring skill weapon-set assignments from `.build`.
- Safely handle offline skips and late installs: level 60 with verified completion evidence evaluates directly to `COMPLETE` without false warnings; insufficient evidence resolves to `VERIFYING` (never false `BLOCKED` or false `COMPLETE`).
- Strictly isolate future requirements: M2 `FUTURE` requirements (e.g., Cast on Dodge at level 52) never block level-52 readiness, and reaching level 58 never reopens a completed level-52 transition.
- Persist transition state via the M1 `CharacterStore`, upgrading `CharacterState` to schema version `3.0` with `transition: Level52TransitionRecord | None = None`.
- Ensure schema migration `2.0 -> 3.0` sets `transition = None` (uninitialized), refusing to invent historical transition states during data migration. Deterministic initialization occurs on first evaluation.
- Maintain 100% determinism with zero live game sensors, OCR, or third-party workflow engines.

**Non-Goals:**
- No M4 objective engine, candidate generation, or priority ranking (`CRITICAL`, `HARD_BLOCKER`).
- No live game sensors, Client.txt log watcher, memory inspection, or process hooks (strict no-input compliance).
- No OCR, computer vision, or screenshot capture implementations (declarative `observable_via` only).
- No Windows notifications, audio cues, or toast popups.
- No PoB2 parser or synthetic data fabrication (respect source availability boundaries).
- No skill weapon-set assignment inference from `.build`.
- No historical journey/event log infrastructure in M3.
- No external state machine library or database framework (plain Python + Pydantic v2).

## Decisions

### 1. Architectural Placement and Modular Structure
- **Decision**: Structure M3 as two focused packages: `companion/rules/` and `companion/transition/`.
- **Rationale**: Clean separation of concerns. `companion/rules/` handles declarative rule loading, schema validation, and stateless rule evaluation. `companion/transition/` handles the persistent state machine, requirement aggregation, transition flags, and state store integration.
- **Alternatives Considered**:
  - *Combine into `companion/build/`*: Rejected. M2 build delta calculation is an offline factual diff; M3 rule evaluation and state machine orchestration represent an operational transition layer. Keeping them distinct preserves single-responsibility modularity.
  - *Single monolithic `companion/progression/` module*: Rejected. Unnecessarily bundles generic rule checking with level-52 state machine mechanics.

### 2. Rule Schema, Declarative Observability, and Transition Roles
- **Decision**: Define typed enums and the Pydantic model `GuideRule` with explicit transition roles:
  ```python
  class RuleSourceType(str, Enum):
      BLUEPRINT_V2 = "BLUEPRINT_V2"
      FUBGUN_BUILD = "FUBGUN_BUILD"
      WRITTEN_GUIDE = "WRITTEN_GUIDE"
      POB2_REFERENCE = "POB2_REFERENCE"
      LABELED_INFERENCE = "LABELED_INFERENCE"

  class SourceVerificationStatus(str, Enum):
      USABLE = "USABLE"
      PENDING_SOURCE_VERIFICATION = "PENDING_SOURCE_VERIFICATION"
      UNAVAILABLE = "UNAVAILABLE"

  class ObservabilityMethod(str, Enum):
      API = "API"
      GEAR_AUDIT = "GEAR_AUDIT"
      SKILL_AUDIT = "SKILL_AUDIT"
      PASSIVE_AUDIT = "PASSIVE_AUDIT"
      VISION = "VISION"
      MANUAL = "MANUAL"

  class RuleEvaluationState(str, Enum):
      PASS = "PASS"
      FAIL = "FAIL"
      UNKNOWN = "UNKNOWN"
      NOT_APPLICABLE = "NOT_APPLICABLE"
      STALE = "STALE"
      CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"

  class TransitionRuleRole(str, Enum):
      BLOCKING_REQUIREMENT = "BLOCKING_REQUIREMENT"
      COMPLETION_EVIDENCE = "COMPLETION_EVIDENCE"
      ADVISORY = "ADVISORY"
      PREPARATION = "PREPARATION"
  ```
  - **Explicit Role Semantics**:
    - `BLOCKING_REQUIREMENT`: May participate in `BLOCKED` and `READY`, but only when `source_status == USABLE` and the rule is currently applicable.
    - `COMPLETION_EVIDENCE`: May contribute to proving the historical Level-52 transition is `COMPLETE`, provided `source_status == USABLE`. It does not automatically become a `READY` blocker unless separately modeled as a blocking requirement.
    - `PREPARATION`: May establish `PREPARING` before level 52 only when `source_status == USABLE` and applicability matches.
    - `ADVISORY`: Never gates `READY`, `BLOCKED`, or `COMPLETE`. Informational only (M4 may consume later).
  - **Prohibition on Implicit Inference**: The transition role is an explicit attribute of `GuideRule`. It must never be derived implicitly from `RequirementType`, observability method, rule name, or source type.
- **Rationale**: Directly aligns with Blueprint v2 Section 27-28 and eliminates ambiguity about how individual rules interact with the transition state machine.
- **Alternatives Considered**: Dynamic DSL or rule script execution (e.g. JSONLogic). Rejected as overengineered; explicit typed models are safer, faster, and easier to test.

### 3. Source Verification Trust Gating and Deadlock Prevention
- **Decision**: When a rule's source verification status is `PENDING_SOURCE_VERIFICATION`, the rule evaluator evaluates the condition conservatively:
  - It produces `UNKNOWN` with reason `PENDING_SOURCE_VERIFICATION`.
  - It SHALL NOT produce `FAIL` or `PASS`.
  - It cannot independently produce `BLOCKED`.
  - It cannot independently prove `COMPLETE`.
  - It is NOT counted as an unsatisfied authoritative blocker when calculating readiness.
  - It can appear in structured output as an unresolved source need, but cannot permanently deadlock `READY`.
  - `UNAVAILABLE` rules also cannot gate transition decisions.
  - Rules are never silently upgraded to `USABLE`.
- **Rationale**: Mandated by Blueprint v2 and M0 anomaly findings. Unverified external guide rules must not masquerade as authoritative truth, trigger false blocking alerts, or deadlock transition progression.
- **Alternatives Considered**: Skip pending rules entirely during evaluation. Rejected: returning `UNKNOWN` preserves observability and audit trails while preventing false blocking gates.

### 4. Tri-State Requirement Readiness Model
- **Decision**: Model requirement readiness as an explicit enum:
  ```python
  class RequirementReadiness(str, Enum):
      SATISFIED = "SATISFIED"
      UNSATISFIED = "UNSATISFIED"
      UNKNOWN = "UNKNOWN"
  ```
  - `SATISFIED`: Evidence definitively verifies the requirement is met under a `USABLE` rule.
  - `UNSATISFIED`: Evidence definitively verifies the requirement is not met (active blocker under a `USABLE` `BLOCKING_REQUIREMENT` rule).
  - `UNKNOWN`: Missing observation, partial audit, stale data, conflicting evidence, or `PENDING_SOURCE_VERIFICATION`.
- **Rationale**: Avoids binary collapse. Incomplete data is neither a confirmed satisfaction nor an active blocker. A transition can only become `READY` when all applicable `USABLE` blocking requirements are `SATISFIED`.

### 5. Level-52 Persistent State Machine Lifecycle
- **Decision**: Implement seven persistent states without invented preparation thresholds:
  ```python
  class Level52TransitionState(str, Enum):
      NOT_RELEVANT = "NOT_RELEVANT"
      PREPARING = "PREPARING"
      VERIFYING = "VERIFYING"
      BLOCKED = "BLOCKED"
      READY = "READY"
      TRANSITIONING = "TRANSITIONING"
      COMPLETE = "COMPLETE"
  ```
  - **State Transitions**:
    - `level < 52`:
      - If an applicable `USABLE` rule with role `PREPARATION` is active and satisfied: evaluates to `PREPARING`.
      - Otherwise: evaluates to `NOT_RELEVANT` (e.g. level 51 without an applicable usable preparation rule evaluates strictly to `NOT_RELEVANT`).
      - A rule with `PENDING_SOURCE_VERIFICATION` cannot establish `PREPARING`.
    - `level >= 52`:
      - If previously `NOT_RELEVANT` or `PREPARING`: enters `VERIFYING`.
      - If in `VERIFYING`:
        - If any applicable `USABLE` blocking requirement is `UNSATISFIED`: moves to `BLOCKED`.
        - If all applicable `USABLE` blocking requirements are `SATISFIED`: moves to `READY`.
        - Otherwise remains in `VERIFYING`.
      - If in `BLOCKED`:
        - If all applicable `USABLE` blocking requirements become `SATISFIED`: moves to `READY`.
        - If failing requirements become unobserved/stale: reverts to `VERIFYING`.
      - If in `READY`:
        - If any applicable `USABLE` requirement becomes `UNSATISFIED`: reverts to `BLOCKED`.
        - If any applicable `USABLE` requirement becomes unobserved/stale: reverts to `VERIFYING`.
        - On explicit transition start signal: moves to `TRANSITIONING`.
      - If in `TRANSITIONING`:
        - If post-swap evidence matching `USABLE` `COMPLETION_EVIDENCE` rules is verified: moves to `COMPLETE`.
        - If canceled/reset: reverts to `VERIFYING` or `BLOCKED`.
      - If in `COMPLETE`:
        - Terminal/absorbing milestone state; remains `COMPLETE` regardless of level advancement (e.g. level 58+) or subsequent future requirements.
- **Rationale**: Matches Blueprint v2 Section 25, prevents oscillation, and eliminates ungrounded pre-transition assumptions.

### 6. Completion Evidence vs Full Build Snapshot
- **Decision**:
  - Proving `COMPLETE` requires satisfying explicitly modeled `COMPLETION_EVIDENCE` rules whose sources are currently `USABLE`.
  - Completion represents the historical transition itself, NOT exact equality to the full level-52 snapshot (`current build == exact lvl52 snapshot` is rejected). A character loaded at level 60 who has evolved their build is recognized as `COMPLETE` if minimal explicit completion evidence markers remain.
  - Strictly prohibit inferring skill weapon-set assignments from `.build` files, as the `.build` structure does not contain a trustworthy weapon-set assignment field. Completion rules assert known equipment facts and skill group presences without fabricating weapon-set assignments.
  - If evidence is insufficient to verify completion: resolves to `VERIFYING` (neither false `BLOCKED` nor false `COMPLETE`).
- **Rationale**: Prevents false blocking alarms for legitimately progressed high-level characters while maintaining strict fidelity to verifiable source facts.

### 7. Transition Status Flags: Derived Conditions vs Persisted Facts
- **Decision**: Avoid storing redundant flags that can drift from canonical state.
  - Persisted canonical state: `state: Level52TransitionState`, `requirements: dict[str, RequirementReadiness]`, timestamps/metadata.
  - Deterministically derived outputs:
    - `transition_pending = (level > 52 and state != Level52TransitionState.COMPLETE)`
    - `missed_transition = (level > 52 and state != Level52TransitionState.COMPLETE and has_verified_preswap_evidence)`
    - Once state becomes `COMPLETE`: `missed_transition` evaluates to `False`.
  - No historical journey/event log infrastructure is created in M3.
- **Rationale**: Eliminates synchronization drift between persistent state and alert flags.

### 8. Future Requirement Isolation (Cast on Dodge)
- **Decision**: M3 transition engine consumes M2 build delta and eligibility evaluations. When evaluating Level-52 requirements:
  - Requirements with eligibility starting > 52 (such as `Cast on Dodge` with interval `[58, 100]`) evaluate to `EligibilityState.FUTURE` in M2.
  - The Level-52 transition engine filters requirements: only requirements with `min_level <= 52` (or interval containing 52) are considered applicable transition blockers.
  - When the character subsequently reaches level 58, Cast on Dodge becomes `ACTIVE` in M2 progression, but this does not retroactively alter or reopen a `COMPLETE` level-52 transition.
- **Rationale**: Fully complies with Blueprint v2 Section 60 and ensures future build evolution does not invalidate past progression milestones.

### 9. State Persistence and Schema 3.0 Migration
- **Decision**:
  - Upgrade `CharacterState` schema to `3.0`.
  - Persist transition state as an optional field:
    ```python
    transition: Level52TransitionRecord | None = None
    ```
  - Define `Level52TransitionRecord`:
    ```python
    class Level52TransitionRecord(BaseModel):
        state: Level52TransitionState = Level52TransitionState.NOT_RELEVANT
        requirements: dict[str, RequirementReadiness] = Field(default_factory=dict)
        last_evaluated_at: str | None = None
        verified_at: str | None = None
        notes: str | None = None
    ```
  - Schema migration `2.0 -> 3.0` (`migrate_2_0_to_3_0` in `companion/state/migrations.py`) sets `transition = None` (uninitialized). It SHALL NOT infer `NOT_RELEVANT`, `PREPARING`, `BLOCKED`, `READY`, or `COMPLETE` during schema migration.
  - The first M3 evaluation post-migration performs deterministic initialization from:
    - current character level
    - available M2 build delta result
    - usable rules
    - trustworthy evidence
    Examples:
    - `level < 52 + no usable prep rule -> NOT_RELEVANT`
    - `level >= 52 + insufficient evidence -> VERIFYING`
    - `level >= 52 + verified completion evidence -> COMPLETE`
    - `level > 52 + verified pre-swap evidence -> BLOCKED (with derived missed_transition=True)`
- **Rationale**: Keeps schema migration strictly focused on data layout, avoiding the creation of invented domain facts during migration.

## Risks / Trade-offs

- **[Risk] Incomplete observations causing prolonged `VERIFYING` state**:
  → *Mitigation*: This is the intended conservative behavior. The companion explicitly documents which specific observation coverage is missing (via `unknowns` in the transition result) so future audit commands can resolve them.
- **[Risk] Schema migration corruption during upgrade**:
  → *Mitigation*: M1's `CharacterStore` performs pre-write backup copying and atomic file replacement. Migration leaves `transition = None`, ensuring zero risk of domain inference bugs during deserialization.
- **[Risk] Unverified guide rules stalling progression**:
  → *Mitigation*: Rules with `PENDING_SOURCE_VERIFICATION` evaluate to `UNKNOWN` and are explicitly excluded from the set of authoritative blockers required for `READY`, preventing progression deadlocks.

## Migration Plan

1. Define `Level52TransitionRecord` in `companion/transition/state.py`.
2. Update `companion/state/schema.py`:
   - Set `CURRENT_SCHEMA_VERSION = "3.0"`.
   - Add `transition: Level52TransitionRecord | None = None`.
3. Update `companion/state/migrations.py`:
   - Implement `migrate_2_0_to_3_0(data: dict) -> dict` setting `data["transition"] = None` and `data["schema_version"] = "3.0"`.
   - Register `"2.0": migrate_2_0_to_3_0` in `MIGRATION_REGISTRY`.
4. Run regression tests on `tests/state/` to confirm v1 and v2 fixtures load cleanly and migrate to v3 with `transition = None`, followed by deterministic initialization on evaluation.