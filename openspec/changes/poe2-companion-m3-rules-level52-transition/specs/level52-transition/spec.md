# Spec Delta

## Purpose

Provides a persistent Level-52 transition state machine and history tracking engine that safely manages the critical dual weapon set swap across character levels, restarts, and late installations.

## ADDED Requirements

### Requirement: Persistent Level-52 Transition State Model
The system SHALL manage the Level-52 weapon swap using seven persistent states: `NOT_RELEVANT`, `PREPARING`, `VERIFYING`, `BLOCKED`, `READY`, `TRANSITIONING`, and `COMPLETE`. The transition state SHALL persist across levels and sessions rather than being evaluated as a transient single-level event. The system SHALL NOT invent arbitrary pre-52 preparation level thresholds (such as level 45, 50, or 51). For a character below level 52 without an applicable `USABLE` rule with role `PREPARATION`, the state SHALL evaluate to `NOT_RELEVANT`.

#### Scenario: Pre-transition character state without usable preparation rule
- **WHEN** character level is below 52 (such as level 51) and no applicable `USABLE` preparation rule exists
- **THEN** the transition state evaluates to `NOT_RELEVANT`

#### Scenario: Pre-transition character state with usable preparation rule
- **WHEN** character level is below 52 (such as level 51) and an applicable `USABLE` rule with role `PREPARATION` is established and active
- **THEN** the transition state evaluates to `PREPARING`

#### Scenario: Pre-transition character state with pending source preparation rule
- **WHEN** character level is below 52 and a preparation rule has source status `PENDING_SOURCE_VERIFICATION`
- **THEN** the rule does not create an authoritative preparation threshold and transition state evaluates to `NOT_RELEVANT`

#### Scenario: Level 52 reached with unknown evidence
- **WHEN** character reaches level 52 and player equipment or skill observations are unobserved or incomplete
- **THEN** the transition state evaluates to `VERIFYING` rather than `COMPLETE` or `BLOCKED`

#### Scenario: Completed transition persists across higher levels
- **WHEN** a character has achieved `COMPLETE` status and advances to subsequent levels (such as level 58 or 60)
- **THEN** the transition state remains `COMPLETE` idempotently without reverting

### Requirement: Transition History and Alert Status Flags
The system SHALL evaluate transition status flags `transition_pending` and `missed_transition` as deterministically derived current-condition outputs rather than independently mutable persisted booleans to prevent drift from canonical state. `transition_pending` SHALL be derived as true whenever character level is greater than 52 while the transition state is not `COMPLETE`. `missed_transition` SHALL be derived as true only when character level is greater than 52, transition state is not `COMPLETE`, and verified observations confirm that pre-swap build configuration remains active. Once the transition becomes `COMPLETE`, `missed_transition` SHALL resolve to false.

#### Scenario: Character advances past level 52 without completing swap
- **WHEN** character level is 53 or higher and the transition state is not `COMPLETE`
- **THEN** `transition_pending` is derived as true

#### Scenario: Verified old build at level greater than 52 triggers MISSED_TRANSITION
- **WHEN** character level is 53 or higher, transition is incomplete, and verified observations show old pre-swap items remain equipped
- **THEN** `missed_transition` is derived as true

#### Scenario: Incomplete evidence does not trigger MISSED_TRANSITION
- **WHEN** character level is 53 or higher, transition is incomplete, but player equipment observations are unknown or partial
- **THEN** `missed_transition` remains false and the system remains in `VERIFYING` with `transition_pending` true

#### Scenario: Transition completion clears MISSED_TRANSITION
- **WHEN** transition state reaches `COMPLETE`
- **THEN** `missed_transition` resolves to false and `transition_pending` resolves to false

### Requirement: Readiness and Blocking Evaluation Semantics
The transition state machine SHALL deterministically evaluate readiness using only applicable rules with source status `USABLE` and role `BLOCKING_REQUIREMENT`. The system SHALL evaluate to `BLOCKED` only when verified evidence proves that at least one currently applicable `USABLE` blocking requirement is `UNSATISFIED`. The system SHALL evaluate to `VERIFYING` when evidence is missing, partial, stale, or conflicting. Rules marked `PENDING_SOURCE_VERIFICATION` or `UNAVAILABLE` SHALL NOT produce `FAIL`, cannot independently cause `BLOCKED`, and SHALL NOT be counted as unsatisfied authoritative blockers, ensuring unverified rules never deadlock `READY`. The system SHALL evaluate to `READY` only when all currently applicable `USABLE` blocking requirements are definitively `SATISFIED`.

#### Scenario: Verified failed usable blocking requirement triggers BLOCKED
- **WHEN** fresh, verified observations show an applicable `USABLE` blocking requirement is unsatisfied
- **THEN** transition state transitions to `BLOCKED`

#### Scenario: Incomplete observations trigger VERIFYING
- **WHEN** transition requirements cannot be verified due to unobserved slots or stale audits
- **THEN** transition state evaluates to `VERIFYING` and does not evaluate to `BLOCKED`

#### Scenario: Pending source verification rule does not deadlock READY
- **WHEN** all applicable `USABLE` blocking requirements are `SATISFIED`, but a rule is marked `PENDING_SOURCE_VERIFICATION`
- **THEN** the pending rule evaluates to `UNKNOWN` with unresolved source need, is not counted as an unsatisfied authoritative blocker, and the transition state evaluates to `READY`

#### Scenario: All applicable usable blocking requirements satisfied triggers READY
- **WHEN** all currently applicable `USABLE` blocking requirements evaluate to `SATISFIED`
- **THEN** transition state transitions to `READY`

### Requirement: Future Requirement Isolation
Requirements with applicability thresholds starting above level 52 (including Cast on Dodge with interval [58, 100]) SHALL NOT block readiness for the level-52 transition. Advancing to the eligibility level of a future requirement SHALL NOT reopen or invalidate a previously completed level-52 transition.

#### Scenario: Cast on Dodge does not block level-52 transition
- **WHEN** evaluating readiness for the level-52 transition where Cast on Dodge is in progression state `FUTURE`
- **THEN** Cast on Dodge is excluded from the level-52 blocking requirements and does not prevent `READY`

#### Scenario: Level 58 progression does not reopen completed transition
- **WHEN** character reaches level 58 after completing the level-52 transition
- **THEN** Cast on Dodge becomes active in build progression but level-52 transition remains `COMPLETE`

### Requirement: Completion Evidence and Late Installation Recovery
Moving from `READY` to `TRANSITIONING` SHALL require an explicit deterministic transition trigger event. Transitioning to `COMPLETE` SHALL require verified evidence satisfying explicitly modeled rules with role `COMPLETION_EVIDENCE` whose sources are currently `USABLE`. Completion SHALL represent the historical transition rather than requiring exact equality with the entire level-52 snapshot, enabling late-installed or evolved characters (such as level 60) to be recognized as `COMPLETE` if minimal explicit completion evidence markers remain. The system SHALL NOT infer skill weapon-set assignments from `.build` files. If available evidence is insufficient to prove that the transition historically occurred, the state machine SHALL evaluate to `VERIFYING` rather than false `BLOCKED` or false `COMPLETE`.

#### Scenario: Explicit trigger moves READY to TRANSITIONING
- **WHEN** transition state is `READY` and an explicit transition-start event is received
- **THEN** transition state moves to `TRANSITIONING`

#### Scenario: Late install with exact post-swap evidence recognized as COMPLETE
- **WHEN** character is loaded at level 60 and verified observations satisfy all `USABLE` completion evidence rules
- **THEN** transition state resolves directly to `COMPLETE` and `missed_transition` remains false

#### Scenario: Late install with evolved build retaining transition markers
- **WHEN** character is loaded at level 60 with an evolved build differing from the lvl52 snapshot, but verified observations satisfy all `USABLE` completion evidence rules
- **THEN** transition state resolves directly to `COMPLETE` without requiring exact equality to the lvl52 snapshot

#### Scenario: Late install with insufficient evidence evaluates to VERIFYING
- **WHEN** character is loaded at level 60 and observations are insufficient or unobserved to satisfy completion evidence rules
- **THEN** transition state resolves to `VERIFYING` with `transition_pending` true, without asserting false `BLOCKED` or false `COMPLETE`

### Requirement: Crash-Safe Persistence and Schema 3.0 Migration
The transition state, requirement readiness evaluations, and transition metadata SHALL be persisted in `CharacterState` using the existing crash-safe single-writer state store under schema version `3.0`. The persistence contract SHALL store transition state as `transition: Level52TransitionRecord | None = None`. Migration from schema version `2.0` to `3.0` SHALL add the transition field in an uninitialized state (`transition = None`) without inferring historical transition states (`NOT_RELEVANT`, `PREPARING`, `BLOCKED`, `READY`, `COMPLETE`) during data migration. The first M3 evaluation after migration SHALL deterministically initialize the transition state from current character level, available M2 build delta results, usable rules, and trustworthy evidence.

#### Scenario: Migration from schema 2.0 to 3.0 leaves transition uninitialized
- **WHEN** a character state with schema version `2.0` is migrated to `3.0`
- **THEN** `schema_version` is updated to `3.0` and `transition` is initialized to `None` without inferring domain transition states

#### Scenario: First evaluation after migration derives deterministic state
- **WHEN** a character state with `transition = None` is first evaluated post-migration
- **THEN** the evaluator deterministically initializes transition state based on character level, M2 results, and evidence (e.g., level < 52 with no usable prep rule initializes to `NOT_RELEVANT`; level >= 52 with verified completion evidence initializes to `COMPLETE`)

#### Scenario: Transition state persists across process restart
- **WHEN** transition state is saved as `READY` and the character store is reloaded in a fresh process
- **THEN** the loaded character state preserves `READY` and its associated requirement evaluations