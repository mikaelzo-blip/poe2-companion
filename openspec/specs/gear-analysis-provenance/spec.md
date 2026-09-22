# Gear Analysis Provenance Specification

## Purpose

Establishes a strictly factual, target-driven gear evaluation engine that compares candidate items against explicit verified build requirements from M0/M2/M3 without arbitrary numeric weights, opaque durability scores, or invented upgrade thresholds.

## Requirements

### Requirement: Target-Driven Factual Item Comparison
The system SHALL compare candidate equipment items against currently equipped items solely using explicit, verified target requirements supplied by the active progression milestone. The comparison result SHALL evaluate to one of five deterministic semantic states: `SATISFIES_MORE_VERIFIED_REQUIREMENTS`, `SATISFIES_FEWER_VERIFIED_REQUIREMENTS`, `EQUIVALENT_FOR_KNOWN_REQUIREMENTS`, `INCOMPARABLE`, or `UNKNOWN`.

#### Scenario: Candidate satisfies strictly more verified target requirements
- **WHEN** an unequipped candidate item meets all verified target requirements satisfied by the equipped item plus at least one additional verified target requirement
- **THEN** the comparison evaluates to `SATISFIES_MORE_VERIFIED_REQUIREMENTS`

#### Scenario: Trade-off between disjoint target requirements
- **WHEN** a candidate item satisfies a missing target requirement but fails a different verified requirement currently satisfied by the equipped item
- **THEN** the comparison evaluates to `INCOMPARABLE` with explicit detail of trade-offs

#### Scenario: Comparison with insufficient target requirements
- **WHEN** an item is compared in a slot where the target build snapshot provides no explicit requirement or attributes cannot be verified
- **THEN** the comparison evaluates to `UNKNOWN` or `INCOMPARABLE` and SHALL NOT evaluate to an upgrade verdict

### Requirement: Elimination of Arbitrary Numeric Gear Scores
The system SHALL NOT compute or display arbitrary weighted formulas, composite defensive durability scores, or magic score delta replacement thresholds for gear items.

#### Scenario: Gear advice request does not emit numeric composite score
- **WHEN** gear investment or replacement advice is requested for an equipped item
- **THEN** the advice articulates discrete target requirement matches and deficits without calculating or exposing a numeric durability score

### Requirement: Preservation of Observable Item Facts and Freshness
The system SHALL preserve and report all verified item facts, including item identity, item hash, structured affixes, sockets, runes, observed timestamp, and time-to-live staleness state.

#### Scenario: Item audit emits complete observable provenance
- **WHEN** an item evaluation is serialized or presented
- **THEN** the output contains structured modifier lines, source provenance, verification state, and freshness status without loss of underlying attributes

### Requirement: Objective Engine Score Isolation
The objective engine SHALL NOT consume or rank candidate objectives using numeric gear scores or invented score thresholds. Objectives for gear progression SHALL be driven entirely by verified delta requirements.

#### Scenario: Gear progression objective derived from verified requirement delta
- **WHEN** an objective candidate is generated for an equipment slot
- **THEN** its priority and rationale are derived from verified build delta requirements and never from an invented numeric gear score
