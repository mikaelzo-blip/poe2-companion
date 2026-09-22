# Spec Delta

## Purpose

Defines the expanded build intelligence system for Path of Exile 2, incorporating survival rules, gear optimization rules, diagnostic troubleshooting rules, story progression quest tracking, and economy upgrade prioritization.

## ADDED Requirements

### Requirement: Survival Rules Evaluation
The system SHALL evaluate player defensive statistics against act and endgame progression thresholds, identifying uncapped elemental resistances, deficient life pools, and hazardous chaos resistance deficits.

#### Scenario: Elemental resistances uncapped in maps
- **WHEN** character level is 65 or higher and fire, cold, or lightning resistance is below 75%
- **THEN** the system generates a high-severity survival alert specifying the missing resistance margin

#### Scenario: Deficient life pool for progression tier
- **WHEN** character level or current act indicates an expected life pool and observed maximum life falls below the safety threshold
- **THEN** the system generates a survival recommendation to prioritize life affixes

### Requirement: Gear Optimization Rules
The system SHALL inspect equipped items and identify uncrafted mod slots, missing sockets for core skills, and low-tier gear bases lagging behind zone level.

#### Scenario: Open affix slot eligible for bench craft
- **WHEN** an equipped rare item possesses fewer than 6 affixes and lacks bench crafted modifiers
- **THEN** the system flags the item as having open craft potential

#### Scenario: Gear base lagging significantly behind character level
- **WHEN** an equipped item base level is more than 20 levels below the character's level
- **THEN** the system advises seeking an upgraded base tier

### Requirement: Diagnostic Troubleshooting Rules
The system SHALL diagnose character execution bottlenecks, including unmet attribute requirements, unreserved mana starvation due to aura reservation, and absent ailment mitigation.

#### Scenario: Unreserved mana insufficient for main skill cost
- **WHEN** reserved spirit and mana leave less than twice the mana cost of the primary offensive skill
- **THEN** the system emits a troubleshooting diagnostic warning of mana starvation

#### Scenario: Attribute threshold blocking gem leveling
- **WHEN** an attribute is within 5 points of a gem's requirement or preventing gem level-up
- **THEN** the system emits an attribute deficit alert with suggested gearing adjustments

### Requirement: Story Progression Quest Guidance
The system SHALL track completion of mandatory permanent reward quests across Acts 1-6 (passive skill books, permanent spirit, and bandit choices) and alert the player to uncompleted rewards.

#### Scenario: Player enters next act with uncompleted spirit quest
- **WHEN** the player advances into an act without having completed permanent spirit quests from earlier acts
- **THEN** the system emits a story guidance warning highlighting the missed permanent reward

### Requirement: Minimal Economy Guidance and Upgrade Prioritization
The system SHALL provide deterministic upgrade prioritization recommendations based on current character bottlenecks and budget tiers.

#### Scenario: Weapon upgrade prioritized when defenses are adequate
- **WHEN** defenses meet progression thresholds and main weapon DPS lags behind target build
- **THEN** the economy advisor recommends allocating currency toward a weapon base or essence upgrade
