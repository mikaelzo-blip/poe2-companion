# Spec Delta

## Purpose

Defines deterministic delta comparison between observed player character state and target build requirements across passives (using compound logical identity, hardened canonicalization, and duplicate conflict detection), skills (enforcing semantic skill-group identity independent of group index reordering), and conservative equipment, governed by a shared centralized policy helper distinguishing evidence quality from scoped observation coverage.

## ADDED Requirements

### Requirement: Passive Delta Computation with Compound Logical Key and Scoped Coverage
The system SHALL compute passive skill deltas by comparing observed player passives against target build passives using the compound key `(passive_id, weapon_set_context)`. The delta evaluation SHALL observe the following rules:
1. Passive identity SHALL be evaluated across all four semantic contexts: `DEFAULT_OR_SHARED`, `SPECIALISATION_1`, `SPECIALISATION_2`, and `UNKNOWN_RESERVED`. Changing the weapon-set context of a passive node SHALL produce a distinct compound key and delta result.
2. Raw duplicate passive entries in target build snapshots SHALL be canonicalized into a single logical allocation requirement per compound key:
   - For every canonical logical target passive, the system SHALL preserve all raw `source_occurrences` (count and original source row indices) and relevant interval/source provenance.
   - The system SHALL derive exactly one logical allocation requirement (`required_count = 1`).
   - The system SHALL inspect duplicate occurrence metadata for material disagreements. If duplicate occurrences for the same logical key contain materially conflicting target metadata or semantics, the system SHALL produce a structured `CONFLICTING_EVIDENCE` record rather than silently selecting one occurrence.
   - The existence of two or more identical raw rows is NOT itself a conflict and SHALL cleanly canonicalize to one allocation requirement.
3. Target variant transitions (e.g. switching between `MAGEBLOOD` and `DOT_CAP`) SHALL evaluate non-monotonically, adding new target requirements and removing requirements specific to the superseded variant.
4. The delta status for each passive requirement SHALL evaluate to one of four explicit states:
   - `PRESENT`: The compound key is confirmed allocated in player state.
   - `MISSING`: The compound key is required in target, currently `ACTIVE`, confirmed unallocated in a verified, non-stale player state, and observation coverage for the passive tree scope is `COMPLETE`.
   - `EXTRA`: The compound key is allocated in player state but absent from target requirements.
   - `UNKNOWN`: The player's passive allocations are unobserved, incomplete, or stale beyond tolerance.
     - If passive tree observation coverage is `PARTIAL`, delta status SHALL evaluate to `UNKNOWN` with reason `PARTIAL_PLAYER_OBSERVATION` and SHALL NOT evaluate to `MISSING`.
     - If observation coverage cannot be established, delta status SHALL evaluate to `UNKNOWN` with reason `OBSERVATION_COVERAGE_UNKNOWN`.
     - Stale observations SHALL evaluate to `UNKNOWN` with reason `STALE_PLAYER_STATE` and SHALL NOT evaluate to `MISSING`.

#### Scenario: Matching passive in same weapon-set context evaluates to PRESENT
- **WHEN** player state has allocated passive `strength36` in `DEFAULT_OR_SHARED` and target requires `(strength36, DEFAULT_OR_SHARED)`
- **THEN** the passive delta status evaluates to `PRESENT`

#### Scenario: Missing target passive evaluates to MISSING when player observation is fresh, verified, and complete
- **WHEN** target requires `(fire62, SPECIALISATION_1)`, player level is eligible, passive observation is fresh, verified, and has `COMPLETE` coverage, and player state lacks this passive in that context
- **THEN** the passive delta status evaluates to `MISSING`

#### Scenario: Fresh VERIFIED but PARTIAL passive observation evaluates to UNKNOWN
- **WHEN** player passive observation is fresh and marked `VERIFIED` but passive observation coverage is `PARTIAL` (covering only a subset of the tree)
- **THEN** an unobserved target passive evaluates to `UNKNOWN` with reason `PARTIAL_PLAYER_OBSERVATION` and SHALL NOT evaluate to `MISSING`

#### Scenario: Extra player passive not in target evaluates to EXTRA
- **WHEN** player has allocated a passive node that does not exist in the target build's requirements
- **THEN** the passive delta status evaluates to `EXTRA`

#### Scenario: Distinct weapon-set contexts prevent false matching
- **WHEN** player has allocated `dexterity13` under `SPECIALISATION_1` but target requires `dexterity13` under `SPECIALISATION_2`
- **THEN** the delta reports `(dexterity13, SPECIALISATION_1)` as `EXTRA` and `(dexterity13, SPECIALISATION_2)` as `MISSING` (if verified and complete) rather than collapsing them

#### Scenario: Identical raw duplicate rows canonicalize cleanly without conflict
- **WHEN** target source snapshot contains identical raw duplicate rows for `dexterity30_` in `DEFAULT_OR_SHARED` (indices 9 and 21)
- **THEN** the target passive requirement specifies exactly 1 allocation requirement, records `source_occurrences = 2`, and produces zero conflict records

#### Scenario: Duplicate occurrences with conflicting metadata produce conflict record
- **WHEN** duplicate occurrences for the same logical key contain materially conflicting level intervals or metadata
- **THEN** the system generates a structured `CONFLICTING_EVIDENCE` record detailing the conflicting occurrences and does not silently choose one

#### Scenario: Target variant change removes and adds passive requirements
- **WHEN** target variant changes from `MAGEBLOOD` to `DOT_CAP`
- **THEN** requirements specific to `MAGEBLOOD` are removed and dual-specialization passives for `DOT_CAP` are added

#### Scenario: Stale player passives evaluate to UNKNOWN with stale reason
- **WHEN** player passive observation is marked stale
- **THEN** unconfirmed target passives evaluate to `UNKNOWN` with reason `STALE_PLAYER_STATE` and SHALL NOT evaluate to `MISSING`

### Requirement: Semantic Skill-Group Identity and Delta Computation
The system SHALL compute skill gem and support gem deltas using a structured target skill-group representation whose logical identity derives from stable semantic structure rather than source group index:
1. Target skill-group logical identity SHALL derive from:
   - Primary active skill or meta-gem identity
   - Parent/meta context (distinguishing standalone active skills from gems socketed inside meta-gems)
   - Active child context where applicable
   The raw `source group_index` SHALL be retained strictly for provenance and audit, and SHALL NOT serve as primary semantic identity across snapshots.
2. If source group indices are reordered across snapshots while semantic skill groups remain identical, the system SHALL derive the exact same logical skill-group interpretation and delta result.
3. The system SHALL explicitly distinguish standalone skills from identical gems utilized inside meta-gem setups. In the level 52 snapshot, standalone `Tornado` and `Tornado` socketed inside `Cast on Dodge` SHALL be maintained as distinct skill requirements regardless of group indices.
4. Attached child support gems SHALL belong strictly to their parent target skill group.
5. The system SHALL NOT infer or fabricate skill weapon-set assignments from build snapshots that lack explicit skill weapon-set fields.
6. Target gems that are not yet level-eligible (where character level is below the gem's level interval minimum) SHALL evaluate to `FUTURE` and SHALL NOT evaluate to `MISSING`.
7. Specifically, `Cast on Dodge` (annotated with interval `[58, 100]`) SHALL evaluate to `FUTURE` when character level is 52 and SHALL NOT evaluate to `MISSING`.
8. Skill delta evaluation SHALL enforce scoped observation coverage:
   - If skill audit coverage is `PARTIAL`, unseen target skills SHALL evaluate to `UNKNOWN` with reason `PARTIAL_PLAYER_OBSERVATION`.
   - If player skill observations have never been recorded, target skills SHALL evaluate to `UNKNOWN` with reason `UNOBSERVED_SUBSYSTEM`.
   - `MISSING` SHALL only be emitted when skill audit coverage is `COMPLETE`, evidence is verified and fresh, and the active target skill is confirmed absent.

#### Scenario: Standalone Tornado and Cast-on-Dodge Tornado remain distinct in level 52 fixture
- **WHEN** evaluating target skills from the pinned level 52 snapshot where `SkillGemTornado` appears standalone and attached inside `SkillGemCastOnDodge`
- **THEN** the system preserves both as separate skill group requirements and does not collapse them into a single gem entry

#### Scenario: Source skill group indices reordered while semantic groups remain identical
- **WHEN** comparing two build representations where the semantic skill groups (e.g. standalone Tornado, Cast on Dodge with Tornado, Flameblast, Oil Grenade) have identical gems and parent contexts but different source group indices
- **THEN** the resolver derives identical logical skill-group requirements and identical delta results

#### Scenario: Ineligible target gem evaluates to FUTURE rather than MISSING
- **WHEN** character level is 52 and target build includes `Cast on Dodge` with level interval `[58, 100]`
- **THEN** the skill delta for `Cast on Dodge` evaluates to `FUTURE` and does not evaluate to `MISSING`

#### Scenario: Partial skill audit evaluates unseen target skill to UNKNOWN
- **WHEN** player skill audit is incomplete (coverage is `PARTIAL`) and a target skill group is not observed
- **THEN** the skill delta evaluates to `UNKNOWN` with reason `PARTIAL_PLAYER_OBSERVATION` and does not evaluate to `MISSING`

#### Scenario: Complete skill audit evaluates confirmed absent active skill to MISSING
- **WHEN** player skill audit is verified, fresh, and has `COMPLETE` coverage, target specifies an active skill with interval `[1, 51]`, character level is 20, and player state lacks the skill
- **THEN** the skill delta evaluates to `MISSING`

#### Scenario: Eligible skill present in player state evaluates to PRESENT
- **WHEN** player state has socketed an active skill matching an eligible target skill and its required supports
- **THEN** the skill group delta evaluates to `PRESENT`

#### Scenario: Unobserved skill state evaluates to UNKNOWN rather than MISSING
- **WHEN** player character has no recorded skill audit or observations in state
- **THEN** all target skill deltas evaluate to `UNKNOWN` with reason `UNOBSERVED_SUBSYSTEM`

#### Scenario: Support gem associations evaluated within target skill group
- **WHEN** a target skill requires specific support gems and player has the active skill but lacks one required support
- **THEN** the active skill reports `PRESENT` while the specific support gem reports `MISSING` (when verified and coverage is complete) within that distinct skill group

### Requirement: Conservative Equipment Delta and Centralized Shared Delta Policy
The system SHALL evaluate equipment slots conservatively against target item specifications while strictly enforcing a centralized delta policy helper distinguishing evidence quality from scoped observation coverage across passives, skills, and equipment:
1. Equipment identity SHALL be defined using the existing `CharacterState` equipment structure, preserving:
   - Equipment slot identifier (e.g. `inventory_id` / slot name)
   - Weapon-set context where applicable (`Weapon1`, `Weapon2`)
   - Known structured item observations (`unique_name`, base type)
   - Observation provenance, freshness, and slot-scoped observation coverage
2. Equipment delta comparison SHALL be strictly factual and SHALL NOT perform gear scoring, upgrade scoring, affix optimization, item pricing, economy evaluation, live inventory inspection, or OCR.
3. Across all domain facts (passives, skills, equipment), the system SHALL use one shared delta evaluation policy helper enforcing that `MISSING` can ONLY be assigned when all five conditions are met:
   a. Target requirement is currently level-eligible (`ACTIVE`),
   b. Relevant player observation is fresh (not marked stale),
   c. Evidence quality is sufficient for definitive comparison (verified evidence strength),
   d. Observation coverage for the relevant scope is `COMPLETE`, and
   e. The target entity is definitively absent from observed player state.
4. Observation coverage SHALL be supplied via explicit input model `PlayerObservationCoverage`:
   - `passives`: `ObservationCoverage` (`COMPLETE`, `PARTIAL`, `UNKNOWN`, defaulting to `UNKNOWN`)
   - `skills`: `ObservationCoverage` (`COMPLETE`, `PARTIAL`, `UNKNOWN`, defaulting to `UNKNOWN`)
   - `equipment_slots`: mapping from equipment slot identifier to `ObservationCoverage` (`dict[str, ObservationCoverage]`)
5. If observation coverage is not supplied or cannot be established, it SHALL default conservatively to `UNKNOWN`, ensuring that absence cannot evaluate to `MISSING`.
6. Observation coverage SHALL NOT be inferred from:
   a. Verification state alone (an observation being `VERIFIED` does not imply `COMPLETE` coverage),
   b. Number of observed entities,
   c. Player character level, or
   d. Presence of observations for other equipment slots (coverage for helmet does not imply coverage for boots or weapons).
7. If observation coverage for the relevant scope is `PARTIAL`, the delta status SHALL evaluate to `UNKNOWN` with structured reason `PARTIAL_PLAYER_OBSERVATION`.
8. If observation coverage for the relevant scope is `UNKNOWN` (including an equipment slot omitted from the `equipment_slots` map), the delta status SHALL evaluate to `UNKNOWN` with structured reason `OBSERVATION_COVERAGE_UNKNOWN`.
9. When player observation is stale, the delta status SHALL evaluate to `UNKNOWN` with structured reason `STALE_PLAYER_STATE` and SHALL NOT evaluate to `MISSING`.
10. When player observation is absent, the delta status SHALL evaluate to `UNKNOWN` with structured reason `UNOBSERVED_SUBSYSTEM`.
11. When target requirement is level-ineligible, the delta status SHALL evaluate to `FUTURE` or `EXPIRED`.
12. Equipment observation coverage SHALL be scoped per slot: a complete fresh observation for one explicitly scoped slot (e.g. helmet slot) MAY establish `MISSING` for that slot without requiring every equipment slot globally to be observed. Omitted or unobserved slots SHALL evaluate to `UNKNOWN`.

#### Scenario: VERIFIED passive state with UNKNOWN coverage remains UNKNOWN
- **WHEN** player passive allocations are marked `VERIFIED` but passive `observation_coverage` is `UNKNOWN`
- **THEN** unallocated target passives evaluate to `UNKNOWN` with reason `OBSERVATION_COVERAGE_UNKNOWN` and SHALL NOT evaluate to `MISSING`

#### Scenario: Slot missing from equipment_slots coverage map evaluates to UNKNOWN
- **WHEN** player equipment state contains observations but a target slot is absent from `observation_coverage.equipment_slots`
- **THEN** the equipment delta for that slot evaluates to `UNKNOWN` with reason `OBSERVATION_COVERAGE_UNKNOWN`

#### Scenario: Coverage for helmet does not imply coverage for boots or weapons
- **WHEN** `observation_coverage.equipment_slots` specifies `COMPLETE` for `Helm` but has no entry for `Boots`
- **THEN** `Helm` may evaluate to `MISSING` if absent, while `Boots` evaluates to `UNKNOWN`

#### Scenario: Coverage never inferred from VerificationState.VERIFIED
- **WHEN** all observed equipment slots have `verification_state = VERIFIED` but no explicit `COMPLETE` coverage is declared
- **THEN** the system does not infer complete coverage and unseen target items evaluate to `UNKNOWN`

#### Scenario: Slot-scoped complete equipment observation establishes MISSING for that slot
- **WHEN** player helmet slot observation is verified, fresh, and has `COMPLETE` coverage for the helmet slot, target requires a specific helmet at current level, and observed slot holds a different item
- **THEN** the equipment delta for the helmet slot evaluates to `MISSING` even if other equipment slots (such as boots or rings) are unobserved

#### Scenario: Unobserved equipment slot evaluates to UNKNOWN
- **WHEN** player equipment state has no recorded observation for a slot (e.g. body armour)
- **THEN** the equipment delta for that slot evaluates to `UNKNOWN` with reason `UNOBSERVED_SUBSYSTEM` and does not evaluate to `MISSING`

#### Scenario: Stale player observation evaluates to UNKNOWN with STALE_PLAYER_STATE reason
- **WHEN** player equipment state has an observation for the chest slot that is marked stale
- **THEN** the equipment delta evaluates to `UNKNOWN` with reason `STALE_PLAYER_STATE` and does not evaluate to `MISSING`

#### Scenario: Matching target equipment item evaluates to PRESENT
- **WHEN** player state has an observed item matching target unique name in the designated slot
- **THEN** the equipment delta evaluates to `PRESENT`

#### Scenario: Shared policy helper guarantees zero false MISSING on unobserved state
- **WHEN** an evaluation is executed where player state is completely unobserved (clean initialization)
- **THEN** every passive, skill, and equipment delta evaluates to `UNKNOWN` (with reason `UNOBSERVED_SUBSYSTEM`) or `FUTURE`, with exactly zero items evaluated as `MISSING`
