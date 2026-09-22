# Vision Sensor Specification

## Purpose

Provides a read-only vision sensing engine with screen classification, character panel parsing, multi-capture verification, vision budget enforcement, and privacy disclosure.

## Requirements

### Requirement: Screen Type Classification
The vision sensor SHALL classify incoming screenshots or textual screen features into one of five recognized screen categories: `CHARACTER_PANEL`, `ITEM_TOOLTIP`, `SKILL_PANEL`, `PASSIVE_SCREEN_TARGETED`, or `UNKNOWN`.

#### Scenario: Classify character panel screen
- **WHEN** a screenshot exhibiting character attributes, defensive stats, and resistance labels is evaluated
- **THEN** the classifier returns `CHARACTER_PANEL` with high confidence

#### Scenario: Classify unknown or gameplay screen
- **WHEN** a general exploration gameplay screenshot without overlay panels is evaluated
- **THEN** the classifier returns `UNKNOWN`

### Requirement: Character Panel Stat Extraction
The vision sensor SHALL parse visible character panel text to extract numeric values for core defensive metrics including unreserved life, mana, spirit, armour, evasion rating, and elemental/chaos resistances.

#### Scenario: Parse complete character panel
- **WHEN** text representation of a valid character panel is submitted
- **THEN** the parser returns a structured `CharacterPanelStats` instance containing all visible metrics

### Requirement: Multi-Capture Semantic Verification
The vision sensor SHALL determine the semantic verification state of extracted stats: corroborating multiple consistent captures as `VERIFIED`, single captures as `SINGLE_SOURCE`, and discrepant captures as `CONFLICTING`.

#### Scenario: Corroborated dual capture
- **WHEN** two consecutive captures taken within the stability threshold yield identical stat values
- **THEN** the verification state is evaluated as `VERIFIED`

#### Scenario: Single capture verification
- **WHEN** only one capture is available for a panel
- **THEN** the verification state is evaluated as `SINGLE_SOURCE`

### Requirement: Vision Budget and Rate Limiting
The vision sensor SHALL enforce an hourly call ceiling and a minimum elapsed duration between captures to prevent resource exhaustion and visual polling overhead.

#### Scenario: Enforce hourly call limit
- **WHEN** the number of vision capture calls within a rolling 60-minute window exceeds the configured maximum
- **THEN** the vision budget tracker rejects further capture attempts until the window recedes

#### Scenario: Enforce minimum inter-capture interval
- **WHEN** a capture is requested before the minimum interval between captures has elapsed
- **THEN** the vision budget tracker rejects the capture request

### Requirement: Privacy Disclosure and Redaction
The vision sensor SHALL explicitly declare its processing mode (local vs cloud) and SHALL redact non-pertinent regions (such as chat overlays and private identifiers) from visual artifacts.

#### Scenario: Declare cloud transmission mode
- **WHEN** a cloud vision provider is configured
- **THEN** the sensor configuration discloses that cropped image regions are transmitted externally
