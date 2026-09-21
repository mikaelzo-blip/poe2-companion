# Spec Delta

## Purpose

Provides a deterministic declarative rule evaluation engine that evaluates gameplay and build rules against player state, respecting source verification trust, declarative observability paths, explicit transition roles, and explicit semantic result states.

## ADDED Requirements

### Requirement: Declarative Rule Schema and Transition Roles
The system SHALL represent guide rules using an explicit declarative schema containing a stable rule ID, provenance metadata, source verification status (`USABLE`, `PENDING_SOURCE_VERIFICATION`, `UNAVAILABLE`), applicability boundaries, requirement definition, declarative observability paths (`API`, `GEAR_AUDIT`, `SKILL_AUDIT`, `PASSIVE_AUDIT`, `VISION`, `MANUAL`), an `evaluable` boolean indicator, and an explicit transition role (`TransitionRuleRole`). The transition role SHALL be modeled explicitly as one of:
- `BLOCKING_REQUIREMENT`: participates in gating `BLOCKED` and `READY`, provided the rule source is `USABLE` and currently applicable;
- `COMPLETION_EVIDENCE`: contributes to proving that the Level-52 transition is `COMPLETE`, provided the source is `USABLE`, without automatically gating `READY` unless separately defined as a blocking requirement;
- `PREPARATION`: establishes `PREPARING` status prior to level 52 only when the source is `USABLE` and applicability matches;
- `ADVISORY`: informational only; never gates `READY`, `BLOCKED`, or `COMPLETE`.

The system SHALL NOT derive `TransitionRuleRole` implicitly from `RequirementType`, observability methods, rule name, or source type. Rules lacking a known observation mechanism SHALL have `evaluable` set to false.

#### Scenario: Rule definition with explicit transition role
- **WHEN** a guide rule is loaded from declarative source
- **THEN** the rule carries its stable ID, source status, applicability criteria, declarative observation capabilities, evaluable status, and an explicit `TransitionRuleRole`

#### Scenario: Inevaluable rule without observation path
- **WHEN** a rule is registered without any supported observation method
- **THEN** `evaluable` is set to false and the evaluation engine skips active assertion without raising an error

#### Scenario: Decoupled transition role and requirement type
- **WHEN** a rule defines a requirement type (such as item or skill requirement)
- **THEN** its participation in the transition state machine is governed strictly by its explicit `transition_role` rather than inferred from the requirement type

### Requirement: Six-State Semantic Rule Evaluation
The evaluation engine SHALL evaluate applicable rules into exactly one of six explicit semantic states: `PASS`, `FAIL`, `UNKNOWN`, `NOT_APPLICABLE`, `STALE`, or `CONFLICTING_EVIDENCE`. The system SHALL NOT convert `UNKNOWN` or `STALE` results into `FAIL`.

#### Scenario: Verified requirement satisfies rule
- **WHEN** fresh, verified player observations confirm that expected conditions are met
- **THEN** the rule evaluation returns `PASS`

#### Scenario: Verified requirement fails rule
- **WHEN** fresh, verified player observations definitively contradict expected conditions
- **THEN** the rule evaluation returns `FAIL`

#### Scenario: Missing or unobserved evidence produces UNKNOWN
- **WHEN** an applicable rule cannot be evaluated due to missing or unobserved player state
- **THEN** the evaluation returns `UNKNOWN` rather than `FAIL`

#### Scenario: Outdated player evidence produces STALE
- **WHEN** player evidence supporting a rule is flagged as stale
- **THEN** the evaluation returns `STALE` rather than `FAIL`

#### Scenario: Contradictory evidence produces CONFLICTING_EVIDENCE
- **WHEN** conflicting source specifications or conflicting observations exist for a rule
- **THEN** the evaluation returns `CONFLICTING_EVIDENCE`

#### Scenario: Character outside rule applicability
- **WHEN** the character does not satisfy the rule's trigger or level applicability boundaries
- **THEN** the rule evaluation returns `NOT_APPLICABLE`

### Requirement: Source Verification Status Gating and Deadlock Prevention
The evaluation engine SHALL enforce source verification trust boundaries. Only `USABLE` rules SHALL serve as authoritative transition gates. Rules marked `PENDING_SOURCE_VERIFICATION`:
- SHALL NOT produce `FAIL` or `PASS`;
- SHALL NOT independently produce `BLOCKED`;
- SHALL NOT independently prove `COMPLETE`;
- SHALL NOT be counted as unsatisfied authoritative blockers;
- SHALL evaluate to `UNKNOWN` with unresolved source provenance.

Unverified rules marked `PENDING_SOURCE_VERIFICATION` or `UNAVAILABLE` SHALL NOT permanently deadlock or prevent a transition from achieving `READY` when all applicable `USABLE` blocking requirements are satisfied. The system SHALL NOT silently upgrade pending or unavailable rules to `USABLE`.

#### Scenario: Pending source verification rule does not block readiness
- **WHEN** a rule marked `PENDING_SOURCE_VERIFICATION` is evaluated against character state
- **THEN** the engine evaluates the rule to `UNKNOWN` with unresolved source provenance, without asserting a definitive failure or blocker

#### Scenario: Pending source verification rule does not deadlock READY
- **WHEN** all applicable `USABLE` blocking requirements evaluate to `PASS`, and an unverified rule is `PENDING_SOURCE_VERIFICATION`
- **THEN** the pending rule is surfaced as an unresolved audit item and is not counted as an unsatisfied blocker, allowing the transition to evaluate to `READY`

#### Scenario: Unavailable rule cannot gate transition
- **WHEN** a rule marked `UNAVAILABLE` is evaluated
- **THEN** the rule does not assert `FAIL`, does not block transition readiness, and cannot prove completion

### Requirement: Tri-State Requirement Readiness Model
The system SHALL evaluate transition requirements using a tri-state readiness model (`SATISFIED`, `UNSATISFIED`, `UNKNOWN`). A requirement SHALL evaluate to `SATISFIED` only when backed by verified positive evidence from a `USABLE` rule, `UNSATISFIED` only when backed by verified negative evidence from a `USABLE` rule, and `UNKNOWN` when evidence is missing, partial, stale, conflicting, or when rule source is unverified. Only `USABLE` rules with role `BLOCKING_REQUIREMENT` SHALL gate transition readiness or blocking.

#### Scenario: Requirement verified satisfied
- **WHEN** verified evidence demonstrates the requirement condition is fulfilled under a `USABLE` rule
- **THEN** requirement readiness evaluates to `SATISFIED`

#### Scenario: Requirement verified unsatisfied
- **WHEN** verified evidence demonstrates the requirement condition is violated under a `USABLE` rule
- **THEN** requirement readiness evaluates to `UNSATISFIED`

#### Scenario: Incomplete or unverified evidence evaluates to UNKNOWN
- **WHEN** requirement evidence is unobserved, partial, stale, conflicting, or from a `PENDING_SOURCE_VERIFICATION` rule
- **THEN** requirement readiness evaluates to `UNKNOWN` and is treated as neither satisfied nor an active blocker