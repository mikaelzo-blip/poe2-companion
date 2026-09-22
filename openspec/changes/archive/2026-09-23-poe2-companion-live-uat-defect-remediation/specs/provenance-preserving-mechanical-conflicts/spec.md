# Spec Delta: Provenance-Preserving Mechanical Conflicts

## Purpose

Provides strictly provenance-preserving mechanical conflict evaluation for character equipment by ensuring unobserved, unprovenanced, or insufficiently corroborated attributes remain UNKNOWN and never default to numeric zero.

## ADDED Requirements

### Requirement: Factual Attribute Deficit Evaluation
The system SHALL emit a factual unmet attribute requirement conflict if and only if both the required attribute value and the character's corresponding attribute value are observed with explicit VERIFIED provenance metadata (such as `ProvenancedField` or `OperandEvidence`) and the verified character attribute is strictly less than the verified item requirement. Plain numeric values without provenance metadata SHALL NOT be treated as verified evidence.

#### Scenario: Verified character attribute meets or exceeds requirement
- **WHEN** the character has an attribute wrapped in explicit provenance metadata with state `VERIFIED` and value 70, and an equipped item requires 52 Strength
- **THEN** no unmet Strength requirement conflict SHALL be emitted

#### Scenario: Verified character attribute falls below requirement
- **WHEN** the character has an attribute wrapped in explicit provenance metadata with state `VERIFIED` and value 30, and an equipped item requires 52 Strength
- **THEN** a factual unmet Strength conflict SHALL be emitted indicating the exact verified values and deficit

### Requirement: Preservation of Unknown and Unprovenanced Attribute States
The system SHALL NOT coerce unobserved, missing, stale, plain numeric, or UNKNOWN character attributes to numeric zero or any other synthetic default. When a character attribute is missing, unprovenanced (raw int/float), or holds a verification state other than VERIFIED, the evaluation result SHALL be treated as insufficient evidence and SHALL NOT emit a factual unmet requirement conflict.

#### Scenario: Unobserved attribute prevents false deficit conflict
- **WHEN** an equipped item requires 52 Strength and the character's Strength attribute is unobserved or has verification state UNKNOWN
- **THEN** no factual unmet Strength requirement conflict SHALL be emitted and the comparison SHALL evaluate to insufficient evidence

#### Scenario: Plain unprovenanced numeric attribute rejected as factual evidence
- **WHEN** an equipped item requires 52 Strength and the character attributes mapping contains a raw integer value without provenance metadata
- **THEN** the system SHALL treat the attribute as unprovenanced / insufficient evidence and SHALL NOT emit a factual unmet requirement conflict

#### Scenario: Stale or uncorroborated attribute suppresses factual conflict
- **WHEN** an equipped item requires 50 Dexterity and the character's Dexterity attribute is marked STALE
- **THEN** the system SHALL NOT emit a factual unmet Dexterity conflict asserting the character has zero or deficit attributes

### Requirement: CLI Gear Status Provenance Awareness
The gear status CLI command SHALL retrieve the active character's provenanced attributes from the character state store when evaluating gear conflicts, preserving unobserved attribute states without passing an empty attribute mapping that triggers default-zero evaluation.

#### Scenario: Gear status command with unobserved character attributes
- **WHEN** a user executes gear status for a character whose attributes have not been verified
- **THEN** the output SHALL report active conflicts without false unmet attribute warnings for the unobserved attributes
