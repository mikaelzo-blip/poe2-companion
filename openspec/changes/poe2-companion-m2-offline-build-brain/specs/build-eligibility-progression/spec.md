# Spec Delta

## Purpose

Defines deterministic level eligibility evaluation (`ACTIVE`, `FUTURE`, `EXPIRED`, `UNKNOWN`) for normalized build entries, boundary validation defense against invalid character levels, and progression phase resolution across leveling and endgame stages without invoking transition state machines.

## ADDED Requirements

### Requirement: Deterministic Level Eligibility Evaluation
The system SHALL evaluate a normalized build element's level interval against an observed character level and return a deterministic eligibility status restricted to `ACTIVE`, `FUTURE`, `EXPIRED`, and `UNKNOWN`. The evaluation SHALL adhere to the following rules:
1. An unrestricted interval (`UNRESTRICTED` or omitted) SHALL evaluate to `ACTIVE` across all integer character levels, including when the character level is unknown.
2. An explicit range interval `[min, max]` SHALL evaluate to `FUTURE` when character level is strictly less than `min`, `ACTIVE` when character level is greater than or equal to `min` and less than or equal to `max`, and `EXPIRED` when character level is strictly greater than `max`.
3. If the character level is unknown (`None` or unverified/unknown provenance) and the interval is bounded, the evaluation SHALL evaluate to `UNKNOWN` and SHALL NOT assume a default level.
4. An interval with unresolved single unsigned integer semantics (`UNRESOLVED_SINGLE_UINT`) SHALL evaluate to `UNKNOWN` with an explicit unresolved semantics flag, and the system SHALL NOT fabricate a minimum-level or exact-level interpretation.
5. Inverted or structurally malformed intervals SHALL be rejected by structural validation and SHALL NOT produce an `ACTIVE` status.

#### Scenario: Below lower bound evaluated as FUTURE (min - 1)
- **WHEN** a build element has interval `[15, 32]` and observed character level is `14`
- **THEN** the eligibility status evaluates to `FUTURE`

#### Scenario: Exact lower bound evaluated as ACTIVE (min)
- **WHEN** a build element has interval `[15, 32]` and observed character level is `15`
- **THEN** the eligibility status evaluates to `ACTIVE`

#### Scenario: Inside range evaluated as ACTIVE
- **WHEN** a build element has interval `[15, 32]` and observed character level is `20`
- **THEN** the eligibility status evaluates to `ACTIVE`

#### Scenario: Exact upper bound evaluated as ACTIVE (max)
- **WHEN** a build element has interval `[15, 32]` and observed character level is `32`
- **THEN** the eligibility status evaluates to `ACTIVE`

#### Scenario: Above upper bound evaluated as EXPIRED (max + 1)
- **WHEN** a build element has interval `[15, 32]` and observed character level is `33`
- **THEN** the eligibility status evaluates to `EXPIRED`

#### Scenario: Unknown character level produces UNKNOWN for bounded intervals
- **WHEN** a build element has a bounded interval `[52, 68]` and observed character level is `None` or unknown
- **THEN** the eligibility status evaluates to `UNKNOWN`

#### Scenario: Unrestricted interval produces ACTIVE across all levels
- **WHEN** a build element has an unrestricted interval (no level bounds specified)
- **THEN** the eligibility status evaluates to `ACTIVE` regardless of whether the character level is 1, 52, 100, or unknown

#### Scenario: Unresolved single uint preserves uncertainty as UNKNOWN
- **WHEN** a build element has a single unsigned integer interval (e.g. `52`)
- **THEN** the eligibility status evaluates to `UNKNOWN` with an unresolved semantics indicator, without assuming `[52, 100]` or `[52, 52]`

### Requirement: Boundary Defense Against Invalid Character Levels
The system SHALL validate character levels at domain boundaries and reject impossible character levels by raising an explicit validation error (`InvalidCharacterLevelError`):
1. A character level of `0` is invalid and SHALL be rejected.
2. A negative character level (< 0) is invalid and SHALL be rejected.
3. A character level strictly greater than the supported game maximum of `100` is invalid and SHALL be rejected.
4. The system SHALL NOT silently map invalid levels into progression phases (e.g. level 0 into `LEVELING_1_14` or level 105 into `HIGH_END`) and SHALL NOT build unnecessary error-recovery guessing logic for impossible character levels.

#### Scenario: Level zero raises validation error
- **WHEN** character level is specified as `0`
- **THEN** the system raises `InvalidCharacterLevelError` and does not assign a progression phase

#### Scenario: Negative level raises validation error
- **WHEN** character level is specified as `-5`
- **THEN** the system raises `InvalidCharacterLevelError` and does not assign a progression phase

#### Scenario: Level exceeding maximum raises validation error
- **WHEN** character level is specified as `101`
- **THEN** the system raises `InvalidCharacterLevelError` and does not assign a progression phase

### Requirement: Deterministic Progression Phase Resolution and 69–84 Fallback Specification
The system SHALL deterministically map validated character level and progression metadata to one of six explicit progression phases:
- `LEVELING_1_14` for levels 1 through 14 (mapping to `lvl 1-14` snapshot)
- `LEVELING_15_32` for levels 15 through 32 (mapping to `lvl 15-32` snapshot)
- `LEVELING_33_51` for levels 33 through 51 (mapping to `lvl 33-51` snapshot)
- `POST_52_53_68` for levels 52 through 68 (mapping to `lvl 52 Swap` / `lvl 53-68` snapshot)
- `LEVELING_69_84_FALLBACK` for levels 69 through 84
- `HIGH_END` for levels 85 through 100
If character level is unknown or absent, the resolved phase SHALL evaluate to `UNKNOWN`.

For `LEVELING_69_84_FALLBACK`:
1. The phase SHALL NOT refer vaguely to a generic "post-52 baseline". It SHALL explicitly specify `lvl 53-68` as its deterministic fallback target reference snapshot.
2. This mapping is an explicit companion fallback policy caused by the absence of a dedicated 69–84 snapshot in the upstream Fubgun guide package.
3. The system SHALL record provenance for this decision (`COMPANION_FALLBACK_SOURCE_GAP`) alongside the resolved target snapshot reference.
4. The resolver SHALL NOT implement or evaluate persistent Level-52 transition states (`PREPARING`, `VERIFYING`, `BLOCKED`, `READY`, `TRANSITIONING`, `COMPLETE`, `MISSED_TRANSITION`), which are strictly reserved for Milestone 3.

#### Scenario: Resolving leveling phases at exact boundaries
- **WHEN** observed character level is evaluated at levels `1`, `14`, `15`, `32`, `33`, and `51`
- **THEN** the resolver returns `LEVELING_1_14` for 1 and 14, `LEVELING_15_32` for 15 and 32, and `LEVELING_33_51` for 33 and 51

#### Scenario: Boundary level 68 resolves to POST_52_53_68
- **WHEN** observed character level is `68`
- **THEN** the resolver returns `POST_52_53_68` referencing `lvl 53-68` without fallback status

#### Scenario: Boundary level 69 resolves to LEVELING_69_84_FALLBACK with exact snapshot
- **WHEN** observed character level is `69`
- **THEN** the resolver returns `LEVELING_69_84_FALLBACK`, binds target snapshot to `lvl 53-68`, and records provenance `COMPANION_FALLBACK_SOURCE_GAP`

#### Scenario: Boundary level 84 resolves to LEVELING_69_84_FALLBACK with exact snapshot
- **WHEN** observed character level is `84`
- **THEN** the resolver returns `LEVELING_69_84_FALLBACK`, binds target snapshot to `lvl 53-68`, and records provenance `COMPANION_FALLBACK_SOURCE_GAP`

#### Scenario: Boundary level 85 resolves to HIGH_END
- **WHEN** observed character level is `85`
- **THEN** the resolver returns `HIGH_END` and initiates high-end target variant resolution

#### Scenario: Unknown character level resolves to UNKNOWN phase
- **WHEN** observed character level is `None` or has an `UNKNOWN` verification status
- **THEN** the resolver returns `UNKNOWN` progression phase

#### Scenario: Strict isolation from M3 transition states
- **WHEN** a character level is at or above 52
- **THEN** the resolver produces only the progression phase (`POST_52_53_68`, `LEVELING_69_84_FALLBACK`, or `HIGH_END`) without emitting transition state machine flags such as `PREPARING`, `BLOCKED`, or `MISSED_TRANSITION`
