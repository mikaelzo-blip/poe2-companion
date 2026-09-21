# Spec Delta

## Purpose

Defines deterministic resolution of build target snapshots, high-end target variants (`NONE`, `LVL85`, `ENDGAME`, `MAGEBLOOD`, `DOT_CAP`), explicit resolver input contracts (`BuildBrainInput`), structured unresolved variant results when no explicit selection is established, target source availability tracking, and structured representation of source conflicts without guessing.

## ADDED Requirements

### Requirement: High-End Target Variant Resolution Without Implicit Defaults
The system SHALL resolve target build variants among explicit enum values `NONE`, `LVL85`, `ENDGAME`, `MAGEBLOOD`, and `DOT_CAP` using structured resolution (`TargetVariantResolution`) based on explicit input:
1. The resolver SHALL define an explicit input contract (`BuildBrainInput`) accepting `character_state`, `observation_coverage: PlayerObservationCoverage`, and `selected_target_variant: TargetVariant | None = None`. M2 SHALL NOT persist or interactively prompt for variant selection; persistence and UX remain strictly external to M2.
2. When the resolved progression phase is not `HIGH_END`, the target variant SHALL evaluate to `NONE` with status `NOT_APPLICABLE`.
3. High-end variants SHALL NOT be modeled as hierarchical or superset relationships; the system SHALL treat `LVL85`, `ENDGAME`, `MAGEBLOOD`, and `DOT_CAP` as independent, non-monotonic configurations where each variant may independently add or remove passives and gear requirements.
4. In `HIGH_END` phase, when `selected_target_variant` is `None` (no explicit target variant selection is provided), the resolver SHALL NOT assume an implicit default such as `LVL85`. Instead, the resolver SHALL return an explicit structured unresolved result:
   - `variant`: `null`
   - `status`: `UNRESOLVED`
   - `reason`: `NO_EXPLICIT_HIGH_END_VARIANT`
5. Valid selectable high-end variants SHALL be strictly limited to `LVL85`, `ENDGAME`, `MAGEBLOOD`, and `DOT_CAP`.
6. Only an explicit input/persisted selection or another future approved deterministic source MAY establish the target variant.
7. The system SHALL NOT infer or silently switch variants based solely on observed player equipment, inventory, or item possession (e.g. possessing a Mageblood belt does not silently resolve or switch the variant to `MAGEBLOOD`).

#### Scenario: Non-high-end phase yields variant NONE
- **WHEN** progression phase is resolved as `LEVELING_33_51` or `POST_52_53_68`
- **THEN** target variant resolution returns variant `NONE` and status `NOT_APPLICABLE`

#### Scenario: HIGH_END with selected_target_variant as None returns UNRESOLVED
- **WHEN** character is in `HIGH_END` progression phase (e.g. level 85) and `selected_target_variant` is `None`
- **THEN** target variant resolution returns `variant: null`, `status: UNRESOLVED`, and `reason: NO_EXPLICIT_HIGH_END_VARIANT`, and does not default to `LVL85`

#### Scenario: Explicit LVL85 variant resolved
- **WHEN** character is in `HIGH_END` phase and `selected_target_variant` is `LVL85`
- **THEN** target variant resolves to `LVL85` with status `RESOLVED` and selects the `lvl 85` snapshot

#### Scenario: Explicit ENDGAME variant resolved
- **WHEN** character is in `HIGH_END` phase and `selected_target_variant` is `ENDGAME`
- **THEN** target variant resolves to `ENDGAME` with status `RESOLVED` and selects the `Endgame` snapshot

#### Scenario: Explicit MAGEBLOOD variant resolved
- **WHEN** character is in `HIGH_END` phase and `selected_target_variant` is `MAGEBLOOD`
- **THEN** target variant resolves to `MAGEBLOOD` with status `RESOLVED` and selects the `Mageblood` snapshot

#### Scenario: Explicit DOT_CAP variant resolved
- **WHEN** character is in `HIGH_END` phase and `selected_target_variant` is `DOT_CAP`
- **THEN** target variant resolves to `DOT_CAP` with status `RESOLVED` and selects the `DoT Cap` snapshot

#### Scenario: Non-monotonic variant transition adds and removes requirements
- **WHEN** switching target variant from `MAGEBLOOD` to `DOT_CAP`
- **THEN** requirements specific to `MAGEBLOOD` are removed and requirements specific to `DOT_CAP` are added, preserving distinct independent configurations without assuming superset relationships

#### Scenario: Item possession does not silently mutate target variant
- **WHEN** a character has a Mageblood belt observed in inventory but `selected_target_variant` is `LVL85` or `ENDGAME`
- **THEN** target variant remains `LVL85` or `ENDGAME` until an explicit variant selection change is provided

### Requirement: Source Conflict Handling, Precedence, and Target Source Availability
The system SHALL resolve target build requirements according to Blueprint v2 precedence (1. verified written Fubgun rule, 2. active `.build`, 3. adjacent `.build`, 4. PoB2 high-end reference, 5. labeled inference) while enforcing source availability tracking:
1. The resolver SHALL track and distinguish source availability states:
   - `USABLE`: Source exists, is frozen, and registered in the current source registry.
   - `PENDING_VERIFICATION`: Source exists in registry but awaits verification.
   - `UNAVAILABLE`: Source is absent from registry.
2. The system SHALL NOT pretend an upstream source is available or fabricate facts from unintegrated sources. Direct PoB2 consumption is NOT an active input for M2; its precedence slot (slot 4) SHALL remain strictly reserved for future verified source integration, and M2 SHALL NOT add a PoB parser or invent PoB-derived target facts.
3. If two or more authoritative inputs of equal precedence conflict materially on the same target element and precedence cannot deterministically break the tie, the system SHALL output a structured `CONFLICTING_EVIDENCE` record detailing competing sources, hashes, and conflicting values rather than silently selecting an arbitrary source.

#### Scenario: Precedence resolves adjacent vs active snapshot conflict
- **WHEN** an adjacent snapshot has differing values from the active stage snapshot
- **THEN** the active snapshot's values take precedence deterministically

#### Scenario: Target source availability distinguishes usable vs unavailable sources
- **WHEN** resolving target requirements where the pinned `.build` file is registered and frozen
- **THEN** the source availability evaluates to `USABLE`, whereas unintegrated external references evaluate to `UNAVAILABLE`

#### Scenario: PoB2 precedence slot reserved without parser fabrication
- **WHEN** resolving target sources in M2
- **THEN** the system consumes verified `.build` inputs without executing a PoB parser and leaves the PoB2 precedence slot reserved for future integration

#### Scenario: Unresolvable source disagreement produces CONFLICTING_EVIDENCE
- **WHEN** two target sources of equal precedence assert contradictory requirements for the same target entry
- **THEN** the resolver flags the target requirement with `CONFLICTING_EVIDENCE` and includes the provenance of both conflicting inputs

#### Scenario: Conflict record retains source provenance
- **WHEN** a `CONFLICTING_EVIDENCE` status is generated
- **THEN** the structured output records each competing source identifier, file hash, and conflicting field values for upstream audit
