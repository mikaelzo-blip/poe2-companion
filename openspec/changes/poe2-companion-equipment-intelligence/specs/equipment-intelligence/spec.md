# Spec Delta: Equipment Intelligence & Gear Brain

## Purpose

Provides an authoritative, deterministic equipment evaluation engine ("Gear Brain") that analyzes character baselines, dual weapon-set loadouts, candidate item contributions, local versus global modifiers, dynamic stat deficiencies, requirement cascades, and stage-aware build rules to produce explainable equipment recommendations without relying on static item scores, unverified assumptions, or game-client automation.

## ADDED Requirements

### Requirement: Hierarchical Decision Reasoning over Static Scoring
The system SHALL evaluate candidate equipment upgrades using a deterministic hierarchical decision pipeline (build breaker check, character requirement check, defensive gap analysis, slot-specific opportunity cost, Life/survivability change, resistance change, attribute requirement change, build-relevant offense change, utility/movement change, opportunity cost synthesis, and final verdict) and SHALL NOT reduce item value to a single scalar score.

#### Scenario: Evaluates candidate item through hierarchical pipeline without scalar score
- **WHEN** a candidate item is evaluated against the current character and equipped loadout
- **THEN** the system executes the hierarchical evaluation pipeline and returns a structured verdict with explicit component trade-offs instead of a single scalar score (e.g. "82/100")

#### Scenario: Hard build breaker halts pipeline and forces rejection
- **WHEN** a candidate item contains a modifier violating a hard build rule for the active progression stage
- **THEN** the system halts standard upgrade scoring, flags the specific violating modifier and rule, and issues a `REJECT` verdict regardless of attractive generic stats

### Requirement: Authoritative Character Stat Baseline, Raw vs Effective Resistances, and UNKNOWN State Handling
The system SHALL model the current character defensive, attribute, and mobility state via an explicit `CharacterStatBaseline` composed of provenanced `CharacterFact` records for Life, Fire Resistance, Cold Resistance, Lightning Resistance, Chaos Resistance, Armour, Evasion, Energy Shield, Strength, Dexterity, Intelligence, Movement Speed, and current maximum elemental/chaos resistances. For each resistance category (Fire, Cold, Lightning, Chaos), the system SHALL explicitly distinguish `raw_uncapped_resistance`, `effective_resistance`, `max_resistance`, and `overcap_buffer`. Each fact SHALL record `value`, `source` (`EXISTING_CHARACTER_STATE`, `GGG_OFFICIAL_API`, `DERIVED_FROM_VERIFIED_COMPONENTS`, `DERIVED_CALCULATION`, `MANUAL_USER_INPUT`, `MANUAL_SNAPSHOT`, `UNKNOWN`), `observed_at`, `verification`, `stale_after`, and `evidence_ref`. If an exact current stat cannot be proven by verified evidence, its value SHALL be set to `UNKNOWN` and SHALL NOT be converted or coerced to zero. Schema defaults SHALL NOT mark omitted baseline facts as verified without explicit evidence. The canonical fact predicate `CharacterFact.is_known` SHALL evaluate to `False` whenever `value` is `None` or `verification` is in `(UNKNOWN, STALE, CONFLICTING)`, ensuring unproven or conflicting facts are never treated as usable baselines.

#### Scenario: Unobserved resistance is recorded as UNKNOWN rather than zero
- **WHEN** official API synchronization or character runtime state does not supply a verified character-sheet value for Lightning Resistance
- **THEN** the baseline records Lightning Resistance with `value: UNKNOWN`, `source: UNKNOWN`, and `verification: UNKNOWN`, and does not initialize or treat the resistance as 0%

#### Scenario: Distinguishes raw uncapped resistance from effective resistance and overcap buffer
- **WHEN** a user records baseline Lightning Resistance with raw uncapped value 115 and maximum resistance 75
- **THEN** the baseline records `raw_uncapped_resistance: 115`, `effective_resistance: 75`, `max_resistance: 75`, and `overcap_buffer: 40`, maintaining the distinction between capped and uncapped state

#### Scenario: Provenanced character facts preserve source and observation evidence
- **WHEN** a user establishes character stats via an explicit manual baseline snapshot
- **THEN** each recorded stat fact retains `source: MANUAL_SNAPSHOT`, timestamp `observed_at`, `verification: SINGLE_SOURCE`, and audit reference `evidence_ref`

#### Scenario: Optional defenses and max resistances recorded without mandatory population
- **WHEN** a user sets baseline stats providing Life, Resistances, and Armour while omitting Evasion and Energy Shield
- **THEN** the baseline stores verified facts for Life, Resistances, and Armour, while Evasion, Energy Shield, and unverified max resistances remain strictly `UNKNOWN` without defaulting to zero or false verified status

### Requirement: Baseline and Loadout Revision Anchoring and Initial Setup Workflow
The system SHALL persist an explicit, auditable relationship between `CharacterStatBaseline` and `EquippedLoadout`, while strictly distinguishing INITIAL LOADOUT CAPTURE from REAL EQUIPMENT MUTATION.
During first-time setup, the user SHALL be permitted to capture all known currently equipped items across shared slots, weapon set 1, and weapon set 2 into a draft loadout (`companion gear loadout set-clipboard --slot <slot>`) without treating each captured item as an in-game gear swap and without incrementing revision.
The system SHALL provide an explicit finalization command (`companion gear loadout finalize`) that establishes `loadout_id` and initial stable `revision = 1`.
The system SHALL require or encourage establishing character baseline (`companion gear baseline set`) only AFTER the current loadout is finalized, anchoring `CharacterStatBaseline.anchored_loadout_revision` directly to revision 1 so that baseline numbers and stored equipment describe the same known equipment state.
Finalization SHALL be permitted with a partial loadout, explicitly recording `known_slots`, `unknown_slots`, and verification state without requiring every slot to be known.
The system SHALL provide an explicit re-snapshot / refresh workflow (`companion gear baseline set` or `companion gear baseline refresh`) that anchors a fresh manual baseline directly to the current loadout revision as `VERIFIED` / `MANUAL`, replacing chains of derived values.

#### Scenario: Capture several existing items before baseline does not simulate gear swaps
- **WHEN** a user executes `companion gear loadout set-clipboard` for multiple equipped slots (e.g. helm, body armour, boots, staff) during initial setup
- **THEN** the items populate the draft loadout without incrementing revision, without triggering mutation reconciliation, and without simulating gear swaps

#### Scenario: Finalized loadout starts a stable revision
- **WHEN** the user executes `companion gear loadout finalize` after capturing draft equipped items
- **THEN** the system finalizes the loadout, assigns `loadout_id`, establishes initial stable `revision: 1`, records known and unknown slots, and enables candidate evaluation

#### Scenario: Baseline anchors to finalized revision
- **WHEN** the user runs `companion gear baseline set` after loadout finalization
- **THEN** the persisted `CharacterStatBaseline` records `anchored_loadout_revision: 1` and is considered fully consistent with loadout revision 1

#### Scenario: Partial loadout retains UNKNOWN slots
- **WHEN** a user finalizes a loadout with only boots and rings captured while helmet, body armour, and weapon slots remain uncaptured
- **THEN** the system finalizes successfully with `revision: 1`, marks the captured slots in `known_slots`, and records the remaining slots as `unknown_slots` with value `UNKNOWN`

#### Scenario: Fresh manual baseline reanchors to current revision
- **WHEN** a user executes `companion gear baseline set` or `companion gear baseline refresh` after several equipment changes advanced loadout to revision 4
- **THEN** the system records a fresh manual baseline with `source: MANUAL_USER_INPUT`, `verification: VERIFIED`, and `anchored_loadout_revision: 4`, replacing prior derived calculation chains

#### Scenario: Persisted baseline and loadout relationship survives application restart
- **WHEN** the companion process restarts and reloads `loadout.json` and `baseline.json`
- **THEN** the system verifies that `baseline.anchored_loadout_revision` matches `loadout.revision` and restores the authoritative baseline state

### Requirement: Post-Setup Loadout Mutation and Safe Baseline Reconciliation Policy
After the initial loadout has been finalized, the system SHALL increment `loadout.revision` ($N \to N+1$) whenever a command executes an actual equipment change (`companion gear loadout promote-candidate` or explicit replacement of an established slot). Following any post-setup loadout mutation, the system SHALL reconcile `CharacterStatBaseline` using the following strict reconciliation policy:
1. **Resistance Rebase Policy (Raw vs Effective)**:
   - The system SHALL NOT perform additive item rebasing directly against a capped effective resistance value.
   - Safe deterministic resistance rebase SHALL be allowed ONLY when enough information exists to reconstruct the raw state: either `raw_uncapped_resistance` is known, OR `effective_resistance` plus a verified `overcap_buffer` is sufficient to reconstruct it.
   - When raw state is proven, the system SHALL compute:
     $$\text{new\_raw} = \text{old\_raw} - \text{displaced\_item\_contribution} + \text{candidate\_contribution}$$
     $$\text{new\_effective} = \min(\text{new\_raw}, \text{verified\_current\_max\_resistance})$$
     and record `source: DERIVED_CALCULATION`, updated timestamps, and anchor to the new loadout revision.
   - If the raw state cannot be proven (e.g. effective resistance is 75% but raw uncapped resistance and overcap buffer are `UNKNOWN`), the system SHALL report the known item resistance delta (e.g. `-30% Lightning Resistance`), but SHALL mark the new absolute effective resistance as `UNKNOWN` / `STALE` and SHALL NOT fabricate an absolute value.
2. **Linear Attributes Rebase**: For linear attributes (Strength, Dexterity, Intelligence), the system SHALL compute `new_baseline = old_verified_baseline - old_item_contrib + new_item_contrib` and mark `source: DERIVED_CALCULATION`.
3. **Complex Non-Linear Defenses Stale**: For complex, non-linear stats subject to passives or global scaling (total Armour, Evasion, Energy Shield), the system SHALL mark the baseline fact as `STALE` / `UNKNOWN` and SHALL NOT fabricate an unsubstantiated new total.
4. **Linear Movement Speed Rebase**: For Movement Speed, if `baseline.movement_speed.is_known` and present, the system SHALL compute `new_baseline = int(baseline.movement_speed.value + net_ms_delta)` and mark `source: DERIVED_CALCULATION` and `verification: VERIFIED`. If present but unproven, the system SHALL mark it `STALE`. If unobserved, it SHALL remain `UNKNOWN`.

#### Scenario: Capped effective resistance is not used as raw additive baseline
- **WHEN** a character has raw lightning resistance 115, max resistance 75, effective resistance 75, and swaps an item replacing +40% with +10%
- **THEN** the system does NOT compute 75 - 40 + 10 = 45; it computes new raw 115 - 40 + 10 = 85 and keeps effective resistance at min(85, 75) = 75

#### Scenario: Known raw overcap correctly absorbs item resistance loss
- **WHEN** a character has raw lightning resistance 115, cap 75, and undergoes a swap losing 30% resistance (-30% net delta)
- **THEN** the new raw resistance becomes 85 and effective resistance remains 75

#### Scenario: Resistance loss exceeding overcap reduces effective resistance correctly
- **WHEN** a character has raw lightning resistance 80, cap 75, and undergoes a swap losing 10% resistance (-10% net delta)
- **THEN** new raw resistance becomes 70 and effective resistance becomes min(70, 75) = 70

#### Scenario: Unknown raw or overcap prevents fake absolute projection while reporting item delta
- **WHEN** a character has effective lightning resistance 75 but raw uncapped resistance and overcap buffer are `UNKNOWN`, and an item swap has net -30% resistance
- **THEN** the system reports known item delta `-30% Lightning Resistance`, but marks absolute post-swap effective resistance as `UNKNOWN` / `STALE`, refusing to fabricate 45%

#### Scenario: Max resistance 78 respected independently of raw resistance
- **WHEN** a character has verified max Fire Resistance of 78, raw Fire Resistance 100, and undergoes a swap losing 15% Fire Resistance (raw becomes 85)
- **THEN** effective Fire Resistance evaluates to min(85, 78) = 78, respecting the dynamic 78% cap rather than 75%

#### Scenario: Promote candidate mutates loadout and increments revision
- **WHEN** the user executes `companion gear loadout promote-candidate --slot ring1` after finalization
- **THEN** the system replaces the item in `shared_slots.ring1`, increments `loadout.revision` from N to N+1, updates `loadout.updated_at`, and triggers baseline reconciliation

#### Scenario: Unsafe defense projection marks total Armour stale rather than fabricating value
- **WHEN** promoting a candidate body armour with 1050 local Armour replacing an equipped body armour with 850 local Armour on a character with 4200 baseline Armour
- **THEN** the system marks the baseline total Armour as `STALE` / `UNKNOWN` with an audit note that global multiplier interactions require a fresh character-sheet snapshot, refusing to fabricate 4400 total Armour

### Requirement: Baseline Consistency Gate
Before evaluating a candidate equipment item, the `EquipmentIntelligenceEngine` SHALL verify whether `baseline.anchored_loadout_revision` matches `current_loadout.revision`. If the revisions mismatch and affected character facts have not been safely reconciled, the engine SHALL treat those facts as `STALE` or `UNKNOWN`. The engine SHALL NOT use stale baseline facts as authoritative current character values, but SHALL continue to compute and display known equipment-level deltas.

#### Scenario: Matching revision permits authoritative character evaluation
- **WHEN** evaluating a candidate item and `baseline.anchored_loadout_revision == current_loadout.revision`
- **THEN** the engine uses all verified baseline facts as authoritative character-sheet values for deficit and threshold evaluations

#### Scenario: Mismatched revision treats unreconciled facts as stale while showing deltas
- **WHEN** evaluating a candidate item when `baseline.anchored_loadout_revision` (revision 2) does not match `current_loadout.revision` (revision 3) due to an unreconciled defense change
- **THEN** the engine marks baseline defense as `STALE`, refuses to state projected absolute character defense, but continues to report the local equipment defense delta (`+150 Armour delta`)

#### Scenario: Stale baseline cannot produce fabricated absolute projected stats
- **WHEN** evaluating a swap where the baseline resistance fact is marked `STALE`
- **THEN** the recommendation marks the projected absolute value as `UNKNOWN` and classifies the verdict as `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE`

### Requirement: Recommendation Generation Must Not Mutate Current State
The system SHALL ensure that candidate inspection and comparison commands (`companion gear inspect-clipboard`, `companion gear evaluate`, `compare`, `recommendation`) are strictly read-only and SHALL NOT mutate stored loadout data or increment the loadout revision. Generating an `EQUIP_NOW` recommendation SHALL NOT cause the engine to infer or apply an equipment change. Only an explicit user action confirming that the item is equipped in-game (`companion gear loadout promote-candidate`) SHALL mutate the stored loadout.

#### Scenario: Inspect clipboard produces recommendation without mutating loadout
- **WHEN** `companion gear inspect-clipboard` is executed and emits an `EQUIP_NOW` recommendation
- **THEN** `loadout.revision` remains unchanged, all loadout slots retain their prior items, and no state files are mutated

#### Scenario: Recommendation alone does not increment loadout revision
- **WHEN** multiple successive candidate items are inspected via CLI
- **THEN** `loadout.revision` remains exactly at its starting value throughout all inspections

### Requirement: Generalized Item Slot Conflict Topology and Handedness Modeling
The system SHALL model equipment slot occupancy and conflicts via explicit slot-conflict topology (`occupied_slots`, `conflicting_slots`, `allowed_companion_slots`) and `SlotOccupancy` classifications (`SINGLE_SLOT`, `MAIN_HAND`, `OFF_HAND`, `TWO_HAND`, `SHARED_EQUIPMENT_SLOT`, `UNKNOWN_OCCUPANCY`). The normalized `ItemCandidate` model SHALL describe the logical slots it occupies and conflicts with derived from normalized item base type and verified PoE2 game-item metadata, strictly refusing to infer handedness or universal conflict solely from superficial name text or guide assumptions alone.
Under verified PoE2 game-item rules:
1. **Staves**: Two-Handed weapon class occupying both weapon hand slots (`main_hand` and `off_hand`), conflicting with both weapon slots in that weapon set.
2. **Crossbows**: Two-Handed weapon class occupying both weapon hand slots (`main_hand` and `off_hand`), conflicting with both weapon slots in that weapon set.
3. **Quivers**: Off-hand accessory that can ONLY be equipped while wielding a **Bow**, and strictly cannot be equipped with a crossbow.

Therefore, for the verified Fubgun 0.5.5 profile:
- A Flameblast staff in `WEAPON_SET_1` SHALL occupy both `weapon_set_1.main_hand` and `weapon_set_1.off_hand`, conflicting with both weapon slots in Set 1.
- An Oil Grenade crossbow in `WEAPON_SET_2` SHALL occupy both `weapon_set_2.main_hand` and `weapon_set_2.off_hand`, conflicting with both weapon slots in Set 2.
- There SHALL be NO quiver contribution in the Fubgun crossbow set.

Generic occupancy metadata SHALL preserve generic future support for other weapon classes (such as Bows having their own verified Bow + Quiver allowed companion slot exception) without hardcoding every two-handed weapon to identical exception behavior. If base metadata or topology is unrecognized, it SHALL remain `UNKNOWN_TOPOLOGY`, blocking confident full projection.

#### Scenario: Staff occupies and conflicts with both set-1 slots
- **WHEN** parsing a two-handed Flameblast staff targeted at `WEAPON_SET_1`
- **THEN** the parser assigns slot conflict topology indicating it occupies `weapon_set_1.main_hand` and `weapon_set_1.off_hand`, and conflicts with both weapon slots in Set 1, causing both weapon hand slots in Set 1 to be owned upon equip

#### Scenario: Crossbow occupies both weapon slots in set 2 and cannot coexist with quiver
- **WHEN** parsing an Oil Grenade crossbow targeted at `WEAPON_SET_2`
- **THEN** the parser assigns verified PoE2 slot topology showing it occupies both `weapon_set_2.main_hand` and `weapon_set_2.off_hand`, conflicts with both weapon slots in Set 2, and strictly prohibits an off-hand quiver from coexisting

#### Scenario: Quiver requires wielding a bow and is not part of Fubgun loadout
- **WHEN** evaluating a quiver item candidate or attempting to assign a quiver to an off-hand slot
- **THEN** the system verifies that quivers are allowed only when wielding a Bow, rejects pairing a quiver with a crossbow, and confirms quivers are not part of the Fubgun V1 loadout model

#### Scenario: Generic occupancy metadata preserves bow and quiver compatibility without hardcoding exceptions
- **WHEN** parsing a Bow base type configured in verified base metadata with `allowed_companion_slots: [SlotType.OFF_HAND]` for quivers
- **THEN** the engine permits an off-hand quiver for the bow while maintaining two-slot conflict for staves and crossbows

#### Scenario: Unknown topology blocks confident full projection
- **WHEN** parsing an item whose weapon base type or slot topology is unrecognized or ambiguous
- **THEN** the parser assigns `slot_occupancy: SlotOccupancy.UNKNOWN_OCCUPANCY` with unknown topology, and the engine refuses to assert a confident full loadout projection, emitting `INSUFFICIENT_DATA`

### Requirement: Two-Handed Weapon Projection and Opposing Set Isolation
When a candidate weapon targets a weapon set, the projected loadout for that weapon set SHALL replace the main-hand item AND remove/disable any verified conflicting off-hand item in that SAME weapon set. A crossbow candidate in `weapon_set_2` SHALL replace the current crossbow in Set 2, own both hand slots in Set 2, introduce no off-hand quiver contribution, and leave `weapon_set_1` completely unaffected. A staff candidate in `weapon_set_1` SHALL replace the current staff in Set 1, own both hand slots in Set 1, and leave `weapon_set_2` completely unaffected. The system SHALL NOT subtract or preserve a fictional quiver. The opposing weapon set SHALL remain completely untouched. When replacing an equipped two-handed weapon with a one-handed candidate, the system SHALL NOT fabricate or assume an off-hand item; an empty or unobserved off-hand slot SHALL remain empty or `UNKNOWN`.

#### Scenario: Two-handed staff replaces one-hand weapon and off-hand shield in weapon set 1
- **WHEN** `weapon_set_1` currently equips a one-handed wand in `main_hand` and a shield in `off_hand`, and a candidate two-handed staff targeting `WEAPON_SET_1` is evaluated
- **THEN** the projected `weapon_set_1` assigns the staff to `main_hand` and removes the shield from `off_hand`, while `weapon_set_2` remains completely unchanged

#### Scenario: One-hand candidate replacing two-handed staff does not fabricate off-hand item
- **WHEN** `weapon_set_1` currently equips a two-handed staff, and a candidate one-handed wand targeting `WEAPON_SET_1` is evaluated
- **THEN** the projected `weapon_set_1` assigns the wand to `main_hand`, leaves `off_hand` empty (`None`), and does NOT invent a hypothetical shield or off-hand stat contribution

#### Scenario: Weapon set 2 remains isolated during set 1 modifications
- **WHEN** evaluating any candidate swap targeting `WEAPON_SET_1`
- **THEN** all slots in `weapon_set_2` (e.g. crossbow occupying both hand slots) retain their exact equipped items and contributions without modification

#### Scenario: Modifying weapon set 2 crossbow handled independently and affects set 2 only
- **WHEN** evaluating a candidate crossbow targeting `WEAPON_SET_2`
- **THEN** the candidate replaces the equipped crossbow in `weapon_set_2`, owns both hand slots in Set 2, introduces no off-hand quiver contribution, and does not affect `weapon_set_1` (Flameblast staff)

#### Scenario: Shared equipment remains shared across both weapon sets
- **WHEN** evaluating a candidate Body Armour in shared equipment
- **THEN** the projected swap applies across both weapon sets, re-evaluating shared defense and attribute requirements for both Set 1 and Set 2

### Requirement: Occupancy-Aware Multi-Slot Contribution and Requirement Cascades
When a swap replaces a multi-slot configuration (such as equipping a two-handed weapon displacing both a main-hand weapon and an off-hand shield), the system SHALL subtract contributions from ALL displaced equipped items. The system SHALL recompute character Life, elemental/chaos resistances, attributes (Strength, Dexterity, Intelligence), defenses, requirement cascades, and build-specific modifiers for the entire displaced topology. The system SHALL NOT subtract only the main-hand item while retaining an incompatible off-hand item's contributions. If candidate occupancy or topology is `UNKNOWN_OCCUPANCY` / `UNKNOWN_TOPOLOGY`, the engine SHALL NOT assert a confident projected full state.

#### Scenario: Two-handed swap removes both main-hand and shield contributions
- **WHEN** replacing a one-hand wand (+20 Intelligence) and shield (+35% Lightning Res, +15 Strength, 300 Armour) with a two-handed staff
- **THEN** the system subtracts the wand's +20 Int AND the shield's +35% Lightning Res, +15 Str, and 300 Armour before applying the staff's contributions

#### Scenario: Swapping two-handed weapon prevents phantom off-hand contributions
- **WHEN** evaluating a candidate staff in `weapon_set_1` or crossbow in `weapon_set_2`
- **THEN** the candidate owns both hand slots in its target set, affects that target set only, and no phantom off-hand contribution (such as a fictional quiver or retained shield) enters projected stats

#### Scenario: Requirement cascade detects attribute loss from displaced off-hand item
- **WHEN** equipping a two-handed staff displaces an off-hand shield providing +25 Dexterity, dropping character Dexterity to 85 where an equipped shared gem requires 100 Dexterity
- **THEN** the system flags a requirement cascade failure specifically citing the displaced shield's lost Dexterity, preventing an unconditional `EQUIP_NOW` verdict

#### Scenario: Unknown handedness blocks confident projected full state
- **WHEN** evaluating a weapon candidate with `UNKNOWN_OCCUPANCY`
- **THEN** the engine warns that slot occupancy is uncertain, refuses to assert confident full loadout projection, and emits `INSUFFICIENT_DATA`

### Requirement: Build-Breaker Certainty Model and High-Risk Unknown Gate
The system SHALL classify build-relevant modifiers under an explicit three-state certainty model:
1. `VERIFIED_SAFE`: Modifier is proven safe for the build's mechanics (e.g. `FIRE_RESISTANCE`, `% increased Fire Damage`).
2. `VERIFIED_BUILD_BREAKER`: Modifier is proven harmful to the build's mechanics in the target slot/weapon-set context (e.g. post-swap shared ring with added fire to attacks, or Oil Grenade crossbow with flat fire damage).
3. `UNKNOWN_APPLICABILITY`: Modifier text or mechanism plausibly relates to a build-breaking rule but its applicability to active skills (such as Oil Grenade attacks) cannot currently be proven.

If a candidate item contains a modifier classified as `UNKNOWN_APPLICABILITY` that could plausibly activate a verified `HARD_REJECT` mechanic, the `EquipmentIntelligenceEngine` MUST NOT emit `EQUIP_NOW` as a confident verdict. The engine SHALL emit either `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE` with an explicit `HIGH_RISK` verification-required warning. The engine SHALL NOT fabricate an unproven `HARD_REJECT` and SHALL NOT silently ignore the risk.

#### Scenario: Verified build breaker emits REJECT verdict
- **WHEN** evaluating a post-swap shared ring containing `Adds 12 to 24 Fire Damage to Attacks`
- **THEN** the modifier is classified as `VERIFIED_BUILD_BREAKER`, the engine flags the Fubgun ignite-ruining mechanic, and emits a `REJECT` verdict

#### Scenario: Verified safe fire modifier proceeds to normal evaluation
- **WHEN** evaluating a post-swap candidate item containing `+35% to Fire Resistance`
- **THEN** the modifier is classified as `VERIFIED_SAFE` and the item proceeds through standard evaluation without penalty

#### Scenario: Unknown fire applicability blocks confident EQUIP_NOW despite high generic stats
- **WHEN** evaluating a candidate ring with outstanding stats (+100 Life, +80% total Res) but containing a novel, unverified modifier `Gain 8% of Physical Damage as Extra Fire Damage during Focus`
- **THEN** the engine classifies the modifier as `UNKNOWN_APPLICABILITY`, identifies the plausible Oil Grenade ignite risk, refuses to emit `EQUIP_NOW`, and emits `CONDITIONAL_UPGRADE` with a prominent `HIGH_RISK` warning or `INSUFFICIENT_DATA`

#### Scenario: Subsequent verification of safe applicability permits re-evaluation
- **WHEN** a previously unknown fire modifier is subsequently verified in the rule engine as not applying to Oil Grenade attacks
- **THEN** re-evaluating the candidate classifies the modifier as `VERIFIED_SAFE` and allows normal upgrade consideration

#### Scenario: Subsequent verification of harmful applicability updates verdict to REJECT
- **WHEN** an unverified fire modifier is confirmed to apply to Oil Grenade attacks
- **THEN** re-evaluating the candidate updates the modifier to `VERIFIED_BUILD_BREAKER` and triggers a `REJECT` verdict

### Requirement: Deterministic Verdict Precedence
The system SHALL resolve the final equipment recommendation verdict through an explicit, non-scalar precedence hierarchy rather than collapsing trade-offs into a single numeric score:
1. **Tier 1: Verified Build Breaker**: If any modifier is `VERIFIED_BUILD_BREAKER`, the verdict SHALL be `REJECT`.
2. **Tier 2: Critical Requirement Failure**: If the swap causes the candidate item, equipped loadout, or build-critical gems to fail level or attribute requirements, the verdict SHALL be `REJECT` or `CONDITIONAL_UPGRADE` depending on attribute deficit recoverability.
3. **Tier 3: Unknown Potential Build Breaker**: If any modifier has `UNKNOWN_APPLICABILITY` regarding a critical build-breaking rule, confident `EQUIP_NOW` SHALL be blocked; the verdict SHALL be `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE` with `HIGH_RISK` notice.
4. **Tier 4: New Critical Character Deficiency**: If the swap creates an unmitigated defense or resistance deficit below target caps, the verdict SHALL be `CONDITIONAL_UPGRADE` or `REJECT`.
5. **Tier 5: Normal Gear Improvement & Trade-offs**: If Tiers 1-4 pass safely, the item SHALL be evaluated for net improvement. If the candidate item causes a negative delta in local defenses (`armour_delta < 0`, `evasion_delta < 0`, or `es_delta < 0`) or trades off one defense type for another, the system SHALL NOT emit `EQUIP_NOW` or clean `DOMINANT_IMPROVEMENT`; the verdict SHALL be `CONDITIONAL_UPGRADE` with `flags=["MIXED_TRADEOFF"]`. Otherwise, net positive upgrades with safe trade-offs evaluate to `EQUIP_NOW`, minor trade-offs evaluate to `CONDITIONAL_UPGRADE`, and sidegrades evaluate to `KEEP_FOR_LATER`.

#### Scenario: Build breaker takes precedence over high attribute gains
- **WHEN** a candidate ring provides +50 to all Attributes and fixes all character deficits, but has flat fire damage to attacks post-swap
- **THEN** Tier 1 precedence triggers `REJECT` immediately, overruling attribute and deficit improvements

#### Scenario: Critical requirement failure takes precedence over unknown build-breaker
- **WHEN** a candidate item fails character attribute requirements and also contains an unverified fire modifier
- **THEN** Tier 2 precedence flags the requirement failure as the primary blocker before Tier 3 evaluation

#### Scenario: Unknown potential build-breaker prevents EQUIP_NOW when stats are positive
- **WHEN** an item satisfies all requirements, creates no deficiencies, and improves Life, but contains an unverified fire modifier
- **THEN** Tier 3 precedence blocks `EQUIP_NOW` and outputs `CONDITIONAL_UPGRADE` with `HIGH_RISK` explanation

### Requirement: Support for Partial Projection and Separation of Deltas from Absolute Values
The system SHALL support partial swap projection when baseline character stats or equipped loadout slots are incomplete or `UNKNOWN`. The system SHALL deterministically compute and report `KNOWN DELTA` from compared equipment contributions (e.g. net change in resistance) but SHALL NOT assert or fabricate `PROJECTED ABSOLUTE VALUE` (e.g. claiming final resistance drops from 75% to 47%) unless the current baseline stat is verified. When critical baseline stats are `UNKNOWN`, the system SHALL classify the verdict as `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE` with explicitly identified risk. Furthermore, when an equipped slot is `UNKNOWN` (such as in a partial loadout), the system SHALL describe candidate properties, but SHALL NOT claim an exact net slot delta against the unobserved displaced item, and SHALL lower evaluation confidence.

#### Scenario: Reports known equipment delta when current baseline resistance is UNKNOWN
- **WHEN** the baseline Lightning Resistance is `UNKNOWN`, the currently equipped ring provides +40% Lightning Resistance, and a candidate ring provides +12% Lightning Resistance
- **THEN** the system calculates and reports a deterministic equipment delta of `-28% Lightning Resistance` while reporting the projected absolute resistance as `UNKNOWN`

#### Scenario: Refuses to state absolute resistance transition without verified baseline
- **WHEN** projecting an item swap where current Cold Resistance is `UNKNOWN`
- **THEN** the recommendation explicitly separates known delta (`-15% Cold Resistance`) from absolute state (`UNKNOWN -> UNKNOWN`) and does not assert a specific ending percentage

#### Scenario: Candidate against unknown current slot cannot claim exact net delta
- **WHEN** evaluating a candidate boots item while the current boots slot in the finalized loadout is `UNKNOWN`
- **THEN** the system describes the candidate boots properties, refuses to claim an exact net boots delta against the unobserved item, and lowers recommendation confidence to `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE`

### Requirement: Character-Stat Acquisition and Explicit Manual Baseline Fallback
The system SHALL explicitly distinguish automatically obtainable character stats from unavailable stats. Recognizing that the official PoE2 Character API does not expose character-sheet stats (Life, Resistances, Defenses, Movement Speed), the system SHALL provide an explicit manual baseline command (`companion gear baseline set`) and snapshot import mechanism allowing users to optionally set Life, Fire/Cold/Lightning/Chaos resistances, Armour, Evasion, Energy Shield, Attributes, Movement Speed, and Max Resistances, preferring transparent manual input over false automation or heuristic guesswork.

#### Scenario: Manual baseline command establishes verified character stat block
- **WHEN** the user executes `companion gear baseline set --life 1450 --fire-res 75 --cold-res 72 --lightning-res 68 --chaos-res -10 --armour 4200 --evasion 1100`
- **THEN** the system stores the values as `CharacterStatBaseline` with source `MANUAL_USER_INPUT` and verification `VERIFIED`, enabling absolute swap projection for provided fields while leaving unmentioned fields as `UNKNOWN`

#### Scenario: Automatic ingestion reports unobserved fields truthfully
- **WHEN** official character API synchronization completes without character panel stats
- **THEN** the system indicates which stats were captured from equipment vs which character-sheet stats remain `UNKNOWN`, prompting the user for manual baseline setup if required

### Requirement: Character Baseline vs Item-Contribution Double-Count Protection
The system SHALL strictly distinguish character-sheet baseline totals from loadout-derived item contributions to prevent double-counting. When a user manually inputs total character Armour (e.g. 4200), the system SHALL NOT add equipped body armour local defense again to reconstruct baseline Armour. Projected absolute stats SHALL subtract the deterministic contribution of the replaced item and add the deterministic contribution of the candidate item only where contribution semantics are valid; if global scaling interactions make absolute projection unsafe, the system SHALL report known local deltas and flag the uncertainty.

#### Scenario: Total reported character Armour is not double-counted with equipped body armour
- **WHEN** a user enters manual baseline Armour of 4200 and currently equips body armour with 850 local Armour
- **THEN** the system maintains current baseline Armour at 4200 and does not sum 4200 + 850 to create an inflated baseline

#### Scenario: Candidate defense projection subtracts old contribution and adds new candidate
- **WHEN** evaluating a candidate body armour with 1050 local Armour replacing an equipped body armour with 850 local Armour on a character with 4200 baseline Armour
- **THEN** the system deterministically projects the swap delta as `+200 local Armour` and projected total Armour as 4400 when linear contribution semantics hold, or reports `+200 local Armour delta` with reduced certainty when complex global multipliers are active

### Requirement: First-Class Two-Weapon-Set Loadout Modeling and Evaluation
The system SHALL model equipped gear using a dual-weapon-set loadout structure consisting of `SHARED EQUIPMENT` (Helm, Body Armour, Gloves, Boots, Amulet, Ring 1, Ring 2, Belt), `WEAPON_SET_1` (MainHand, OffHand), and `WEAPON_SET_2` (MainHand, OffHand). The system SHALL NOT restrict V1 evaluation to the currently active weapon set only. Candidate weapon evaluations SHALL require or determine a `target_weapon_set`, evaluating swaps within the targeted set while preserving the opposing weapon set intact and verifying `(passive_id, weapon_set_context)` build rules.

#### Scenario: Evaluates staff replacement strictly within Flameblast weapon set
- **WHEN** evaluating a candidate staff targeted at `WEAPON_SET_1` for Fubgun's build
- **THEN** the system evaluates replacement against the equipped `WEAPON_SET_1` items, leaves `WEAPON_SET_2` (crossbow setup) completely unaffected, and checks Set 1 build rules

#### Scenario: Evaluates crossbow replacement strictly within Oil Grenade weapon set
- **WHEN** evaluating a candidate crossbow targeted at `WEAPON_SET_2`
- **THEN** the system evaluates replacement against the equipped `WEAPON_SET_2` items without modifying `WEAPON_SET_1` loadout

#### Scenario: Shared equipment swap evaluates impact across both weapon sets
- **WHEN** evaluating candidate Body Armour or Amulet in shared equipment
- **THEN** the system evaluates defensive and attribute impacts uniformly and validates compatibility across both weapon set contexts

#### Scenario: Rejects candidate weapon targeted at invalid or mismatched weapon set
- **WHEN** a candidate weapon is evaluated with a mismatched or invalid `target_weapon_set`
- **THEN** the system flags the configuration error and does not silently substitute the currently active weapon set

### Requirement: Offline Manual Loadout Ingestion via Clipboard, Finalization, and Slot Promotion
The system SHALL provide an explicit, passive manual loadout ingestion workflow operating without official API access:
1. First, the user populates a draft loadout by hovering equipped items in-game, pressing `Ctrl+C`, and running `companion gear loadout set-clipboard --slot <slot>` (`boots`, `ring1`, `ring2`, `amulet`, `weapon-set-1-main`, `weapon-set-1-off`, `weapon-set-2-main`, `weapon-set-2-off`).
2. Second, the user finalizes the loadout via `companion gear loadout finalize`, establishing `loadout_id`, initial stable `revision = 1`, and recording known and unknown slots.
3. Third, the user captures character baseline via `companion gear baseline set`, which anchors to revision 1.
The system SHALL provide `companion gear loadout show` to inspect the full loadout, `companion gear loadout clear <slot>` to remove a slot entry, and `companion gear loadout promote-candidate` to promote an evaluated candidate item to equipped status after finalization. Generating a recommendation SHALL NOT mutate the stored loadout.

#### Scenario: Ingests boots from clipboard into current loadout
- **WHEN** a user copies equipped boots in-game and executes `companion gear loadout set-clipboard --slot boots`
- **THEN** the system parses the clipboard text, validates slot compatibility, and saves the item into `shared_slots.boots` with source `CLIPBOARD_ITEM_TEXT`

#### Scenario: Finalize current loadout establishes loadout id and revision 1
- **WHEN** the user executes `companion gear loadout finalize` on a draft loadout
- **THEN** the system marks the loadout finalized, initializes `revision: 1`, records `known_slots` and `unknown_slots`, and prepares the loadout for baseline anchoring

#### Scenario: Ingests rings into distinct ring1 and ring2 slots
- **WHEN** a user copies two distinct rings and runs `companion gear loadout set-clipboard --slot ring1` followed by `companion gear loadout set-clipboard --slot ring2`
- **THEN** the system preserves both rings in distinct `ring1` and `ring2` slots without overwriting one with the other

#### Scenario: Ingests weapons into explicit weapon sets without blind inference
- **WHEN** a user runs `companion gear loadout set-clipboard --slot weapon-set-1-main` for a staff and `companion gear loadout set-clipboard --slot weapon-set-2-main` for a crossbow
- **THEN** the system assigns the staff strictly to `weapon_set_1.main_hand` and the crossbow strictly to `weapon_set_2.main_hand` without inferring set from active game state

#### Scenario: Candidate evaluation does not mutate stored loadout
- **WHEN** `companion gear inspect-clipboard` returns an `EQUIP_NOW` recommendation for a candidate item
- **THEN** the stored `EquippedLoadout` remains unchanged until the user explicitly runs `companion gear loadout promote-candidate`

### Requirement: Loadout Persistence, Provenance, and Conflict Detection
The system SHALL persist the established loadout locally in `EquippedLoadout` where every slot entry retains the normalized `ItemCandidate`, `source` (`CLIPBOARD_ITEM_TEXT`, `GGG_OFFICIAL_API`, `MANUAL`), `observed_at`, `verification`, and `evidence_ref`. If official API synchronization supplies equipment that contradicts manually ingested clipboard items for the same slot, the system SHALL NOT silently overwrite or merge the states; it SHALL flag the slot verification as `CONFLICTING` and surface the discrepancy in the Gear Brain.

#### Scenario: Stored loadout persists slot provenance and timestamps
- **WHEN** an item is saved into a loadout slot via manual clipboard ingestion
- **THEN** the persisted record contains `source: CLIPBOARD_ITEM_TEXT`, timestamp `observed_at`, `verification: SINGLE_SOURCE`, and raw evidence hash

#### Scenario: Contradictory API and manual loadout states flag CONFLICTING
- **WHEN** official API synchronization detects a different equipped ring than the one recorded via manual clipboard ingestion
- **THEN** the system sets slot verification to `CONFLICTING`, records both evidence references, and alerts the user to confirm the active equipped item

#### Scenario: Stale manual equipment is flagged as stale
- **WHEN** an equipped slot has not been refreshed past its `stale_after` threshold
- **THEN** the system displays the slot as `STALE` and cautions the user during swap evaluation

#### Scenario: Unpopulated loadout slot remains UNKNOWN
- **WHEN** a loadout slot has not been populated by either API or manual ingestion
- **THEN** the slot is treated as `UNKNOWN`, candidate replacement treats replaced item contribution as empty, and the engine flags the unobserved slot context

### Requirement: Local Item Modifiers vs Global Character Contributions and Double-Counting Prevention
The system SHALL classify all parsed item modifiers into typed application scopes: `LOCAL_ITEM_STAT`, `GLOBAL_CHARACTER_STAT`, `REQUIREMENT`, `BUILD_MECHANIC`, `CONDITIONAL`, or `UNKNOWN_SCOPE`. The system SHALL ensure that displayed item defense properties (Armour, Evasion, Energy Shield) that already incorporate local percentage modifiers are not double-counted by applying the local modifier again at the global character level.

#### Scenario: Displayed item Armour does not double-count local increased Armour
- **WHEN** a body armour item has displayed Armour of 450 and an explicit modifier `+42% increased Armour`
- **THEN** the system treats 450 as the final local Armour contribution, marks the percentage modifier as `LOCAL_ITEM_STAT`, and does not add +42% to the global character Armour multiplier

#### Scenario: Distinguishes local weapon attack modifiers from global character damage
- **WHEN** a weapon has `% increased Physical Damage` marked as local to weapon attacks
- **THEN** the modifier is categorized as `LOCAL_ITEM_STAT` and is not applied as a generic global character damage multiplier for spell skills

#### Scenario: Preserves unmodeled modifier scope as UNKNOWN_SCOPE
- **WHEN** an item has a complex or unmodeled modifier text
- **THEN** the system assigns scope `UNKNOWN_SCOPE`, logs raw text for audit, and does not apply unverified numeric math

### Requirement: Deterministic Item Contribution Model
The system SHALL map parsed items into an explicit `ItemContribution` model that aggregates character-relevant effects: Life delta source, resistance contributions (Fire, Cold, Lightning, Chaos), attribute contributions (Strength, Dexterity, Intelligence), movement speed contribution, final local armour and evasion contributions, global character modifiers, weapon-set-specific modifiers, build mechanic flags, and unresolved modifiers. Loadout swap projections SHALL operate exclusively on `ItemContribution` semantics rather than unclassified modifier summation.

#### Scenario: Item contribution aggregates normalized defensives and attributes
- **WHEN** an item candidate with +78 Life, +25% Fire Res, +14 Strength, and 280 base Armour is mapped to `ItemContribution`
- **THEN** the contribution exposes exact structured fields for Life, Fire Res, Strength, and Armour contribution ready for loadout delta computation

### Requirement: Dynamic Resistance Limits, Raw Overcap Modeling, and Rebase Policy
The system SHALL model resistance goals dynamically using `raw_uncapped_resistance`, `current_effective_resistance`, `current_max_resistance`, `target_resistance`, and `overcap_buffer`. The system SHALL NOT hardcode 75% as an immutable engine constant, but SHALL use verified max resistance (e.g. 78% if maximum resistance is increased) while distinguishing capped effective resistance from raw uncapped buffer. Additive rebasing SHALL be applied only to raw uncapped resistance when proven, never directly to capped effective values. The system SHALL NOT invent campaign or progression resistance penalty calculations without verified game rules.

#### Scenario: Evaluates resistance against modified dynamic maximum resistance
- **WHEN** a character has a verified maximum Fire Resistance of 78% and currently has 78% effective resistance with a 15% overcap buffer
- **THEN** the system uses 78% as the target threshold and measures marginal overcap buffer relative to 78% rather than 75%

#### Scenario: Avoids fabricating progression resistance penalties
- **WHEN** calculating absolute resistance from components without verified Act progression penalty context
- **THEN** the system marks absolute resistance as `UNKNOWN` rather than inventing an unverified penalty deduction, while continuing to report exact equipment deltas

### Requirement: Whole-Loadout Requirement Cascade Validation
The system SHALL revalidate the attribute requirements (Strength, Dexterity, Intelligence) and level requirements of all equipped items across the entire relevant loadout and build-critical gems whenever a proposed swap alters character attributes. If removing the current item causes an equipped item or build-critical gem to fail its attribute requirement, the system SHALL flag the requirement cascade deficiency and adjust the verdict to `CONDITIONAL_UPGRADE` or `REJECT`.

#### Scenario: Removing amulet breaks Dexterity requirement on equipped weapon
- **WHEN** replacing an amulet providing +30 Dexterity with a candidate amulet providing 0 Dexterity drops character Dexterity to 94, while an equipped crossbow requires 112 Dexterity
- **THEN** the system detects `NEW_DEFICIENCY: Dexterity 94 < required 112 for equipped slot WeaponSet2.MainHand`, flags a requirement cascade failure, and emits `CONDITIONAL_UPGRADE` or `REJECT`

#### Scenario: Swap satisfies candidate requirement but breaks socketed gem requirement
- **WHEN** a candidate gear swap satisfies its own attribute requirements but causes a build-critical gem to become uncastable due to lost Intelligence
- **THEN** the system reports the broken gem requirement dependency and prevents an unconditional `EQUIP_NOW` verdict

### Requirement: Exact Fubgun Build-Breaker Predicates and Staff Exception
The system SHALL evaluate build-breaker rules against exact normalized modifier families, item slot, shared vs weapon-set placement, target weapon set, whether the modifier is active/applicable in Oil Grenade context, and progression stage. The system SHALL enforce the verified Fubgun 0.5.5 rule: flat fire damage or extra fire damage anywhere on gear is forbidden post-swap if it applies to Oil Grenade, with Flameblast staff (weapon set 1) as the sole verified exception. The system SHALL NOT use broad substring matching and SHALL NOT reject benign Fire modifiers.

#### Scenario: Post-swap shared ring with flat fire to attacks triggers HARD_REJECT
- **WHEN** evaluating a candidate ring in shared equipment for Fubgun post-swap stage (`lvl 52 Swap` or later) containing `Adds 12 to 24 Fire Damage to Attacks`
- **THEN** the engine detects an attack-applicable flat fire damage modifier on shared gear that applies to Oil Grenade, triggers `HARD_REJECT`, and rejects the item

#### Scenario: Post-swap shared gloves with added fire applicable to Oil Grenade triggers HARD_REJECT
- **WHEN** evaluating candidate gloves in shared equipment containing added fire damage applicable to attacks
- **THEN** the engine detects that the fire damage applies to Oil Grenade attacks post-swap, triggers `HARD_REJECT`, and rejects the item

#### Scenario: Oil Grenade crossbow in weapon set 2 with added or extra fire triggers HARD_REJECT
- **WHEN** evaluating a candidate crossbow targeted at `WEAPON_SET_2` containing flat added Fire Damage or extra Fire Damage
- **THEN** the engine detects that the modifier is active during Oil Grenade attacks, triggers `HARD_REJECT`, and rejects the item

#### Scenario: Flameblast staff in weapon set 1 with verified Fire modifier is NOT rejected
- **WHEN** evaluating a candidate staff targeted at `WEAPON_SET_1` containing fire damage modifiers that are inactive when weapon set 2 is active
- **THEN** the engine applies the verified Fubgun staff exception, determines the modifier does not apply to Oil Grenade attacks, and does NOT trigger a build-breaker rejection

#### Scenario: Item with Fire Resistance is NOT rejected
- **WHEN** evaluating a post-swap candidate item containing `+35% to Fire Resistance`
- **THEN** the system classifies the modifier as `FIRE_RESISTANCE`, confirms it is a defensive stat, and does NOT trigger a build-breaker rejection

#### Scenario: Item with increased Fire Damage is NOT rejected solely by fire rule
- **WHEN** evaluating an item containing `22% increased Fire Damage`
- **THEN** the system classifies the modifier as `INCREASED_FIRE_DAMAGE`, confirms it is not flat added or extra fire damage, and does NOT trigger the build-breaker rejection

#### Scenario: Item with unrelated fire text is NOT rejected
- **WHEN** evaluating an item with text `+1 to Level of all Fire Spell Skill Gems` or descriptive fire lore text
- **THEN** the system classifies it as `FIRE_SPELL_LEVEL` or non-harmful affix, avoiding false build-breaker triggers

#### Scenario: Pre-swap progression stage evaluates under stage-aware grenade rules
- **WHEN** evaluating an item during pre-swap leveling stages (e.g. `lvl 15-31` or `lvl 32-51`) before Flameblast swap
- **THEN** the system applies the pre-swap stage rules and does not enforce the post-swap dual-weapon staff exception rule prematurely

### Requirement: Official API Capability Gating and PoE2 Limitations
The system SHALL accurately gate official API capabilities according to current Path of Exile 2 developer documentation. The system SHALL declare `OfficialCharacterData.equipment` as available when OAuth is configured, but SHALL explicitly designate unequipped inventory, rucksacks, and private account stashes as `UNAVAILABLE_BY_CURRENT_OFFICIAL_API` for PoE2. The system SHALL NOT attempt to discover backpack items or crawl stashes via the official API, maintaining these architectures dormant under capability gates.

#### Scenario: API capability reports backpack discovery unavailable for PoE2
- **WHEN** querying official API capability for character inventory or account stash discovery in PoE2
- **THEN** the system returns `UNAVAILABLE_BY_CURRENT_OFFICIAL_API` with documented reference and routes candidate inspection through clipboard text

### Requirement: OAuth 2.1 Specification and External Registration Freeze Handling
The system SHALL adhere to official OAuth 2.1 public client requirements using Authorization Code grant with PKCE (`S256` code challenge) and `localhost` redirect URIs. The system SHALL record the external limitation that new developer application registration is currently unavailable per GGG documentation. The system SHALL feature-gate official synchronization into `API_AVAILABLE`, `AUTH_CONFIGURED`, and `AUTH_UNAVAILABLE` states without crashing or blocking core offline functionality.

#### Scenario: Unconfigured OAuth credentials yields AUTH_UNAVAILABLE without blocking gear evaluation
- **WHEN** `POE2_CLIENT_ID` or `POE2_ACCESS_TOKEN` environment variables are absent
- **THEN** the API subsystem enters `AUTH_UNAVAILABLE` state while the Equipment Intelligence engine remains fully operational for manual and clipboard workflows

### Requirement: Core V1 Workflow Operational Without Official API
The system SHALL provide a complete, self-contained Equipment Intelligence V1 workflow operational entirely without GGG official API credentials. The workflow SHALL support: (1) establishing current character baseline via `companion gear baseline set`, (2) establishing currently equipped items per slot via `companion gear loadout set-clipboard`, (3) copying candidate item text in-game via `Ctrl+C`, (4) parsing and projecting candidate text via `companion gear inspect-clipboard`, (5) producing explainable recommendations, and (6) explicitly promoting equipped upgrades via `companion gear loadout promote-candidate`.

#### Scenario: Complete candidate evaluation executed entirely offline
- **WHEN** an offline user with an established manual baseline copies an item to clipboard and runs `companion gear inspect-clipboard`
- **THEN** the system parses the item, projects the swap against the saved loadout, checks build rules and requirement cascades, and outputs the recommendation verdict without network access

### Requirement: Dynamic Character Deficiency and Marginal Value Modeling
The system SHALL model character deficiencies dynamically across defensive and attribute stats (Life, Fire Resistance, Cold Resistance, Lightning Resistance, Chaos Resistance, Armour, Evasion, Energy Shield, Movement Speed, Strength, Dexterity, and Intelligence), distinguishing `CURRENT`, `REQUIRED` (target threshold), `DEFICIT`, `SURPLUS`, and semantic `VERIFICATION` status. The system SHALL evaluate stats using marginal value, weighting deficit stats as critical priority while discounting surplus stats beyond thresholds.

#### Scenario: High marginal value assigned to deficit resistance
- **WHEN** a character has 43% Lightning Resistance against a 75% target threshold (32% deficit)
- **THEN** a candidate item providing Lightning Resistance receives critical marginal valuation in the defensive gap analysis

#### Scenario: Low marginal value assigned to overcapped surplus resistance
- **WHEN** a character has 78% Fire Resistance against a 75% target threshold (3% surplus)
- **THEN** a candidate item providing additional Fire Resistance receives diminished marginal valuation compared to an item addressing an active deficit

### Requirement: Four Primary Recommendation Verdicts and Unknown State Handling
The system SHALL classify candidate gear evaluations into four primary recommendation verdicts (`EQUIP_NOW`, `CONDITIONAL_UPGRADE`, `KEEP_FOR_LATER`, `REJECT`) and SHALL emit `INSUFFICIENT_DATA` when required character facts are `UNKNOWN`, strictly refusing to convert missing or unknown facts to zero.

#### Scenario: Candidate immediately improves build with safe trade-offs evaluates to EQUIP_NOW
- **WHEN** a candidate item provides immediate net improvements to character survivability or needed offense with acceptable trade-offs
- **THEN** the system issues an `EQUIP_NOW` verdict

#### Scenario: Candidate is strong but breaks resistance cap evaluates to CONDITIONAL_UPGRADE
- **WHEN** a candidate item possesses desirable high-tier stats but swapping it immediately creates an unmitigated defense deficit
- **THEN** the system issues a `CONDITIONAL_UPGRADE` verdict detailing prerequisites for equipping

#### Scenario: Missing required character state facts evaluates to INSUFFICIENT_DATA
- **WHEN** essential character attributes or equipped slot data have `UNKNOWN` verification status preventing factual delta calculation
- **THEN** the system issues an `INSUFFICIENT_DATA` verdict and reports the unobserved required fields without guessing

### Requirement: Slot-Specific Opportunity Cost and Evaluation
The system SHALL apply slot-specific evaluation rules that weigh modifiers according to the unique opportunity cost of the equipment slot (e.g. Movement Speed on Boots, base defenses and Life on Body Armour, resistance and attribute balancing on Jewelry, build-relevant mechanics on Weapons and Amulets).

#### Scenario: Movement speed heavily weighted on boots
- **WHEN** evaluating candidate footwear in the `Boots` slot
- **THEN** Movement Speed is evaluated as a primary requirement with high opportunity cost penalty if absent

### Requirement: Normalized Item Parsing and Unknown Modifier Isolation
The system SHALL parse item text from manual clipboard (`Ctrl+C`) or API responses into structured `ItemCandidate` models with typed normalized modifiers (`modifier_type`, `value`, `scope`, `slot_occupancy`). Unknown or unmodeled modifiers SHALL be captured as `UNKNOWN_MODIFIER` with raw text, scope `UNKNOWN_SCOPE`, and provenance preserved, strictly refusing to guess modifier mechanics.

#### Scenario: Standard item text parsed into normalized typed modifiers with scope
- **WHEN** standard PoE2 item clipboard text containing `+32% to Lightning Resistance` is parsed
- **THEN** the parser outputs normalized modifier `LIGHTNING_RESISTANCE: 32` with scope `GLOBAL_CHARACTER_STAT` while retaining raw source text

### Requirement: Strict Read-Only Game Safety and Anti-Automation Compliance
The system SHALL operate in a strictly passive, read-only manner relative to the game client and operating system. The system SHALL NOT simulate keyboard or mouse input (`SendInput`, `pyautogui`, `pynput`), SHALL NOT access game process memory or inject DLLs, and SHALL NOT automate equipping, moving, or trading items.

#### Scenario: Clipboard candidate inspection reads clipboard passively without simulating keypresses
- **WHEN** inspecting a candidate item from clipboard
- **THEN** the system only reads the text currently present in the operating system clipboard and executes zero simulated keystrokes

### Requirement: Explainable Deltas and Separation of AI Advisory Plane
The system SHALL accompany every recommendation verdict with explicit, deterministic numeric deltas, identified trade-offs, and affected deficiency gaps. Any conversational or AI advisory summary (e.g. from Hermes) SHALL be strictly constrained to explaining deterministic facts and SHALL NOT alter or hallucinate numeric stats, deltas, or verdicts.

#### Scenario: Recommendation outputs complete explainable numeric deltas
- **WHEN** a recommendation is generated
- **THEN** the output includes explicit stat deltas, current vs projected values, resolved deficiencies, new deficits created, and plain-language explanation

### Requirement: Separation of Loadout Structural Consistency from Per-Fact Freshness
The system SHALL separate loadout structural consistency (verification that `baseline.anchored_loadout_revision` matches `current_loadout.revision` and loadout fingerprints align) from individual `CharacterFact` freshness. The system SHALL evaluate `CharacterFact.is_known` such that facts with `CONFLICTING`, `UNKNOWN`, or `STALE` verification states are treated as unusable (`is_known: False`). A synchronized loadout revision SHALL NOT imply that every individual stat fact is fresh, and an individual stale fact SHALL NOT invalidate loadout structural consistency.

#### Scenario: Loadout structural consistency verified independently of per-fact freshness
- **WHEN** evaluating loadout consistency where `baseline.anchored_loadout_revision == current_loadout.revision` but baseline Armour is marked `STALE`
- **THEN** the system confirms loadout structural consistency is intact while identifying Armour specifically as stale

#### Scenario: Conflicting character fact is treated as not known
- **WHEN** a character fact has `verification: CONFLICTING` due to contradictory API and manual evidence
- **THEN** the system evaluates `fact.is_known` as `False`, refusing to treat the conflicting value as authoritative

### Requirement: Decision-Relevant Fact Dependencies and Targeted Confidence Gating
The system SHALL determine decision-relevant fact dependencies (`RecommendationFactDependencies`) for every candidate evaluation. Only character facts materially impacted by the swap (candidate modifying local defense, movement speed, life, or resistances) or required for validation (attributes required by candidate, equipped items, or build-critical gems in requirement cascades) SHALL gate recommendation confidence.
If any decision-relevant fact has an unusable state (`STALE`, `UNKNOWN`, `CONFLICTING`), the system SHALL block confident `EQUIP_NOW` (`is_sufficient_for_equip_now: False`, `sufficiency: INSUFFICIENT_FOR_CONFIDENT_EQUIP`) and output explicit diagnostic reasons identifying the unproven fact and its state.
Unrelated stale facts SHALL NOT globally block recommendations or prevent `EQUIP_NOW` when evaluating candidates that do not depend on those facts.

#### Scenario: Stale Armour blocks candidate modifying local Armour
- **WHEN** candidate body armour changes local Armour while baseline Armour is marked `STALE`
- **THEN** the system determines that Armour is decision-relevant, sets `is_sufficient_for_equip_now: False`, blocks `EQUIP_NOW`, and outputs an explanation that baseline Armour is STALE

#### Scenario: Stale defenses do not block defense-independent candidate ring
- **WHEN** evaluating a candidate ring modifying only Life and Fire Resistance while baseline Armour, Evasion, and Energy Shield are `STALE`
- **THEN** the system determines defenses are not decision-relevant for the ring, confirms needed facts (Life, Fire Res) are fresh, and permits confident evaluation and `EQUIP_NOW`

#### Scenario: Conflicting attribute fact required by requirement cascade blocks confident equip
- **WHEN** a swap alters character attributes and an equipped gem requires Dexterity, but baseline Dexterity is marked `CONFLICTING`
- **THEN** the system identifies Dexterity as decision-relevant for cascade validation, blocks confident equip, and outputs a diagnostic reason citing conflicting Dexterity

### Requirement: Local Defense Regression Detection and Multidimensional Trade-off Semantics
The system SHALL detect local defense regressions (Armour, Evasion, Energy Shield) deterministically. If a candidate item produces a negative delta in any local defense category (`armour_delta < 0`, `evasion_delta < 0`, or `es_delta < 0`), or trades off one defense type for another (such as losing Armour while gaining Evasion), the system SHALL treat the defense reduction as an explicit regression. The system SHALL NOT mask local defense regressions behind Life gains, resistance increases, or scalar scores. Candidates with defense regressions SHALL NOT qualify for clean `EQUIP_NOW` via `DOMINANT_IMPROVEMENT`, `RESOLVES_DEFICIT`, or `IMPROVES_DEFICIT`; they SHALL evaluate to `MultidimensionalComparison.MIXED_TRADEOFF` and `Verdict.CONDITIONAL_UPGRADE` with `flags=["MIXED_TRADEOFF"]` and explicit trade-off explanations detailing the exact defense losses.

#### Scenario: Significant Armour drop with Life gain evaluates to CONDITIONAL_UPGRADE trade-off
- **WHEN** evaluating a candidate body armour with 0 Armour and +80 Life replacing an equipped body armour with 800 Armour on a character with 1000 baseline Armour
- **THEN** the system detects a negative Armour delta (-800), treats the trade-off as `MIXED_TRADEOFF`, and emits `Verdict.CONDITIONAL_UPGRADE` with `flags: ["MIXED_TRADEOFF"]` rather than `EQUIP_NOW`

#### Scenario: Trading Armour for Evasion evaluates as MIXED_TRADEOFF
- **WHEN** evaluating a candidate item that loses 400 Armour while gaining 300 Evasion
- **THEN** the system classifies the outcome as `MIXED_TRADEOFF` and advises the user of the defensive trade-off

#### Scenario: Clean upgrade with non-negative defense deltas qualifies for EQUIP_NOW
- **WHEN** evaluating a candidate item with non-negative defense deltas and positive Life/resistance improvements that resolve active deficits
- **THEN** the system does not trigger defense regression flags and allows clean evaluation to `Verdict.EQUIP_NOW`

### Requirement: Movement Speed Baseline Reconciliation and Preservation
During post-setup equipment mutation and baseline reconciliation (`reconcile_baseline_after_swap`), the system SHALL reconcile `movement_speed`. If `baseline.movement_speed.is_known`, the system SHALL compute the net movement speed delta:
$$\Delta \text{MS} = \text{candidate\_contribution.movement\_speed\_delta} - \sum \text{displaced\_contributions.movement\_speed\_delta}$$
and record the new value with `source: DERIVED_CALCULATION` and `verification: VERIFIED`.
If baseline movement speed has a value but is unproven (`STALE` or `CONFLICTING`), the system SHALL mark it `STALE`.
If movement speed was unobserved (`UNKNOWN`), it SHALL remain `UNKNOWN`. The system SHALL NOT fabricate movement speed values.

#### Scenario: Known baseline movement speed projects net candidate minus displaced delta
- **WHEN** baseline Movement Speed is known at 7%, displaced boots provide 10%, and candidate boots provide 25% (+15% net delta)
- **THEN** baseline reconciliation updates Movement Speed to 22% with `source: DERIVED_CALCULATION` and `verification: VERIFIED`

#### Scenario: Unproven baseline movement speed is marked stale on promotion
- **WHEN** baseline Movement Speed is already `STALE` and an item promotion alters Movement Speed
- **THEN** baseline reconciliation retains the fact as `STALE`, refusing to fabricate an authoritative absolute value

#### Scenario: Candidate changing movement speed against unknown baseline gates confidence
- **WHEN** evaluating candidate boots with +20% Movement Speed on a character whose baseline Movement Speed is `UNKNOWN`
- **THEN** data sufficiency flags Movement Speed as decision-relevant and unobserved, blocking confident `EQUIP_NOW`

### Requirement: Immutable Loadout Revision History Snapshots on Finalized Transitions
Whenever an established, finalized loadout transitions due to an equipment mutation (`companion gear loadout promote-candidate`, `set-clipboard`, `clear`), the system SHALL persist an immutable snapshot of revision $N$ in `runtime/loadout_history/{character_id}/rev_{N:06d}.json` before incrementing to revision $N+1$.
The system SHALL increment the revision exactly once per real change and SHALL attach a `LoadoutTransitionResult` containing `previous_revision`, `new_revision`, `is_finalized`, `is_changed`, and `history_snapshot_path`.
CLI promotion commands SHALL route through this authoritative wrapper, and stdout output SHALL accurately communicate transition state (e.g. indicating whether a revision increment occurred, whether existing baseline became stale, or whether the change occurred in a draft).

#### Scenario: Promoting candidate on finalized loadout creates history snapshot and advances revision
- **WHEN** running `companion gear loadout promote-candidate --slot boots` on a finalized loadout at revision 1
- **THEN** the system snapshots revision 1 to `runtime/loadout_history/{character_id}/rev_000001.json`, advances loadout revision to 2, and reports that the existing baseline is now stale

#### Scenario: Unchanged promotion creates no history snapshot and preserves revision
- **WHEN** promoting an identical candidate into a slot already occupied by that item
- **THEN** the system determines no change occurred, creates no history snapshot, keeps revision unchanged, and reports the slot was unchanged

#### Scenario: CLI displays state-accurate wording for finalized vs draft mutations
- **WHEN** mutating a slot in a draft loadout versus a finalized loadout
- **THEN** the CLI output states "updated in loadout draft" for draft mutations, and reports revision advancement "revision: N -> N+1" with baseline staleness warnings for finalized mutations
