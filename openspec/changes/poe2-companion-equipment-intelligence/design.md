# Design: PoE2 Equipment Intelligence & Gear Brain

## Context

The current PoE2 Companion repository provides character runtime state persistence (`companion.state`), progression stage tracking and Level-52 milestone evaluation (`companion.transition`), guide rule loading (`companion.rules`), and an official GGG API client with OAuth and circuit breaking (`companion.api`).

However, existing planning had critical gaps regarding character state availability, weapon set modeling, loadout ingestion, and modifier semantics:
1. **Character Stat Baseline Absence**: Official PoE2 API (`GET /character/poe2/<name>`) returns `equipment` (equipped items), `skills` (socketed gems), `passives`, and `quest_stats`. It does **not** expose a complete character-sheet stat block (Life, Resistances, Armour, Evasion, Energy Shield, total Attributes, Movement Speed). Furthermore, `CharacterState` today only stores stubbed/initialized defaults (`source="DEFAULT_INIT"`, `verification="UNKNOWN"`). The engine must not pretend official equipment data alone provides character-sheet values, and must never coerce missing facts to zero.
2. **Offline Current-Loadout Ingestion Void**: Without official API credentials, the V1 engine had no defined method for learning what items the character currently wears. The engine must provide a simple, passive manual loadout ingestion workflow via clipboard (`Ctrl+C`) for all shared slots and dual weapon sets.
3. **Loadout Provenance and Conflict Detection**: Equipment data can arrive from manual clipboard entry or official API sync. These sources must retain provenance (`CLIPBOARD_ITEM_TEXT`, `GGG_OFFICIAL_API`, `MANUAL`) and must never silently overwrite or merge contradictory data; conflicts must be marked `verification: CONFLICTING` and surfaced.
4. **Baseline vs Loadout-Derived Contribution Double-Counting**: Total character defenses entered manually (e.g. Armour = 4200) already incorporate equipped item defense. Summing equipped body armour defense (e.g. 850) back into baseline defense would double-count. Projections must cleanly differentiate total character baseline from item-specific contributions.
5. **Precise Fubgun 0.5.5 Fire Damage Rule & Staff Exception**: In Fubgun's Level-52+ post-swap build, the verified rule states: *"You cannot have flat fire damage or extra fire damage anywhere on your gear (the only exception is your staff)."* The underlying mechanical danger is that added or extra Fire damage applying to Oil Grenade (attacks) allows Oil Grenade itself to trigger an inferior ignite that blocks Flameblast's massive ignite. A simplistic weapon-only flat fire check misses dangerous shared rings and gloves while falsely rejecting the allowed Flameblast staff.
6. **Dual Weapon-Set Awareness**: Fubgun's build actively alternates between Flameblast (weapon set 1, staff) and Oil Grenade (weapon set 2, crossbow). Manual loadout ingestion and candidate evaluation must explicitly assign and evaluate items within designated weapon sets without guessing or relying on active set state.
7. **Local vs Global Modifier Semantics**: Local defense modifiers (e.g. `% increased Armour` on Body Armour) modify the item's displayed defense and must not be double-counted as global character multipliers.
8. **Official API Realities & Offline Core**: GGG developer documentation specifies that `inventory`, `rucksack`, and `GET /stash` are PoE1-only. Additionally, GGG currently has developer application registration unavailable. The V1 product must operate completely offline without API credentials.
9. **Baseline Anchoring & Post-Equip Mutation Hazard**: A character stat baseline represents observations made while wearing a specific loadout. If the loadout changes (via promotion or manual assignment) without tracking revisions, old baseline facts falsely purport to represent the new gear. Furthermore, non-linear stats like Armour cannot be trivially rebased without full engine math.
10. **Multi-Slot Occupancy & Two-Handed Weapon Handedness**: In Path of Exile 2, two-handed weapon classes such as Staves and Crossbows occupy both weapon hand slots (`main_hand` and `off_hand`). Equipping a two-handed weapon displaces both weapon hand slots in that set. The engine must not leave phantom shields or quivers equipped or fail to subtract off-hand attributes during requirement cascades.
11. **High-Risk Unknown Build-Breaker Uncertainty**: Candidate items with novel or unverified fire modifiers cannot be proven safe for Oil Grenade attack mechanics. Emitting a confident `EQUIP_NOW` for such items creates severe risk of breaking the build's primary ignite mechanic.
12. **Resistance Rebase Hazard (Capped Effective vs Raw Uncapped State)**: Additive resistance rebasing is mathematically valid only when the baseline being rebased is the raw uncapped resistance contribution. For example, if raw lightning resistance is 115, cap is 75, and effective resistance is 75, swapping an item from +40% to +10% yields new raw resistance of 85 ($115 - 40 + 10 = 85$) and effective resistance remains 75 ($\min(85, 75) = 75$). Rebasing directly from capped effective value ($75 - 40 + 10 = 45$) is incorrect and produces dangerous false alerts. The engine must explicitly distinguish `raw_uncapped_resistance`, `effective_resistance`, `max_resistance`, and `overcap_buffer`.
13. **Initial Setup vs Real Equipment Mutation Semantics**: During initial setup, the user describes equipment that was ALREADY worn when the character-sheet baseline was observed. Treating each initial slot entry as an in-game gear swap would prematurely increment revisions and trigger baseline reconciliation on an unestablished baseline. The workflow must establish the loadout draft first, finalize it (`companion gear loadout finalize`, establishing revision 1), and then anchor the manual character baseline to revision 1. Partial loadout must be supported with explicit known vs unknown slots.
14. **Generalized Slot Conflict Topology vs Universal Handedness**: In Path of Exile 2, two-handed weapon classes do not all share identical companion slot rules. While Bows uniquely permit an off-hand Quiver, Staves and Crossbows are both two-handed weapon classes that occupy both weapon slots (`main_hand` and `off_hand`), conflicting with both weapon slots and strictly disallowing off-hand accessories like quivers or shields. Quivers can only be equipped while wielding a Bow, never with a crossbow. Normalized base metadata grounded in verified game-item rules must specify actual slot-conflict topology (`occupied_slots`, `conflicting_slots`, `allowed_companion_slots`) rather than relying on generic guide text or hardcoding every two-handed weapon to identical behavior.

## Goals / Non-Goals

**Goals:**
- Introduce an authoritative `CharacterStatBaseline` / `CharacterFact` model with explicit provenance (`value`, `source`, `observed_at`, `verification`, `stale_after`, `evidence_ref`) where missing facts remain `UNKNOWN`, never zero.
- Explicitly distinguish `raw_uncapped_resistance`, `effective_resistance`, `max_resistance`, and `overcap_buffer` across all elemental and chaos resistances.
- Prohibit additive resistance rebasing directly against capped effective values; enforce Resistance Rebase Policy where raw state must be proven (raw uncapped known or effective + overcap buffer) to rebase, otherwise marking post-swap effective resistance `UNKNOWN` / `STALE` while reporting item deltas.
- Distinguish Initial Loadout Capture (draft) from Real Equipment Mutation; provide 3-step setup (draft capture -> finalize establishing `revision = 1` -> capture baseline anchored to revision 1).
- Support partial initial loadout, recording `known_slots` and `unknown_slots`, and lowering confidence when candidate evaluation targets an unknown current slot.
- Provide an explicit fresh baseline re-snapshot workflow (`companion gear baseline set` / `baseline refresh`) re-anchoring directly to current loadout revision as `VERIFIED` / `MANUAL`.
- Anchor `CharacterStatBaseline` to `EquippedLoadout` via monotonic `revision` numbers (`baseline.anchored_loadout_revision == loadout.revision`).
- Reconcile `CharacterStatBaseline` upon post-setup loadout mutation (`promote-candidate`, replacing established slot) with safe deterministic rebase (`DERIVED_CALCULATION`) for proven raw additive stats vs marking facts `STALE` / `UNKNOWN` for complex non-linear stats (Armour, Evasion, Energy Shield).
- Enforce a Baseline Consistency Gate before candidate evaluation: mismatched revisions prevent un-reconciled facts from being authoritative, while known item deltas continue to be computed and displayed.
- Strictly decouple candidate inspection / recommendations from state mutation: `inspect-clipboard`, `evaluate`, `compare`, `recommendation` are strictly read-only; only explicit user confirmation (`promote-candidate`) mutates loadout.
- Model generalized slot conflict topology (`occupied_slots`, `conflicting_slots`, `allowed_companion_slots`) and handedness (`SlotOccupancy`) using normalized item base metadata.
- Support weapon set projection: candidate weapons displace all verified conflicting slots in that set, leaving the opposing weapon set completely untouched; one-hand weapons replacing two-handed weapons leave the off-hand empty/unknown without fabricating gear.
- Provide occupancy-aware contribution removal: multi-slot replacements subtract contributions from ALL displaced items, recalculating Life, resistances, attributes, defense, and whole-loadout requirement cascades.
- Establish a tri-state build-breaker certainty model (`VERIFIED_SAFE`, `VERIFIED_BUILD_BREAKER`, `UNKNOWN_APPLICABILITY`).
- Enforce a High-Risk Unknown Build-Breaker Gate: modifiers with unverified applicability that could plausibly trigger oil-grenade ignite risk block confident `EQUIP_NOW`, emitting `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE` with `HIGH_RISK` warning.
- Enforce a deterministic non-scalar verdict precedence hierarchy: `VERIFIED_BUILD_BREAKER` -> `CRITICAL REQUIREMENT FAILURE` -> `UNKNOWN POTENTIAL BUILD-BREAKER` -> `NEW CRITICAL CHARACTER DEFICIENCY` -> Normal gear improvement.
- Support deterministic partial projection, separating `KNOWN DELTA` from `PROJECTED ABSOLUTE VALUE`.
- Establish an explicit Character-Stat Acquisition Plan with an expanded Field Availability Matrix and an explicit manual baseline CLI workflow (`companion gear baseline set`).
- Provide an explicit offline current-loadout ingestion workflow via clipboard (`companion gear loadout set-clipboard --slot <slot>`), loadout finalization (`companion gear loadout finalize`), inspection (`show`), clearing (`clear`), and candidate promotion (`promote-candidate`).
- Persist loadout entries with strict provenance and explicit conflict detection (`verification: CONFLICTING`).
- Strictly prevent double-counting between total character-sheet baseline defense and item-derived defense contributions during swap projections.
- Provide full two-weapon-set support in V1: `SHARED EQUIPMENT`, `WEAPON_SET_1` (Flameblast staff occupying both weapon hand slots), and `WEAPON_SET_2` (Oil Grenade crossbow occupying both weapon hand slots with zero quiver contribution), with explicit weapon set designation during ingestion and evaluation.
- Implement the exact Fubgun 0.5.5 fire damage rule modeling mechanical risk: shared gear with attack fire damage -> `HARD_REJECT`; weapon set 2 crossbow with fire damage -> `HARD_REJECT`; weapon set 1 staff -> verified exception (NOT rejected); benign Fire modifiers (`FIRE_RESISTANCE`, `% increased Fire Damage`) -> NOT rejected; unknown modifier applicability -> `UNKNOWN` / `HIGH_RISK`.
- Classify modifier scopes (`LOCAL_ITEM_STAT`, `GLOBAL_CHARACTER_STAT`, `REQUIREMENT`, `BUILD_MECHANIC`, `CONDITIONAL`, `UNKNOWN_SCOPE`) and prevent defense double-counting.
- Define a deterministic `ItemContribution` layer mediating all candidate and loadout stat deltas.
- Model dynamic resistance targets (`raw_uncapped_resistance`, `current_effective_resistance`, `current_max_resistance`, `target_resistance`, `overcap_buffer`) without inventing unverified campaign penalties.
- Implement whole-loadout requirement cascade validation across equipped items and build-critical gems upon attribute changes.
- Honestly gate official API capabilities (`UNAVAILABLE_BY_CURRENT_OFFICIAL_API` for inventory and stashes) and adhere to OAuth 2.1 public client specifications with registration freeze handling (`API_AVAILABLE`, `AUTH_CONFIGURED`, `AUTH_UNAVAILABLE`).
- Guarantee complete V1 Gear Brain functionality without official API credentials via clipboard ingestion and manual baseline.
- Maintain strict anti-automation compliance: zero simulated inputs, zero memory reading, zero automated gameplay actions.

**Non-Goals:**
- Automated passive tree pathfinding or gem link optimizers (gem requirements are validated only as requirement context).
- OCR or visual screen scraping in V1 core (clipboard candidate inspection is primary; visual panel captures remain optional auxiliary inputs).
- Automated inventory crawling via official API (unsupported by GGG PoE2 API).
- Fabricated Effective Health Pool (EHP) formulas (defenses are presented as explicit separate deltas).
- Game client automation, keystroke injection (`SendInput`), or automated gear swapping.

## Decisions

### Decision 1: Authoritative Character Stat Baseline & Provenance Handling
- **Approach**: Model character stats via `CharacterStatBaseline` containing provenanced `CharacterFact[T]` instances.
  - Allowed sources: `EXISTING_CHARACTER_STATE`, `GGG_OFFICIAL_API`, `DERIVED_FROM_VERIFIED_COMPONENTS`, `DERIVED_CALCULATION`, `MANUAL_USER_INPUT`, `MANUAL_SNAPSHOT`, `UNKNOWN`.
  - Allowed verification states: `VERIFIED`, `CORROBORATED`, `SINGLE_SOURCE`, `STALE`, `UNKNOWN`, `CONFLICTING`.
  - Invariant: When a character-sheet stat is unobserved or unproven, `value = UNKNOWN` (represented as `None` with `verification_state = UNKNOWN`). The engine strictly forbids converting missing stats to `0` or `0%`.
- **Rationale**: In PoE2, resistances can be negative (-60% or lower) or positive (75%+). Treating missing stats as 0 is mathematically wrong and dangerously misleads defensive evaluation.
- **Alternatives Rejected**:
  - *Coercing missing values to 0*: Falsely triggers massive deficit warnings or falsely assumes zero resistance.
  - *Heuristic stat estimation*: Guessing stats from character level or passives alone produces inaccurate verdicts.

### Decision 2: Initial Setup Workflow, Loadout Finalization, and Revision Anchoring
- **Approach**:
  - Strictly distinguish **INITIAL LOADOUT CAPTURE** from **REAL EQUIPMENT MUTATION**. During initial setup, the user is describing equipment that was ALREADY equipped when the character-sheet baseline was observed.
  - **Preferred Initial Setup Order (3-Step V1 Workflow)**:
    1. *Step A: Capture Current Loadout First (Draft)*: The user manually captures all known currently equipped items (`shared_slots`, `weapon_set_1`, `weapon_set_2`) via `companion gear loadout set-clipboard --slot <slot>`. These populate a setup/loadout draft without simulating gear swaps and without incrementing revisions.
    2. *Step B: Finalize Current Loadout*: The user runs `companion gear loadout finalize`. Finalization transitions the loadout to finalized status, assigns `loadout_id`, initializes stable `revision = 1`, and records `known_slots` and `unknown_slots`.
    3. *Step C: Capture Character Baseline*: Only AFTER the loadout is finalized, the user captures character stats via `companion gear baseline set ...`. The baseline is anchored to `revision = 1` (`anchored_loadout_revision = 1`), guaranteeing that character-sheet numbers and stored gear describe the same equipment state.
  - **Partial Initial Loadout Handling**:
    - The engine does not require every slot to be known. Unobserved slots remain `UNKNOWN`.
    - Finalization is permitted with a partial loadout, recording `known_slots`, `unknown_slots`, and verification state.
    - Gear Brain lowers confidence when a candidate projection depends on an unknown displaced item (e.g. current boots `UNKNOWN`, candidate boots known -> engine describes candidate properties, but cannot claim an exact net boots delta).
  - **Explicit Re-Snapshot / Rebase Workflow**:
    - The user can refresh the baseline at any time via `companion gear baseline set ...` or `companion gear baseline refresh`.
    - The fresh manual baseline becomes `VERIFIED` / `MANUAL` and anchors directly to the current `loadout.revision`, replacing long chains of derived baseline values with a fresh authoritative snapshot.
- **Rationale**: Character-sheet observations are only valid for the exact items worn at observation time. Ingesting existing items must not trigger false mutation reconciliation. Finalizing before baseline capture guarantees synchronization.

### Decision 3: Post-Setup Loadout Mutation & Safe Baseline Reconciliation (Resistance Rebase Policy)
- **Approach**:
  - Following initial loadout finalization, commands that execute real equipment changes increment `loadout.revision` ($N \to N+1$):
    - `companion gear loadout promote-candidate --slot <slot>`
    - explicit replacement of an established current slot via `companion gear loadout set-clipboard --slot <slot>`
  - The engine then immediately reconciles `CharacterStatBaseline`:
    - **Outcome A: Safe Resistance Rebase Policy (Raw vs Effective)**:
      - The engine strictly refuses to perform additive item rebasing directly against a capped effective resistance value.
      - Safe deterministic resistance rebase is permitted ONLY when enough information exists to reconstruct the raw state: either `raw_uncapped_resistance` is known, OR `effective_resistance` plus a verified `overcap_buffer` is sufficient to reconstruct it.
      - When raw state is proven:
        $$\text{new\_raw} = \text{old\_raw} - \text{displaced\_item\_contribution} + \text{candidate\_contribution}$$
        $$\text{new\_effective} = \min(\text{new\_raw}, \text{verified\_current\_max\_resistance})$$
      - If raw state cannot be proven (e.g. effective is 75% but raw uncapped resistance and overcap buffer are `UNKNOWN`):
        - Report the known item resistance delta (e.g. `-30% Lightning Resistance`).
        - Mark the new absolute effective resistance as `UNKNOWN` / `STALE`.
        - Refuse to fabricate an unverified absolute value.
    - **Outcome B: Linear Attributes Rebase**:
      - For linear attributes (Strength, Dexterity, Intelligence):
        $$\text{new\_stat} = \text{old\_verified\_stat} - \text{old\_item\_contrib} + \text{new\_item\_contrib}$$
        Set `source = BaselineSource.DERIVED_CALCULATION`.
    - **Outcome C: Mark Complex Defenses Stale / Unknown**:
      - For complex, non-linear stats subject to passives, global scaling, or unmodeled interactions (total Armour, Evasion, Energy Shield, Life scaling):
        - Mark `verification = VerificationState.STALE`.
        - Refuse to fabricate a projected total Armour (e.g. do not guess $4200 - 850 + 1050 = 4400$).
        - Surface notice to the user: *"Equipped loadout updated. Run `companion gear baseline set` or take a panel snapshot to refresh total character Armour."*
- **Rationale**: Additive rebasing against capped values creates severe mathematical distortion (e.g. 115% raw losing 30% res remains 75% effective, not 45%). Safe rebase requires raw uncapped state.

### Decision 4: Baseline Consistency Gate
- **Approach**:
  - Before `EquipmentIntelligenceEngine` evaluates a candidate item, it executes the consistency gate:
    ```python
    if baseline.anchored_loadout_revision != current_loadout.revision:
        for fact in baseline.affected_unreconciled_facts():
            fact.mark_stale()
    ```
  - If a fact is marked `STALE` or `UNKNOWN`:
    - The engine refuses to use it as an authoritative current character stat.
    - The engine refuses to assert projected absolute character values (e.g. `75% -> 47%`).
    - The engine continues to compute and report deterministic equipment-level deltas (e.g. `-28% Fire Resistance`).
    - Verdict defaults to `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE` with identified risk.
- **Rationale**: Prevents stale character baselines from misleading upgrade recommendations while maintaining helpful equipment delta information.

### Decision 5: Recommendation Generation Must Not Mutate Current State
- **Approach**:
  - Candidate inspection and comparison commands (`companion gear inspect-clipboard`, `companion gear evaluate`, `compare`, `recommendation`) are strictly read-only.
  - Generating an `EQUIP_NOW` recommendation does NOT increment `loadout.revision` and does NOT modify `loadout.json`.
  - Only an explicit user action (`companion gear loadout promote-candidate`) confirms that the item was equipped in-game and triggers state mutation.
- **Rationale**: An agent or engine recommendation is an advisory hypothesis, not an observation of reality. Equipping an item in PoE2 is a human gameplay action.

### Decision 6: Generalized Slot Conflict Topology & Handedness Modeling
- **Approach**:
  - Rather than deriving weapon occupancy from build guides alone or universally assuming two-handed weapons share identical exception rules, normalized base metadata exposes actual slot-conflict topology grounded in verified PoE2 game-item rules:
    ```python
    class SlotConflictTopology(BaseModel):
        occupied_slots: list[SlotType]
        conflicting_slots: list[SlotType] = Field(default_factory=list)
        allowed_companion_slots: list[SlotType] = Field(default_factory=list)
        is_known: bool = True
    ```
  - **Verified PoE2 Rules**:
    - **Staves**: Two-Handed; occupy both weapon slots (`main_hand` and `off_hand`).
    - **Crossbows**: Two-Handed; occupy both weapon slots (`main_hand` and `off_hand`).
    - **Quivers**: Off-hand accessory that can ONLY be equipped while wielding a **Bow**, never with a crossbow.
  - **Verified Fubgun 0.5.5 Profile Loadout**:
    - **Flameblast staff**:
      - `occupied_slots`: `[weapon_set_1.main_hand, weapon_set_1.off_hand]`
      - `conflicting_slots`: `[weapon_set_1.main_hand, weapon_set_1.off_hand]` (both weapon slots in Set 1)
      - `allowed_companion_slots`: `[]`
    - **Oil Grenade crossbow**:
      - `occupied_slots`: `[weapon_set_2.main_hand, weapon_set_2.off_hand]`
      - `conflicting_slots`: `[weapon_set_2.main_hand, weapon_set_2.off_hand]` (both weapon slots in Set 2)
      - `allowed_companion_slots`: `[]`
    - There is **no quiver contribution** in the Fubgun crossbow set.
  - **Generic Extensibility**:
    - Keep topology metadata generic for other future item classes: Bows may declare `allowed_companion_slots: [SlotType.OFF_HAND]` for quivers, but that is NOT part of the Fubgun V1 equipment profile.
    - If base metadata or topology is unrecognized, it remains `UNKNOWN_TOPOLOGY` (`is_known = False`), which blocks confident full projection.

### Decision 7: Weapon Projection & Multi-Slot Displacement
- **Approach**:
  - When evaluating a candidate weapon targeting a weapon set:
    - Projected topology in target set: assigns candidate to target slot, and removes all verified conflicting slots in that same set.
    - Displaced items: all equipped items in the target slot and any conflicting slots.
    - **Crossbow Candidate in Weapon Set 2**:
      - Replaces the current crossbow in Set 2.
      - Owns both hand slots in Set 2 (`main_hand` and `off_hand`).
      - Has no off-hand quiver contribution (do not subtract or preserve a fictional quiver).
      - Does not affect `weapon_set_1`.
    - **Staff Candidate in Weapon Set 1**:
      - Replaces the current staff in Set 1.
      - Owns both hand slots in Set 1 (`main_hand` and `off_hand`).
      - Does not affect `weapon_set_2`.
    - Opposing weapon set remains 100% untouched.
  - When evaluating a candidate one-handed weapon replacing a two-handed staff:
    - Projected Set 1 topology: `main_hand`: candidate one-handed item; `off_hand`: empty (`None`).
    - The engine strictly refuses to fabricate or assume an off-hand item; an unequipped off-hand slot remains empty.
  - Shared equipment (Body, Rings, etc.) is evaluated uniformly across both weapon set contexts.

### Decision 8: Multi-Slot Occupancy-Aware Contribution & Requirement Cascades
- **Approach**:
  - When projecting a multi-slot displacement (such as equipping a two-handed staff displacing a 1H wand and a shield):
    - Replaced item contributions:
      $$C_{\text{displaced}} = C_{\text{main\_hand}} + C_{\text{off\_hand}}$$
    - Net delta:
      $$\Delta = C_{\text{candidate}} - C_{\text{displaced}}$$
    - The engine subtracts resistances, attributes, Life, and local defense of BOTH displaced items.
    - Requirement cascade re-evaluates all remaining equipped items and socketed gems against projected attributes.
    - If the removed shield provided +25 Dexterity and dropping that Dexterity causes an equipped crossbow or gem to fail its requirement, the engine catches the deficiency immediately and downgrades the verdict to `CONDITIONAL_UPGRADE` or `REJECT`.

### Decision 9: Build-Breaker Certainty Model & High-Risk Unknown Gate
- **Approach**:
  - Tri-state classification for build-breaking modifiers:
    ```python
    class BuildBreakerCertainty(str, Enum):
        VERIFIED_SAFE = "VERIFIED_SAFE"
        VERIFIED_BUILD_BREAKER = "VERIFIED_BUILD_BREAKER"
        UNKNOWN_APPLICABILITY = "UNKNOWN_APPLICABILITY"
    ```
  - **Classification Rules for Fubgun Post-Swap Build**:
    - `VERIFIED_BUILD_BREAKER`:
      - Post-swap shared gear (rings, gloves, amulet, belt, helm, body, boots) with flat Fire to attacks (`Adds X to Y Fire Damage to Attacks`) or verified Extra Fire to attacks.
      - Weapon Set 2 crossbow with flat or extra Fire damage (quivers cannot be equipped with crossbows and are not part of Fubgun loadout).
      - Action: Triggers `HARD_REJECT` -> Verdict `REJECT`.
    - `VERIFIED_SAFE`:
      - `FIRE_RESISTANCE` (defensive).
      - `INCREASED_FIRE_DAMAGE` (% increase does not add flat fire to base physical attacks).
      - `FIRE_SPELL_LEVEL` / Gem affixes.
      - Weapon Set 1 Flameblast staff fire modifiers (verified staff exception).
      - Action: Normal upgrade evaluation.
    - `UNKNOWN_APPLICABILITY`:
      - Novel or ambiguous Fire modifier where applicability to Oil Grenade attacks cannot be proven from evidence (e.g. conditional flat fire, unmodeled trigger fire, novel PoE2 affixes).
      - Action: **HIGH-RISK UNKNOWN GATE**:
        - Engine MUST NOT emit `EQUIP_NOW`.
        - Permitted conservative outcomes: `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE` with explicit `HIGH_RISK: Fire modifier applicability to Oil Grenade unverified` warning.
        - Engine refuses to fabricate an unsubstantiated `HARD_REJECT` and refuses to ignore the risk.

### Decision 10: Deterministic Non-Scalar Verdict Precedence
- **Approach**:
  - Recommendations are decided through an auditable, deterministic 5-tier evaluation hierarchy:
    ```
    Tier 1: VERIFIED_BUILD_BREAKER?
      └── YES ──> REJECT (hard stop)
      └── NO  ──> Proceed to Tier 2

    Tier 2: CRITICAL_REQUIREMENT_FAILURE? (candidate, equipped gear, or gems fail stat requirements)
      └── YES ──> REJECT (if unrecoverable) or CONDITIONAL_UPGRADE (prerequisites: acquire X attributes)
      └── NO  ──> Proceed to Tier 3

    Tier 3: UNKNOWN_POTENTIAL_BUILD_BREAKER? (UNKNOWN_APPLICABILITY on critical mechanic)
      └── YES ──> BLOCKS confident EQUIP_NOW ──> INSUFFICIENT_DATA or CONDITIONAL_UPGRADE (HIGH_RISK)
      └── NO  ──> Proceed to Tier 4

    Tier 4: NEW_CRITICAL_CHARACTER_DEFICIENCY? (unmitigated drop below target resistance or Life)
      └── YES ──> CONDITIONAL_UPGRADE or REJECT
      └── NO  ──> Proceed to Tier 5

    Tier 5: NORMAL_GEAR_IMPROVEMENT?
      ├── Significant net upgrade with safe trade-offs ──> EQUIP_NOW
      ├── Upgrade with minor trade-offs ────────────────> CONDITIONAL_UPGRADE
      ├── Sidegrade / stash potential ──────────────────> KEEP_FOR_LATER
      └── Strict downgrade ─────────────────────────────> REJECT
    ```
  - Under no circumstances is this decision sequence collapsed into a scalar score.

### Decision 11: Field Availability Matrix & Expanded Manual Baseline Workflow
- **Approach**: Maintain the authoritative field availability matrix across all defensive, attribute, and mobility stats:

| Stat | Current Source in Repo | Exact / Derived / Unknown | Refresh Method | Confidence / Verification |
| :--- | :--- | :--- | :--- | :--- |
| **Character Level** | `CharacterState.level` / Official API | Exact | API Sync / Client Log | `VERIFIED` |
| **Current Zone / Act** | `CharacterState.current_zone` / Log | Exact | Log Parser | `VERIFIED` |
| **Equipped Items** | Official API (`OfficialCharacterData.equipment`) | Exact | OAuth API / Manual Snapshot | `VERIFIED` (if authed) |
| **Life** | None in `CharacterState` root (only optional vision) | **UNKNOWN** | Manual Baseline / Vision Snapshot | `UNKNOWN` (unless manual/vision) |
| **Armour** | None in `CharacterState` root (only optional vision) | **UNKNOWN** | Manual Baseline / Vision Snapshot | `UNKNOWN` (unless manual/vision) |
| **Evasion** | None in `CharacterState` root (only optional vision) | **UNKNOWN** | Manual Baseline / Vision Snapshot | `UNKNOWN` (unless manual/vision) |
| **Energy Shield** | None in `CharacterState` root | **UNKNOWN** | Manual Baseline / Vision Snapshot | `UNKNOWN` (unless manual/vision) |
| **Fire Resistance** | `CharacterState.resistances["fire"]` (defaults 0) | **UNKNOWN** | Manual Baseline / Vision Snapshot | `UNKNOWN` (default init) |
| **Cold Resistance** | `CharacterState.resistances["cold"]` (defaults 0) | **UNKNOWN** | Manual Baseline / Vision Snapshot | `UNKNOWN` (default init) |
| **Lightning Res** | `CharacterState.resistances["lightning"]` (defaults 0) | **UNKNOWN** | Manual Baseline / Vision Snapshot | `UNKNOWN` (default init) |
| **Chaos Resistance** | `CharacterState.resistances["chaos"]` (defaults 0) | **UNKNOWN** | Manual Baseline / Vision Snapshot | `UNKNOWN` (default init) |
| **Strength** | `CharacterState.attributes["strength"]` (defaults 10) | **UNKNOWN** | Manual Baseline / Loadout Derived | `UNKNOWN` (default init) |
| **Dexterity** | `CharacterState.attributes["dexterity"]` (defaults 10) | **UNKNOWN** | Manual Baseline / Loadout Derived | `UNKNOWN` (default init) |
| **Intelligence** | `CharacterState.attributes["intelligence"]` (defaults 10) | **UNKNOWN** | Manual Baseline / Loadout Derived | `UNKNOWN` (default init) |
| **Movement Speed** | None in `CharacterState` root | **UNKNOWN** | Manual Baseline / Loadout Derived | `UNKNOWN` (unless boots parsed) |
| **Max Fire Res** | Default 75% | Derived | Manual Baseline / Passive Calc | `VERIFIED` (or modified) |
| **Max Cold Res** | Default 75% | Derived | Manual Baseline / Passive Calc | `VERIFIED` (or modified) |
| **Max Lightning Res** | Default 75% | Derived | Manual Baseline / Passive Calc | `VERIFIED` (or modified) |
| **Max Chaos Res** | Default 75% | Derived | Manual Baseline / Passive Calc | `VERIFIED` (or modified) |

- **Expanded Manual Baseline CLI**: Command `companion gear baseline set` accepts optional flags:
  ```bash
  companion gear baseline set \
    --life 1500 \
    --fire-res 75 \
    --cold-res 72 \
    --lightning-res 68 \
    --chaos-res -10 \
    --armour 4200 \
    --evasion 1100 \
    --energy-shield 0 \
    --str 120 \
    --dex 95 \
    --int 180 \
    --movement-speed 15 \
    --max-fire-res 78
  ```
  Every parameter is optional. Omitted parameters remain `UNKNOWN`.

### Decision 12: Baseline vs Loadout-Derived Contribution Double-Count Protection
- **Approach**: Maintain strict boundaries between total character-sheet stats and item contributions:
  1. *Character-Sheet Baseline Total* ($S_{\text{baseline}}$): The full character stat reported by the user (e.g. Armour = 4200). It already incorporates the character's base attributes, passives, and equipped item defense.
  2. *Equipped Item Contribution* ($C_{\text{equipped}}$): The local defense or stat contributed by the currently equipped item (e.g. Body Armour = 850 local Armour).
  3. *Candidate Item Contribution* ($C_{\text{candidate}}$): The local defense or stat contributed by the candidate item (e.g. candidate Body Armour = 1050 local Armour).
- **Double-Counting Prevention Invariant**:
  - The engine SHALL NOT sum $S_{\text{baseline}} + C_{\text{equipped}}$ when establishing current state. Doing so would count the body armour twice.
  - When evaluating a candidate replacement:
    $$\Delta \text{Local} = C_{\text{candidate}} - C_{\text{equipped}}$$
    $$S_{\text{projected}} = S_{\text{baseline}} + \Delta \text{Local} \quad \text{(when linear contribution semantics are valid)}$$
  - If complex global multipliers (e.g. global `% increased Armour` from passives or buffs) make absolute projection unsafe without full tree simulation, the engine reports the deterministic local delta ($\Delta = +200 \text{ local Armour}$) and explicitly reduces confidence rather than fabricating an absolute total.

### Decision 13: Offline Manual Current-Loadout Ingestion via Clipboard
- **Approach**: Provide a completely offline, passive workflow for capturing the player's currently equipped gear:
  1. User hovers their equipped item in the PoE2 game window.
  2. User manually presses `Ctrl+C` (PoE2 copies standard item text to clipboard).
  3. User runs companion command specifying the slot:
     ```bash
     companion gear loadout set-clipboard --slot boots
     companion gear loadout set-clipboard --slot ring1
     companion gear loadout set-clipboard --slot ring2
     companion gear loadout set-clipboard --slot amulet
     companion gear loadout set-clipboard --slot weapon-set-1-main
     companion gear loadout set-clipboard --slot weapon-set-1-off
     companion gear loadout set-clipboard --slot weapon-set-2-main
     companion gear loadout set-clipboard --slot weapon-set-2-off
     ```
  4. Companion reads clipboard text, parses it into `ItemCandidate`, validates slot compatibility, and saves it into `EquippedLoadout`.
  5. Companion provides:
     - `companion gear loadout show`: Displays full equipped loadout across shared slots and both weapon sets with timestamps and verification states.
     - `companion gear loadout clear <slot>`: Clears a specific slot if unequipped.
     - `companion gear loadout promote-candidate`: Explicitly promotes an evaluated candidate item into the equipped slot. Generating recommendations never mutates loadout.
- **Safety**: 100% passive, zero keystrokes injected into the game client.

### Decision 14: Loadout Storage, Provenance, and Conflict Detection
- **Approach**: Persist loadout in a structured local file (`loadout.json`) where every slot is an `EquippedSlotEntry`:
  ```python
  class EquippedSlotEntry(BaseModel):
      item: ItemCandidate
      slot: SlotType
      weapon_set: WeaponSetContext | None = None
      source: BaselineSource  # CLIPBOARD_ITEM_TEXT, GGG_OFFICIAL_API, MANUAL
      observed_at: str
      verification: VerificationState
      evidence_ref: str | None = None
      stale_after: str | None = None
  ```
- **Conflict Handling Invariant**:
  - If official API synchronization returns an item that differs from the manually ingested clipboard item for the same slot:
    - The engine sets `verification = VerificationState.CONFLICTING`.
    - Both evidence hashes are retained.
    - The engine surfaces the conflict to the user: *"Slot ring1 has conflicting manual and API data. Run `companion gear loadout show` or re-ingest to resolve."*
    - The engine refuses to guess which source is correct.

### Decision 15: Local vs Global Modifier Semantics & Double-Counting Prevention
- **Approach**: Tag each modifier with `ModifierScope`:
  - `LOCAL_ITEM_STAT`: Affects item properties only (e.g. `% increased Armour` on Body Armour, local flat physical damage on weapons).
  - `GLOBAL_CHARACTER_STAT`: Character-wide stat (e.g. elemental resistances, maximum Life, global attributes, global cast speed).
  - `REQUIREMENT`: Required level and attributes.
  - `BUILD_MECHANIC`: Affixes affecting specific build mechanics (e.g. ignite chance, added fire damage).
  - `CONDITIONAL`: Trigger- or condition-bound stats.
  - `UNKNOWN_SCOPE`: Unmodeled modifiers, isolated for audit.
- **Double-Counting Rule**:
  - The displayed Armour, Evasion, or Energy Shield on an item represents the final local value already calculated by the game.
  - When calculating character defense deltas, the engine uses the displayed item defense as the local contribution.
  - Modifiers categorized as `LOCAL_ITEM_STAT` contributing to local defense are **not** added again to the character's global defense modifiers.

### Decision 16: Dynamic Resistance Limits & Target Modeling
- **Approach**:
  - Model `current_effective_resistance`, `current_max_resistance`, `target_resistance`, and `overcap_buffer`.
  - Default target is 75%, but if character passives/gear provide +max resistance (e.g. max Fire Res = 78%), `target_resistance` and overcap calculations dynamically adjust to 78%.
  - Distinguish effective capped resistance ($\min(\text{raw}, \text{max})$) from overcap buffer ($\max(0, \text{raw} - \text{max})$).
  - Campaign resistance penalties (-20% / -40% in progression) are only applied when verified by explicit progression context. Otherwise, absolute resistance is marked `UNKNOWN` while known equipment deltas remain exact.

### Decision 17: Official API Capability Gating & OAuth 2.1 Specification
- **Approach**:
  - Document capabilities honestly:
    - `GET /character/poe2/<name>`: Equipment, Skills, Passives, Quest Stats (`AVAILABLE`).
    - Character inventory & rucksack: `UNAVAILABLE_BY_CURRENT_OFFICIAL_API` (PoE1 only).
    - Account Stashes (`GET /stash`): `UNAVAILABLE_BY_CURRENT_OFFICIAL_API` (PoE1 only).
  - OAuth Specification: Adhere to OAuth 2.1 Public Client standard (Authorization Code + PKCE S256, localhost redirect).
  - External Prerequisite Limitation: Record that GGG developer documentation states new application registration is unavailable.
  - Feature Gating: Maintain three clean states: `API_AVAILABLE`, `AUTH_CONFIGURED`, `AUTH_UNAVAILABLE`.
  - Offline V1 Workflow: Core Gear Brain functions 100% offline without API credentials using manual baseline and clipboard inspection (`companion gear inspect-clipboard`).

## Data Models

```python
class BaselineSource(str, Enum):
    EXISTING_CHARACTER_STATE = "EXISTING_CHARACTER_STATE"
    GGG_OFFICIAL_API = "GGG_OFFICIAL_API"
    DERIVED_FROM_VERIFIED_COMPONENTS = "DERIVED_FROM_VERIFIED_COMPONENTS"
    DERIVED_CALCULATION = "DERIVED_CALCULATION"
    MANUAL_USER_INPUT = "MANUAL_USER_INPUT"
    MANUAL_SNAPSHOT = "MANUAL_SNAPSHOT"
    CLIPBOARD_ITEM_TEXT = "CLIPBOARD_ITEM_TEXT"
    UNKNOWN = "UNKNOWN"

class CharacterFact(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)
    value: T | None  # None indicates UNKNOWN
    source: BaselineSource
    observed_at: str
    verification: VerificationState
    stale_after: str | None = None
    evidence_ref: str | None = None

    @property
    def is_known(self) -> bool:
        return self.value is not None and self.verification != VerificationState.UNKNOWN

class CharacterStatBaseline(BaseModel):
    baseline_id: str
    character_id: str
    anchored_loadout_revision: int
    life: CharacterFact[int]
    armour: CharacterFact[int]
    evasion: CharacterFact[int]
    energy_shield: CharacterFact[int]
    raw_fire_res: CharacterFact[int]
    effective_fire_res: CharacterFact[int]
    max_fire_res: CharacterFact[int] = Field(default_factory=lambda: CharacterFact(value=None, source=BaselineSource.UNKNOWN, observed_at="", verification=VerificationState.UNKNOWN))
    fire_overcap_buffer: CharacterFact[int]
    raw_cold_res: CharacterFact[int]
    effective_cold_res: CharacterFact[int]
    max_cold_res: CharacterFact[int] = Field(default_factory=lambda: CharacterFact(value=None, source=BaselineSource.UNKNOWN, observed_at="", verification=VerificationState.UNKNOWN))
    cold_overcap_buffer: CharacterFact[int]
    raw_lightning_res: CharacterFact[int]
    effective_lightning_res: CharacterFact[int]
    max_lightning_res: CharacterFact[int] = Field(default_factory=lambda: CharacterFact(value=None, source=BaselineSource.UNKNOWN, observed_at="", verification=VerificationState.UNKNOWN))
    lightning_overcap_buffer: CharacterFact[int]
    raw_chaos_res: CharacterFact[int]
    effective_chaos_res: CharacterFact[int]
    max_chaos_res: CharacterFact[int] = Field(default_factory=lambda: CharacterFact(value=None, source=BaselineSource.UNKNOWN, observed_at="", verification=VerificationState.UNKNOWN))
    chaos_overcap_buffer: CharacterFact[int]
    strength: CharacterFact[int]
    dexterity: CharacterFact[int]
    intelligence: CharacterFact[int]
    movement_speed: CharacterFact[int]
    observed_at: str
    updated_at: str

class SlotOccupancy(str, Enum):
    SINGLE_SLOT = "SINGLE_SLOT"
    MAIN_HAND = "MAIN_HAND"
    OFF_HAND = "OFF_HAND"
    TWO_HAND = "TWO_HAND"
    SHARED_EQUIPMENT_SLOT = "SHARED_EQUIPMENT_SLOT"
    UNKNOWN_OCCUPANCY = "UNKNOWN_OCCUPANCY"

class SlotConflictTopology(BaseModel):
    occupied_slots: list[SlotType]
    conflicting_slots: list[SlotType] = Field(default_factory=list)
    allowed_companion_slots: list[SlotType] = Field(default_factory=list)
    is_known: bool = True

class ModifierScope(str, Enum):
    LOCAL_ITEM_STAT = "LOCAL_ITEM_STAT"
    GLOBAL_CHARACTER_STAT = "GLOBAL_CHARACTER_STAT"
    REQUIREMENT = "REQUIREMENT"
    BUILD_MECHANIC = "BUILD_MECHANIC"
    CONDITIONAL = "CONDITIONAL"
    UNKNOWN_SCOPE = "UNKNOWN_SCOPE"

class NormalizedModifierType(str, Enum):
    MAXIMUM_LIFE = "MAXIMUM_LIFE"
    FIRE_RESISTANCE = "FIRE_RESISTANCE"
    COLD_RESISTANCE = "COLD_RESISTANCE"
    LIGHTNING_RESISTANCE = "LIGHTNING_RESISTANCE"
    CHAOS_RESISTANCE = "CHAOS_RESISTANCE"
    LOCAL_ARMOUR = "LOCAL_ARMOUR"
    LOCAL_EVASION = "LOCAL_EVASION"
    LOCAL_ENERGY_SHIELD = "LOCAL_ENERGY_SHIELD"
    MOVEMENT_SPEED = "MOVEMENT_SPEED"
    STRENGTH = "STRENGTH"
    DEXTERITY = "DEXTERITY"
    INTELLIGENCE = "INTELLIGENCE"
    FLAT_FIRE_DAMAGE_ATTACK = "FLAT_FIRE_DAMAGE_ATTACK"
    FLAT_FIRE_DAMAGE_SPELL = "FLAT_FIRE_DAMAGE_SPELL"
    EXTRA_FIRE_DAMAGE = "EXTRA_FIRE_DAMAGE"
    INCREASED_FIRE_DAMAGE = "INCREASED_FIRE_DAMAGE"
    FIRE_SPELL_LEVEL = "FIRE_SPELL_LEVEL"
    ALL_SPELL_LEVEL = "ALL_SPELL_LEVEL"
    UNKNOWN_MODIFIER = "UNKNOWN_MODIFIER"

class NormalizedModifier(BaseModel):
    modifier_type: NormalizedModifierType
    scope: ModifierScope
    value: float
    raw_text: str
    is_implicit: bool = False
    verification_state: VerificationState = VerificationState.VERIFIED

class ItemCandidate(BaseModel):
    item_id: str
    name: str
    base_type: str
    slot: SlotType
    slot_occupancy: SlotOccupancy = SlotOccupancy.SINGLE_SLOT
    slot_conflict_topology: SlotConflictTopology = Field(default_factory=lambda: SlotConflictTopology(occupied_slots=[]))
    rarity: str
    item_level: int | None = None
    required_level: int = 1
    required_str: int = 0
    required_dex: int = 0
    required_int: int = 0
    local_armour: int = 0
    local_evasion: int = 0
    local_energy_shield: int = 0
    modifiers: list[NormalizedModifier] = Field(default_factory=list)
    raw_text: str

class ItemContribution(BaseModel):
    item_id: str
    slot: SlotType
    slot_occupancy: SlotOccupancy = SlotOccupancy.SINGLE_SLOT
    slot_conflict_topology: SlotConflictTopology = Field(default_factory=lambda: SlotConflictTopology(occupied_slots=[]))
    target_weapon_set: WeaponSetContext | None = None
    life_delta: float = 0.0
    fire_res_delta: float = 0.0
    cold_res_delta: float = 0.0
    lightning_res_delta: float = 0.0
    chaos_res_delta: float = 0.0
    str_delta: int = 0
    dex_delta: int = 0
    int_delta: int = 0
    movement_speed_delta: float = 0.0
    local_armour: int = 0
    local_evasion: int = 0
    local_energy_shield: int = 0
    global_modifiers: list[NormalizedModifier] = Field(default_factory=list)
    weapon_set_modifiers: list[NormalizedModifier] = Field(default_factory=list)
    build_mechanic_modifiers: list[NormalizedModifier] = Field(default_factory=list)
    unknown_modifiers: list[NormalizedModifier] = Field(default_factory=list)

class EquippedSlotEntry(BaseModel):
    item: ItemCandidate
    slot: SlotType
    weapon_set: WeaponSetContext | None = None
    source: BaselineSource
    observed_at: str
    verification: VerificationState
    evidence_ref: str | None = None
    stale_after: str | None = None

class EquippedLoadout(BaseModel):
    loadout_id: str
    character_id: str
    revision: int = 1
    is_finalized: bool = False
    known_slots: list[SlotType] = Field(default_factory=list)
    unknown_slots: list[SlotType] = Field(default_factory=list)
    shared_slots: dict[SlotType, EquippedSlotEntry | None] = Field(default_factory=dict)
    weapon_set_1: dict[SlotType, EquippedSlotEntry | None] = Field(default_factory=dict)
    weapon_set_2: dict[SlotType, EquippedSlotEntry | None] = Field(default_factory=dict)
    active_weapon_set: int = 1
    updated_at: str

class RequirementCascadeResult(BaseModel):
    candidate_valid: bool
    broken_equipment_slots: list[SlotType] = Field(default_factory=list)
    broken_skills: list[str] = Field(default_factory=list)
    details: list[str] = Field(default_factory=list)

class BuildBreakerCertainty(str, Enum):
    VERIFIED_SAFE = "VERIFIED_SAFE"
    VERIFIED_BUILD_BREAKER = "VERIFIED_BUILD_BREAKER"
    UNKNOWN_APPLICABILITY = "UNKNOWN_APPLICABILITY"

class BuildModifierFamily(str, Enum):
    ADDS_FIRE_DAMAGE_ATTACKS = "ADDS_FIRE_DAMAGE_ATTACKS"
    ADDS_FIRE_DAMAGE_SPELLS = "ADDS_FIRE_DAMAGE_SPELLS"
    EXTRA_FIRE_DAMAGE = "EXTRA_FIRE_DAMAGE"
    INCREASED_FIRE_DAMAGE = "INCREASED_FIRE_DAMAGE"
    FIRE_RESISTANCE = "FIRE_RESISTANCE"
    FIRE_SPELL_LEVEL = "FIRE_SPELL_LEVEL"

class BuildRule(BaseModel):
    rule_id: str
    name: str
    severity: RuleSeverity
    description: str
    min_stage: ProgressionStage
    max_stage: ProgressionStage | None = None
    target_slots: list[SlotType] = Field(default_factory=list)
    target_weapon_set: WeaponSetContext | None = None
    prohibited_families: list[BuildModifierFamily] = Field(default_factory=list)
    exempt_archetypes: list[str] = Field(default_factory=list)  # e.g. ["staff"] for weapon_set_1
    mechanical_risk_explanation: str

class EquipmentRecommendation(BaseModel):
    candidate_item: ItemCandidate
    target_slot: SlotType
    target_weapon_set: WeaponSetContext | None
    replaced_items: list[ItemCandidate] = Field(default_factory=list)
    verdict: EquipmentVerdict
    summary: str
    known_deltas: list[StatDelta]
    projected_absolute_values: list[StatDelta]
    resolved_deficiencies: list[str]
    new_deficiencies_created: list[str]
    cascade_result: RequirementCascadeResult
    build_breaker_certainty: BuildBreakerCertainty = BuildBreakerCertainty.VERIFIED_SAFE
    build_breaker_triggered: BuildRule | None = None
    prerequisites_to_equip: list[str] = Field(default_factory=list)
    explanation: str
    confidence: VerificationState
```

## Risks / Trade-offs

- **[Risk: GGG API Registration Freeze]** → Users cannot create new OAuth clients today.
  *Mitigation*: The entire Gear Brain operates 100% offline via manual draft loadout capture, loadout finalization (`companion gear loadout finalize`), manual baseline (`companion gear baseline set`), and clipboard parsing (`companion gear inspect-clipboard`). OAuth is an optional enhancement for automatic equipped gear sync.
- **[Risk: Stale or Inaccurate Manual Baseline After Gear Mutation]** → Changing gear mutates the character state, leaving old baseline facts incorrect.
  *Mitigation*: Monotonic `revision` tracking anchors baseline to loadout. Additive stats safely rebase (`DERIVED_CALCULATION`), while non-linear defenses are marked `STALE` / `UNKNOWN`. Stale baseline blocks absolute claims and gates confident verdicts without blocking delta reporting.
- **[Risk: Resistance Rebase from Capped Effective Values]** → Rebase calculations against capped effective resistance (e.g. 75 - 40 + 10 = 45) distort character state when raw resistance has an overcap buffer (e.g. 115 - 40 + 10 = 85 -> effective 75).
  *Mitigation*: Resistance rebase policy requires raw uncapped resistance. If raw resistance cannot be proven, the engine reports item deltas and marks post-swap effective resistance `UNKNOWN` / `STALE`, refusing to fabricate absolute numbers.
- **[Risk: Premature Mutation During Initial Setup]** → Ingesting existing items could trigger gear swap logic and baseline invalidation before setup is complete.
  *Mitigation*: Distinguish initial setup (draft) from post-setup mutations. `companion gear loadout finalize` establishes revision 1, after which `companion gear baseline set` anchors to revision 1.
- **[Risk: Conflating Crossbow and Bow Off-Hand Rules]** → Assuming crossbows can equip quivers like bows violates PoE2 game-item rules where quivers are bow-exclusive and crossbows occupy both weapon hand slots.
  *Mitigation*: Normalized base metadata specifies actual `SlotConflictTopology` (`occupied_slots`, `conflicting_slots`, `allowed_companion_slots`) grounded in verified game rules. Both Staves and Crossbows occupy both weapon slots in their respective sets; quivers are bow-only and excluded from the Fubgun loadout; and generic metadata preserves future bow+quiver support without corrupting crossbow projection.
- **[Risk: Multi-Slot Weapon Displacements Leaving Phantom Items]** → Equipping a two-handed weapon could accidentally preserve off-hand shield contributions or fail to catch lost shield attributes.
  *Mitigation*: Generalized slot conflict topology identifies all conflicting slots in the target set. Projection displaces all conflicting items, subtracting their contributions and verifying requirement cascades across the full displaced topology.
- **[Risk: Unverified Fire Modifiers Ruining Post-Swap Ignite]** → Novel or unmodeled fire modifiers might apply to Oil Grenade and break the build if recommended.
  *Mitigation*: High-Risk Unknown Gate blocks confident `EQUIP_NOW` for any modifier with `UNKNOWN_APPLICABILITY` relating to fire damage, emitting `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE` with explicit `HIGH_RISK` warning.
- **[Risk: Accidental Double-Counting of Defenses]** → Total character Armour could be inflated if combined with item local Armour.
  *Mitigation*: The engine explicitly decouples $S_{\text{baseline}}$ from item contributions; candidate projection only adds $\Delta \text{Local} = C_{\text{candidate}} - C_{\text{equipped}}$.

## Open Questions

- *Open Question 1*: Should visual character panel OCR be prioritized for automated baseline ingestion?
  *Resolution*: Deferred to post-V1. Manual baseline (`companion gear baseline set`) provides deterministic, zero-hallucination baseline facts immediately without vision latency or OCR error rates.
