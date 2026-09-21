# Spec Delta

## Purpose

Routes typed game observations through an in-memory event bus, reconciles character state with field-level provenance and staleness tracking, and records an append-only, privacy-sanitized journey history.

## ADDED Requirements

### Requirement: Observation Event Bus
The system SHALL provide an in-memory, decoupled observation event bus supporting typed event publication and subscription, enabling sensing monitors and state reconcilers to communicate without tight coupling.

#### Scenario: Publish and receive typed event
- **WHEN** an observation source publishes an `ObservationEvent` to the bus
- **THEN** all registered synchronous listeners for that event type SHALL be invoked with the event payload in deterministic subscription order

#### Scenario: Unsubscribe listener
- **WHEN** a subscriber unsubscribes from the event bus
- **THEN** subsequent events of that type SHALL NOT invoke the unsubscribed listener

### Requirement: Provenanced State Reconciliation
The system SHALL reconcile incoming observation events into the active `CharacterState` using `ProvenancedField` metadata, updating character level, current zone, death count, and observation timestamps while preserving provenance integrity.

#### Scenario: Level up observation reconciled
- **WHEN** a valid level-up observation event is processed by the reconciler
- **THEN** the character's `level` field SHALL be updated to the new level with `source="client_log"`, `provenance_state=VERIFIED`, and timestamp matching the event

#### Scenario: Zone transition observation reconciled
- **WHEN** an area entry observation event is processed
- **THEN** the character's `current_zone` field SHALL reflect the new area name with verified provenance

#### Scenario: Death event observation reconciled
- **WHEN** a death observation event matching the active character is processed
- **THEN** the character's `death_count` SHALL be incremented with single-source provenance

### Requirement: Append-Only Journey History Log
The system SHALL record every normalized observation event and major progression milestone to a persistent append-only JSONL log (`runtime/journey_history.jsonl`), strictly omitting unverified raw chat or sensitive data.

#### Scenario: Normalized event appended to history
- **WHEN** an observation event is reconciled
- **THEN** a structured JSON record containing event type, timestamp, character ID, and normalized payload SHALL be appended to the journey history log

#### Scenario: Raw chat invariant in history
- **WHEN** inspect journey history records
- **THEN** no record in the history file SHALL contain raw chat content, whispers, or unparsed log text
