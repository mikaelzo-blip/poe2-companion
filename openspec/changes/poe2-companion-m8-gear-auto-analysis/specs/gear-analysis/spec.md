# Spec Delta

## Purpose

Provides a passive gear auto-analysis engine that parses stable item tooltips, hashes items deterministically, tracks gear freshness via TTL, compares equipped gear against target build requirements, offers investment advice, and identifies observable mechanical conflicts.

## ADDED Requirements

### Requirement: Stable Tooltip Detection and Parsing
The system SHALL parse item tooltip text when two consecutive captures yield identical text features, extracting rarity, name, base type, level/attribute requirements, implicit/explicit mods, and socket/rune details.

#### Scenario: Corroborated stable item tooltip
- **WHEN** two consecutive captures of an item tooltip match identically
- **THEN** the parser returns a structured `ItemTooltip` with extracted properties and verification state `VERIFIED`

#### Scenario: Unstable tooltip rejected
- **WHEN** two consecutive captures of a tooltip exhibit discrepant or changing content
- **THEN** the parser marks the evaluation as `CONFLICTING` or unstable and requests re-capture

### Requirement: Deterministic Item Hashing
The system SHALL compute a deterministic hash string from normalized item attributes to establish persistent identity across session audits.

#### Scenario: Identical item yields identical hash
- **WHEN** the same item attributes are hashed across separate runs
- **THEN** identical SHA-256 hash strings are produced

#### Scenario: Differing item attributes yield distinct hashes
- **WHEN** items with differing mods, base types, or rolls are hashed
- **THEN** distinct hash strings are produced

### Requirement: Current-vs-Target Gear Comparison and Staleness
The system SHALL compare equipped items against build target requirements and track staleness via a configurable time-to-live (TTL).

#### Scenario: Equipped gear meets target stage requirements
- **WHEN** fresh equipped gear contains all mandatory mods and attributes for the target progression stage
- **THEN** the comparison returns satisfied readiness for that slot

#### Scenario: Stale gear audit produces unknown evaluation
- **WHEN** a gear audit exceeds the configured TTL threshold without re-verification
- **THEN** slot evaluation evaluates to `STALE` and flags the slot for re-audit

### Requirement: Investment and Durability Advice
The system SHALL generate actionable investment advice evaluating whether an equipped item provides sufficient durability for subsequent progression stages.

#### Scenario: Item durability flagged for upcoming stage transition
- **WHEN** an equipped item lacks adequate defense or resists for an approaching progression milestone
- **THEN** the advisor emits an investment warning advising replacement before the milestone

#### Scenario: Candidate upgrade outperforms equipped item
- **WHEN** an unequipped candidate tooltip is compared against the currently equipped slot item
- **THEN** the advisor computes the relative delta and recommends whether to equip or retain

### Requirement: Observable Mechanic Conflict Detection
The system SHALL detect observable mechanic conflicts between equipped items, character stats, and target build rules without external game mutation.

#### Scenario: Attribute threshold deficit identified
- **WHEN** an item's strength, dexterity, or intelligence requirement exceeds the character's observed attributes
- **THEN** a mechanic conflict warning is emitted

#### Scenario: Conflicting weapon archetype detected
- **WHEN** an equipped weapon does not match the target build's weapon requirement
- **THEN** an archetype mismatch conflict warning is generated

### Requirement: Guided Slot-by-Slot Gear Audit
The system SHALL orchestrate an interactive slot-by-slot gear audit that prompts the player through equipment slots sequentially without automating mouse inputs.

#### Scenario: Complete gear audit walkthrough
- **WHEN** the player performs a full audit across all equipment slots
- **THEN** the audit state records verified items for each slot and emits an observation event

#### Scenario: Partial audit preserves verified slots and isolates unverified slots
- **WHEN** only a subset of equipment slots is audited
- **THEN** verified slots are updated and unaudited slots remain marked unverified without false assumptions
