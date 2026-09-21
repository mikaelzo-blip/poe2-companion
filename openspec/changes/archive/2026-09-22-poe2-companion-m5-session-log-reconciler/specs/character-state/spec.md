# Spec Delta

## ADDED Requirements

### Requirement: Live Session Tracking Fields
The `CharacterState` domain model SHALL support optional provenanced live tracking fields including `current_zone` (`ProvenancedField[str]`), `death_count` (`ProvenancedField[int]`), `session_active` (`bool`), and `last_observed_at` (`datetime`), allowing the state store to represent real-time gameplay context alongside offline build data.

#### Scenario: Character state holds live session facts
- **WHEN** a character state is initialized or reconciled from live game events
- **THEN** `current_zone`, `death_count`, and `session_active` fields SHALL serialize to and deserialize from state JSON without schema validation errors
