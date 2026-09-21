# Objective Engine Specification

## Purpose

Provides a deterministic, categorical objective generation and ranking engine that translates M2 build deltas, M3 transition states, and guide rules into prioritized, non-hallucinatory player guidance without numerical scoring or artificial confidence percentages.

## Requirements

### Requirement: Eight-Tier Categorical Priority Hierarchy
The objective engine SHALL classify all generated objective candidates into exactly one of eight categorical priority ranks in strict precedence order:
1. `CRITICAL_MECHANIC_BREAK`: Broken build synergies, contradictory weapon assignments, or mechanical dysfunctions that prevent the build from functioning.
2. `HARD_BLOCKER`: Progression gates where verified evidence confirms an unsatisfied prerequisite (such as an unsatisfied usable blocking requirement for the level-52 transition).
3. `SURVIVAL_RISK`: Critical defensive deficiencies. The engine SHALL only generate survival risks when backed by an authoritative, evaluable `USABLE` rule; the system SHALL NOT fabricate survival risks in the absence of an authoritative rule.
4. `TRANSITION_REQUIREMENT`: Active requirements or preparation needs for an impending or active progression transition.
5. `CURRENT_PROGRESSION`: Available, level-eligible progression steps including unallocated passive nodes, missing required skills, or primary gear upgrades for the current progression phase.
6. `STRONG_UPGRADE`: High-impact secondary gear, socket links, or passive optimizations that materially improve build power.
7. `OPTIMIZATION`: Non-critical refinements, secondary gem quality, or minor stat tuning.
8. `FUTURE_PREPARATION`: Action items preparing for upcoming levels or milestones that are not yet eligible for current execution.

The engine SHALL NOT calculate or output continuous numerical priority scores (such as decimal priority percentages) and SHALL NOT calculate artificial confidence percentages.

#### Scenario: Categorical priority ordering strictly maintained
- **WHEN** multiple objective candidates across different categories are generated
- **THEN** candidates are strictly ordered by categorical rank: `CRITICAL_MECHANIC_BREAK` preceding `HARD_BLOCKER`, preceding `SURVIVAL_RISK`, down to `FUTURE_PREPARATION`

#### Scenario: No numerical scoring or fake confidence
- **WHEN** an objective candidate is emitted
- **THEN** the candidate contains a categorical `priority` enum and qualitative evidence status, without decimal priority numbers or percentage confidence metrics

#### Scenario: No fabricated survival risk without authoritative rule
- **WHEN** player character has defensive deficits but no authoritative `USABLE` rule exists defining a survival threshold
- **THEN** the engine does not generate a `SURVIVAL_RISK` objective

### Requirement: Deterministic Candidate Generation Consuming M2 and M3 Outputs
The objective engine SHALL deterministically synthesize objective candidates directly from M2 `BuildDeltaResult` and M3 `Level52TransitionResult` / `CharacterState`.
- When M3 transition state evaluates to `BLOCKED`, the engine SHALL emit a `HARD_BLOCKER` objective identifying the specific unsatisfied blocking requirements.
- When M3 transition state evaluates to `VERIFYING`, the engine SHALL emit an investigation/verification objective requiring character state observation, and SHALL NOT emit a `HARD_BLOCKER` or corrective advice.
- When M3 transition state evaluates to `COMPLETE`, the engine SHALL NOT emit any historical transition objectives.
- When M2 build delta contains `MISSING` passives or skills for the active progression phase, the engine SHALL emit `CURRENT_PROGRESSION` objectives.
- Requirements evaluated as `FUTURE` (such as Cast on Dodge [58, 100] at level 52) SHALL be classified as `FUTURE_PREPARATION` and SHALL NOT evaluate as a current blocker.

#### Scenario: M3 BLOCKED generates HARD_BLOCKER objective
- **WHEN** character is at level 52 and M3 transition state evaluates to `BLOCKED` with unsatisfied weapon swap requirements
- **THEN** the engine emits a `HARD_BLOCKER` objective detailing the unsatisfied weapon swap blocker

#### Scenario: M3 VERIFYING generates verification objective
- **WHEN** character is at level 52 and transition state evaluates to `VERIFYING` due to unobserved equipment
- **THEN** the engine emits a verification objective and does not generate a `HARD_BLOCKER`

#### Scenario: M3 COMPLETE suppresses transition objectives
- **WHEN** character transition state evaluates to `COMPLETE` at level 58
- **THEN** the engine generates zero transition objectives for the completed level-52 swap

#### Scenario: Future requirement isolated as FUTURE_PREPARATION
- **WHEN** character is at level 52 and target build includes Cast on Dodge with interval [58, 100]
- **THEN** Cast on Dodge is emitted as `FUTURE_PREPARATION` and does not block current progression

### Requirement: Uncertainty Preservation and Non-Corrective Invariants
The objective engine SHALL strictly preserve uncertainty states (`UNKNOWN`, `STALE`, `CONFLICTING_EVIDENCE`). The engine SHALL NOT convert uncertainty into corrective player instructions or assumed failure.
- When an entity's observation coverage is `PARTIAL` or state is `UNKNOWN`, the engine SHALL NOT generate a `MISSING` corrective objective.
- When evidence is `STALE`, the engine SHALL generate a data freshness refresh request rather than asserting corrective item changes.
- When evidence is `CONFLICTING_EVIDENCE`, the engine SHALL surface a conflict resolution audit need rather than picking an arbitrary resolution.
- When high-end progression phase is reached without an explicit target variant, the engine SHALL emit a target variant selection objective and SHALL NOT silently assume `LVL85`.

#### Scenario: Unknown passive state does not produce corrective advice
- **WHEN** passive tree observation coverage is `PARTIAL` resulting in `UNKNOWN` delta status for an unobserved node
- **THEN** the engine emits an observation audit request and does not instruct the player to allocate the node

#### Scenario: Stale observation produces data refresh request
- **WHEN** character equipment observation is flagged as stale
- **THEN** the engine emits an audit request to refresh player equipment and does not advise changing items

#### Scenario: Unselected high-end variant requires explicit selection
- **WHEN** character reaches high-end progression phase and no explicit target variant is selected
- **THEN** the engine emits a variant selection objective and does not implicitly default to `LVL85`

### Requirement: Deterministic Deduplication, Tie-Breaking, and Empty Fallback
The engine SHALL sort and deduplicate objectives deterministically.
1. Tie-breaking among objectives within the same priority category SHALL follow a fixed four-step criterion:
   - Evidence trustworthiness: `VERIFIED > SINGLE_SOURCE > STALE/UNKNOWN`
   - Horizon: `CURRENT > FUTURE`
   - Cost of ignoring: `HIGH_COST_OF_IGNORING > LOW`
   - Recency: `OLDER_UNRESOLVED_CRITICAL > NEW_MINOR`
   - Lexicographical tie-break on stable objective identifier.
2. Identical input states SHALL produce byte-for-byte identical ordered objective lists.
3. If no actionable objectives are generated, the engine SHALL return a structured `NO_ACTIONABLE_OBJECTIVE` result indicating the character is fully aligned with target build goals for current observations.

#### Scenario: Deterministic ordering with tie-breaking
- **WHEN** two candidates share the same category `CURRENT_PROGRESSION`, one backed by `VERIFIED` evidence and one by `SINGLE_SOURCE`
- **THEN** the verified candidate deterministically precedes the single-source candidate

#### Scenario: Identical inputs yield identical objectives
- **WHEN** objective evaluation is executed twice with identical character state and delta inputs
- **THEN** the generated objective list and ordering are completely identical

#### Scenario: No actionable objectives returns structured result
- **WHEN** character state is fully synchronized with target requirements and all rules pass
- **THEN** the engine returns a structured result containing `NO_ACTIONABLE_OBJECTIVE`
