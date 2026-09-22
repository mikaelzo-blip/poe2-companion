# Spec Delta: Intelligence Provenance

## Purpose

Establishes strict provenance governance and quarantine for intelligence rules, defines per-operand provenance and evidence requirements for authoritative mechanical comparisons, decommissions deferred story and economy features from authoritative runtime execution, and prevents unsourced heuristics from generating high-severity gating objectives.

## ADDED Requirements

### Requirement: Provenance Classification of Intelligence Rules
The system SHALL classify every advisory and diagnostic rule into one of four mutually exclusive provenance categories: `SOURCE_BACKED`, `LABELED_INFERENCE`, `DEFERRED_BY_BLUEPRINT`, or `REMOVE`. Only `SOURCE_BACKED` rules SHALL be eligible to produce authoritative recommendations or gating objectives.

#### Scenario: Rule with explicit guide provenance evaluated
- **WHEN** a rule possessing verified provenance from the Fubgun guide or Blueprint is evaluated
- **THEN** it is classified as `SOURCE_BACKED` and may emit standard authoritative advisories

#### Scenario: Labeled inference cannot masquerade as verified fact
- **WHEN** a heuristic rule designated as `LABELED_INFERENCE` is evaluated
- **THEN** its advisory metadata explicitly flags the finding as an inference and SHALL NOT generate blocking or high-severity objectives

### Requirement: Operand Provenance and Evidence Verification for Mechanical Rules
The system SHALL NOT treat mechanical comparison rules as monolithically `SOURCE_BACKED` without verifying every constituent operand. A mechanical comparison (such as `unreserved_mana < main_skill_cost` or `current_attribute < item_requirement`) SHALL be authoritative ONLY when every required operand independently satisfies all five evidence criteria:
1. **Available**: Value is present, non-null, and structurally validated.
2. **From supported structured sources**: Derived strictly from supported authoritative sources (official API, verified passive tree, verified item requirements, or validated gem metadata), and NEVER from inferred or fabricated values.
3. **Sufficiently fresh**: Observation timestamp is within valid time-to-live (`is_stale == False`).
4. **Sufficiently reliable**: Verification state is strictly `VERIFIED`.
5. **Within adequate observation scope**: Measured within the applicable active configuration (matching active weapon swap, currently socketed gems, and active reservations).

If ANY required operand is missing or has verification state `UNKNOWN`, the comparison result SHALL evaluate to `UNKNOWN` and SHALL NOT emit a definitive advisory. If ANY required operand is `STALE`, the comparison result SHALL evaluate to `UNKNOWN`. The system SHALL NOT invent, estimate, or default missing operand values.

#### Scenario: Missing or unknown unreserved mana produces UNKNOWN
- **WHEN** `unreserved_mana` has verification state `UNKNOWN` or is missing
- **THEN** evaluation of `unreserved_mana < main_skill_cost` yields `UNKNOWN` and produces no definitive lockout advisory

#### Scenario: Stale skill cost produces UNKNOWN
- **WHEN** `main_skill_cost` has staleness state `STALE`
- **THEN** evaluation of `unreserved_mana < main_skill_cost` yields `UNKNOWN` and produces no definitive lockout advisory

#### Scenario: All operands verified produces factual mechanical deficit
- **WHEN** `current_strength` is `VERIFIED` and fresh, `required_strength` is `VERIFIED` and fresh, and `current_strength < required_strength`
- **THEN** the comparison evaluates to an authoritative factual mechanical deficit and emits a lockout advisory

#### Scenario: Missing operand values are not invented
- **WHEN** an item requirement or character attribute operand cannot be extracted from structured sources
- **THEN** the system sets the operand state to `UNKNOWN` rather than inventing a fallback default or estimating a value

### Requirement: Mechanical Hard Lockout Isolation and Buffer Removal
The diagnostic engine SHALL restrict mechanical troubleshooting solely to direct observable deficits where verified current resources are strictly less than verified requirements (`unreserved_mana < main_skill_cost`, `current_attribute < item_requirement`). The system SHALL NOT evaluate or emit warnings based on arbitrary safety multiplier buffers or margins, specifically removing the `2x` mana cost heuristic and the `< 5` attribute safety margin.

#### Scenario: True mana lockout detected
- **WHEN** verified unreserved mana is strictly less than the verified primary skill mana cost (`unreserved_mana < main_skill_cost`)
- **THEN** an authoritative diagnostic alert for mana lockout is generated

#### Scenario: Arbitrary 2x mana buffer heuristic suppressed
- **WHEN** verified unreserved mana is sufficient to cast the primary skill but less than two times the cost (`main_skill_cost <= unreserved_mana < 2 * main_skill_cost`)
- **THEN** no critical diagnostic alert is generated

#### Scenario: Arbitrary attribute safety margin suppressed
- **WHEN** verified character attribute meets item requirements but has fewer than 5 points of buffer (`0 <= char_attr - req_attr < 5`)
- **THEN** no attribute deficit warning or lockout alert is generated

### Requirement: Deferral Compliance for Story and Economy Features
The system SHALL NOT execute hardcoded story quest route guidance or advanced economy ROI optimization as authoritative companion intelligence, adhering to Blueprint Section 62 deferred feature specifications.

#### Scenario: Requesting story quest progression advice
- **WHEN** story quest advice is queried via runtime API or CLI
- **THEN** the system indicates that story route planning and quest databases are deferred features per Blueprint Section 62 and does not emit fabricated quest recommendations

#### Scenario: Requesting economy optimization priority
- **WHEN** economy priority advice is queried via runtime API or CLI
- **THEN** the system indicates that advanced economy optimization is a deferred feature per Blueprint Section 62 and does not emit fabricated currency allocation ladders

### Requirement: Objective Engine Severity Gating for Heuristics
The objective engine SHALL NOT emit high-severity objective candidates (`CRITICAL_MECHANIC_BREAK`, `HARD_BLOCKER`, `SURVIVAL_RISK`, `STRONG_UPGRADE`, or `OPTIMIZATION`) unless the underlying condition is backed by an authoritative, evaluable `USABLE` rule with verified provenance and verified operand requirements.

#### Scenario: Survival risk gating enforcement
- **WHEN** survival advisories are evaluated without an authoritative evaluable USABLE rule
- **THEN** the objective engine produces zero `SURVIVAL_RISK` objective candidates
