# Tasks: PoE2 Equipment Intelligence & Gear Brain

## 1. Normalized Item Model, Scopes, Generalized Slot Topology, and Text Parser

- [x] 1.1 Define `SlotType`, `SlotOccupancy` (`SINGLE_SLOT`, `MAIN_HAND`, `OFF_HAND`, `TWO_HAND`, `SHARED_EQUIPMENT_SLOT`, `UNKNOWN_OCCUPANCY`), `SlotConflictTopology` (`occupied_slots`, `conflicting_slots`, `allowed_companion_slots`, `is_known`), `ModifierScope`, `NormalizedModifierType`, `NormalizedModifier`, and `ItemCandidate` schemas in `companion/equipment/schema.py` and verify via `uv run pytest tests/unit/equipment/test_schema.py`
- [x] 1.2 Implement PoE2 item text parser in `companion/equipment/parser.py` parsing item headers, rarity, base type, defense ratings, requirements, normalized slot-conflict topology from verified base metadata (two-handed staff occupies both slots in set 1; two-handed crossbow occupies both slots in set 2; quivers require wielding a bow and cannot pair with crossbows; unknown topology remains unknown), and mod lines and verify via `uv run pytest tests/unit/equipment/test_parser.py`
- [x] 1.3 Implement modifier normalizer in `companion/equipment/normalizer.py` distinguishing `LOCAL_ITEM_STAT`, `GLOBAL_CHARACTER_STAT`, `REQUIREMENT`, `BUILD_MECHANIC`, `CONDITIONAL`, and `UNKNOWN_SCOPE` and verify via `uv run pytest tests/unit/equipment/test_normalizer.py`
- [x] 1.4 Implement unit tests for local vs global modifier scope and double-count prevention (displayed Armour includes local % and is not added globally, local weapon damage not generic global damage, unknown scope isolated) in `tests/unit/equipment/test_modifier_scope.py` and verify via `uv run pytest tests/unit/equipment/test_modifier_scope.py`

## 2. Item Contribution, Baseline Models, and Revision Anchoring

- [x] 2.1 Define `BaselineSource`, `CharacterFact`, and `CharacterStatBaseline` models in `companion/equipment/baseline.py`, distinguishing `raw_uncapped_resistance`, `effective_resistance`, `max_resistance`, and `overcap_buffer` per resistance family, supporting `baseline_id`, `anchored_loadout_revision: int`, optional Life, Defenses, Attributes, and Movement Speed, enforcing that omitted stats remain `UNKNOWN` without unverified hardcoded verified defaults, and verify via `uv run pytest tests/unit/equipment/test_baseline_schema.py`
- [x] 2.2 Implement `ItemContribution` layer in `companion/equipment/contribution.py` aggregating character-relevant contributions from parsed candidate items, preserving slot conflict topology and weapon set context, and verify via `uv run pytest tests/unit/equipment/test_contribution.py`
- [x] 2.3 Implement baseline CLI commands `companion gear baseline set`, `companion gear baseline show`, and `companion gear baseline refresh` in `companion/equipment/baseline_cli.py`, accepting raw/effective resistances, defenses, and attributes, anchoring directly to current loadout revision, and replacing derived baseline chains and verify via `uv run pytest tests/unit/equipment/test_baseline_cli.py`
- [x] 2.4 Implement baseline consistency gate in `companion/equipment/baseline_gate.py` verifying `baseline.anchored_loadout_revision == current_loadout.revision` and marking unreconciled stats `STALE` without blocking known item deltas and verify via `uv run pytest tests/unit/equipment/test_baseline_gate.py`
- [x] 2.5 Implement unit tests for baseline double-count protection, omitted fields remaining `UNKNOWN`, and partial projection honesty in `tests/unit/equipment/test_baseline.py` and verify via `uv run pytest tests/unit/equipment/test_baseline.py`

## 3. Loadout Domain Models, Revision Tracking, and Post-Equip Reconciliation

- [x] 3.1 Implement `EquippedSlotEntry` and `EquippedLoadout` domain models in `companion/equipment/loadout.py` supporting `loadout_id`, monotonic `revision`, `is_finalized: bool`, `known_slots`, `unknown_slots`, `shared_slots`, `weapon_set_1`, and `weapon_set_2` with provenance metadata and verify via `uv run pytest tests/unit/equipment/test_loadout.py`
- [x] 3.2 Implement manual loadout CLI commands in `companion/equipment/loadout_cli.py`:
  - `companion gear loadout set-clipboard --slot <slot>` populating draft loadout during initial setup without simulating gear swaps or incrementing revisions
  - `companion gear loadout finalize` transitioning draft to finalized state, establishing `loadout_id`, initializing stable `revision = 1`, and recording known vs unknown slots
  - `companion gear loadout show` and `companion gear loadout clear <slot>`
  and verify via `uv run pytest tests/unit/equipment/test_loadout_cli.py`
- [x] 3.3 Implement candidate promotion command `companion gear loadout promote-candidate --slot <slot>` in `companion/equipment/loadout_promotion.py`, incrementing `loadout.revision` and reconciling baseline after finalization, while ensuring candidate inspection and recommendation commands remain strictly read-only and never mutate state, and verify via `uv run pytest tests/unit/equipment/test_loadout_promotion.py`
- [x] 3.4 Implement post-setup baseline reconciler in `companion/equipment/reconciler.py` executing Resistance Rebase Policy (rebase raw uncapped resistance when proven and clamp via `min(new_raw, max_res)`; if raw state unproven, mark effective resistance `UNKNOWN` / `STALE` while reporting item delta) and marking non-linear defenses (Armour, Evasion, ES) `STALE` / `UNKNOWN` and verify via `uv run pytest tests/unit/equipment/test_reconciler.py`
- [x] 3.5 Implement loadout provenance tracking and conflict detection flagging `verification: CONFLICTING` when API synchronization contradicts manual loadout data in `companion/equipment/loadout_provenance.py` and verify via `uv run pytest tests/unit/equipment/test_loadout_provenance.py`
- [x] 3.6 Implement comprehensive unit tests for baseline/loadout revisions and initial setup in `tests/unit/equipment/test_baseline_revision.py`:
  - Capture several existing items before baseline does not simulate gear swaps
  - Finalized loadout starts a stable revision (revision 1)
  - Baseline anchors to finalized revision
  - Partial loadout retains UNKNOWN slots
  - Candidate against unknown current slot cannot claim exact net delta
  - Promote candidate increments revision
  - Safe raw resistance rebase where proven produces correct new baseline (`DERIVED_CALCULATION`)
  - Unsafe Armour projection marks total Armour stale rather than fabricating value
  - Fresh manual baseline reanchors to current revision
  - Stale baseline cannot produce fake absolute projected stat
  - Recommendation alone does not change loadout revision
  - Manually replacing established current slot after finalization increments revision and reconciles baseline
  - Application restart preserves baseline/loadout revision relationship
  and verify via `uv run pytest tests/unit/equipment/test_baseline_revision.py`

## 4. Generalized Slot Conflict Topology, Two-Handed Projection, and Weapon-Set Independence

- [x] 4.1 Implement weapon-set projection engine in `companion/equipment/weapon_projection.py` utilizing `SlotConflictTopology` to displace all verified conflicting slots in target set (staff candidate replaces staff and owns both slots in set 1; crossbow candidate replaces crossbow, owns both slots in set 2, with no off-hand quiver contribution) while keeping opposing weapon set completely untouched and one-hand replacement leaving off-hand empty/unknown without fabricating gear and verify via `uv run pytest tests/unit/equipment/test_weapon_projection.py`
- [x] 4.2 Implement occupancy-aware contribution aggregator in `companion/equipment/occupancy_contribution.py` subtracting contributions from ALL displaced items in the replaced topology (main-hand + conflicting off-hand) without subtracting or preserving fictional off-hand contributions for crossbows and verify via `uv run pytest tests/unit/equipment/test_occupancy_contribution.py`
- [x] 4.3 Implement comprehensive unit tests for slot conflict topology and multi-slot displacement in `tests/unit/equipment/test_weapon_set_occupancy.py`:
  - Staff set 1 occupies both weapon slots (main-hand and off-hand)
  - Crossbow set 2 occupies both weapon slots (main-hand and off-hand)
  - Crossbow cannot coexist with quiver (quiver requires bow)
  - Quiver is not part of Fubgun loadout model
  - Swapping crossbow affects set 2 only and owns both hand slots
  - Swapping staff affects set 1 only and owns both hand slots
  - No phantom off-hand contribution enters projected stats (no fictional quiver or shield)
  - Weapon set 2 remains isolated during set 1 modifications
  - Generic occupancy metadata preserves generic future support for other classes (e.g. bow + quiver) without hardcoding identical exceptions
  - UNKNOWN topology blocks confident full projection
  - Shared gear remains shared across both sets
  - Requirement cascade includes removed off-hand attribute/resistance contribution
  and verify via `uv run pytest tests/unit/equipment/test_weapon_set_occupancy.py`

## 5. Partial Projection and Dynamic Resistance Intelligence

- [x] 5.1 Implement partial projection engine in `companion/equipment/partial_projection.py` reporting `KNOWN DELTA` from compared items while keeping `PROJECTED ABSOLUTE VALUE` as `UNKNOWN` when baseline is unverified or stale and verify via `uv run pytest tests/unit/equipment/test_partial_projection.py`
- [x] 5.2 Implement dynamic resistance target and rebase model (`raw_uncapped_resistance`, `effective_resistance`, `max_resistance`, `overcap_buffer`) in `companion/equipment/resistance.py`, using verified max resistance (e.g. 78%) without inventing unverified campaign penalties and verify via `uv run pytest tests/unit/equipment/test_resistance_targets.py`
- [x] 5.3 Implement dynamic marginal-value evaluator for elemental and chaos resistances, weighting deficits below target cap as critical and surplus resistance as low marginal value and verify via `uv run pytest tests/unit/equipment/test_resistance_intelligence.py`
- [x] 5.4 Implement comprehensive unit tests for resistance intelligence and rebase policy in `tests/unit/equipment/test_partial_resistance.py`:
  - Capped effective resistance is not used as raw additive baseline
  - Raw 115, cap 75, swap -30 resistance -> effective remains 75 (raw becomes 85)
  - Raw 80, cap 75, swap -10 -> effective becomes 70
  - Effective 75 but raw/overcap UNKNOWN -> absolute post-swap resistance UNKNOWN
  - Known item delta still reported when absolute resistance is unknown
  - Max resistance 78 respected independently of raw resistance (raw 85, cap 78 -> effective 78)
  - Overcap buffer modeled separately from effective resistance
  and verify via `uv run pytest tests/unit/equipment/test_partial_resistance.py`

## 6. Whole-Loadout Requirement Cascade Validation

- [x] 6.1 Implement requirement cascade validator in `companion/equipment/requirements.py` checking candidate requirements, all equipped items across shared and both weapon sets, and build-critical gems upon attribute changes and verify via `uv run pytest tests/unit/equipment/test_requirement_cascade.py`
- [x] 6.2 Implement cascade deficiency reporting generating `RequirementCascadeResult` and downgrading recommendation verdict to `CONDITIONAL_UPGRADE` or `REJECT` and verify via `uv run pytest tests/unit/equipment/test_cascade_reporting.py`
- [x] 6.3 Implement unit tests for requirement cascades (removing amulet breaks weapon requirement, swap satisfies item but breaks socketed gem, displaced off-hand attribute loss breaks gem) in `tests/unit/equipment/test_cascades.py` and verify via `uv run pytest tests/unit/equipment/test_cascades.py`

## 7. Exact Fubgun Build-Breaker Engine, Certainty Tri-State, and High-Risk Unknown Gate

- [x] 7.1 Define `RuleSeverity`, `BuildRule`, `BuildModifierFamily`, and `BuildBreakerCertainty` (`VERIFIED_SAFE`, `VERIFIED_BUILD_BREAKER`, `UNKNOWN_APPLICABILITY`) schemas in `companion/equipment/rules.py` and verify via `uv run pytest tests/unit/equipment/test_rule_schema.py`
- [x] 7.2 Encode verified stage-aware rules for Fubgun 0.5.5 Flameblast / Oil Grenade in `companion/equipment/fubgun_rules.py` prohibiting flat or extra Fire damage applying to Oil Grenade while explicitly exempting Flameblast staff (weapon set 1) and verify via `uv run pytest tests/unit/equipment/test_fubgun_rules.py`
- [x] 7.3 Implement `BuildBreakerEngine` in `companion/equipment/build_breaker.py` evaluating modifier family, slot, shared vs weapon-set context, target weapon set, Oil Grenade attack applicability, and progression stage, classifying modifiers into tri-state certainty, and verify via `uv run pytest tests/unit/equipment/test_build_breaker.py`
- [x] 7.4 Implement High-Risk Unknown Gate in `companion/equipment/build_breaker_gate.py` blocking confident `EQUIP_NOW` when modifiers have `UNKNOWN_APPLICABILITY` regarding Oil Grenade ignite risk and emitting `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE` with `HIGH_RISK` warning and verify via `uv run pytest tests/unit/equipment/test_build_breaker_gate.py`
- [x] 7.5 Implement comprehensive unit tests for build-breaker certainty and verdict uncertainty in `tests/unit/equipment/test_verdict_uncertainty.py`:
  - Verified harmful Fire modifier -> REJECT
  - Verified safe Fire modifier -> normal evaluation
  - Unknown Fire applicability + amazing generic stats -> NOT EQUIP_NOW (emits `CONDITIONAL_UPGRADE` with `HIGH_RISK` or `INSUFFICIENT_DATA`)
  - Unknown potential build-breaker remains explicit in explanation
  - Later verification SAFE permits reevaluation to EQUIP_NOW
  - Later verification harmful changes verdict to REJECT
  and verify via `uv run pytest tests/unit/equipment/test_verdict_uncertainty.py`
- [x] 7.6 Implement comprehensive unit tests for Fubgun fire rule in `tests/unit/equipment/test_fubgun_fire_rule.py`:
  - Positive tests: shared ring with added fire to attacks -> REJECT; shared gloves with added fire to attacks/Oil Grenade -> REJECT; Oil Grenade crossbow with added fire -> REJECT; verified extra fire applying to Oil Grenade -> REJECT
  - Negative tests: Flameblast staff in weapon set 1 with fire modifiers -> NOT rejected (verified exception); Fire Resistance -> NOT rejected; % increased Fire Damage -> NOT rejected solely by fire rule; unrelated "Fire" text -> NOT rejected; pre-swap stages using stage-aware rules
  - Ambiguity test: unknown fire modifier applicability -> UNKNOWN / HIGH_RISK, never fabricated HARD_REJECT
  and verify via `uv run pytest tests/unit/equipment/test_fubgun_fire_rule.py`

## 8. Equipment Intelligence Engine, Non-Scalar Verdict Precedence, and Recommendations

- [x] 8.1 Implement slot-specific evaluation weights in `companion/equipment/slots.py` (Boots movement speed, Body Armour base defenses, Jewelry balancing) and verify via `uv run pytest tests/unit/equipment/test_slot_intelligence.py`
- [x] 8.2 Implement deterministic non-scalar verdict precedence resolver in `companion/equipment/precedence.py` enforcing Tier 1 (Verified Build Breaker) -> Tier 2 (Critical Requirement Failure) -> Tier 3 (Unknown Potential Build Breaker) -> Tier 4 (New Critical Character Deficiency) -> Tier 5 (Normal Gear Improvement) and verify via `uv run pytest tests/unit/equipment/test_precedence.py`
- [x] 8.3 Implement the core `EquipmentIntelligenceEngine` in `companion/equipment/engine.py` coordinating baseline consistency gating, multi-slot projection, build breaker tri-state evaluation, cascades, and verdict precedence and verify via `uv run pytest tests/unit/equipment/test_engine.py`
- [x] 8.4 Generate structured, explainable delta models (`EquipmentRecommendation`) with trade-offs, replaced items list, and compensation slots identified and verify via `uv run pytest tests/unit/equipment/test_recommendation.py`

## 9. Manual Clipboard Candidate Workflow and CLI Commands

- [x] 9.1 Implement passive clipboard reader utility using standard platform clipboard access in `companion/equipment/clipboard.py`, strictly enforcing zero simulated keypresses or mouse inputs, and verify via `uv run pytest tests/unit/equipment/test_clipboard.py`
- [x] 9.2 Add CLI command `companion gear inspect-clipboard` in `companion/cli.py` to inspect and evaluate item text copied from in-game stash or inventory against stored loadout and baseline without mutating loadout or incrementing revision and verify via `uv run pytest tests/unit/equipment/test_cli_clipboard.py`
- [x] 9.3 Add CLI command `companion gear evaluate --file <item.txt>` for file-based offline inspection and test automation and verify via `uv run pytest tests/unit/equipment/test_cli_evaluate.py`
- [x] 9.4 Implement unit tests verifying the complete no-OAuth V1 offline workflow (draft loadout set-clipboard -> finalize loadout (rev 1) -> baseline set -> inspect candidate -> verdict -> promote candidate mutates revision) in `tests/unit/equipment/test_offline_workflow.py` and verify via `uv run pytest tests/unit/equipment/test_offline_workflow.py`

## 10. Official Character API Adapter and Capability Gating

- [x] 10.1 Implement official API capability matrix in `companion/equipment/api_adapter.py` reporting `PoE2_EQUIPMENT` as available and `PoE2_INVENTORY` and `PoE2_STASH` as `UNAVAILABLE_BY_CURRENT_OFFICIAL_API` and verify via `uv run pytest tests/unit/equipment/test_api_capabilities.py`
- [x] 10.2 Implement OAuth 2.1 status gating (`API_AVAILABLE`, `AUTH_CONFIGURED`, `AUTH_UNAVAILABLE`) handling developer registration freeze and falling back to offline workflow without crashing and verify via `uv run pytest tests/unit/equipment/test_api_gating.py`
- [x] 10.3 Implement mapping of `OfficialCharacterData.equipment` to `EquippedLoadout` with provenance `GGG_OFFICIAL_API` when authenticated and conflict detection against manual entries and verify via `uv run pytest tests/unit/equipment/test_api_adapter.py`

## 11. End-to-End Integration and UAT Verification Suite

- [x] 11.1 Assemble end-to-end integration test suite verifying candidate parsing, multi-slot projection, baseline revision anchoring, and verdict generation across realistic PoE2 items via `uv run pytest tests/integration/equipment/test_equipment_pipeline.py`
- [x] 11.2 Execute UAT scenario testing candidate boots upgrade (+66 Life, +28% Lightning Res, +10% Movement Speed) on character with 43% Lightning Res deficit confirming `EQUIP_NOW` via `uv run pytest tests/integration/equipment/test_uat_boots.py`
- [x] 11.3 Execute UAT scenario testing high-life ring upgrade that removes 40% Lightning Res from current ring confirming `CONDITIONAL_UPGRADE` via `uv run pytest tests/integration/equipment/test_uat_conditional_ring.py`
- [x] 11.4 Execute UAT scenario testing post-swap shared ring with flat fire to attacks confirming `REJECT` via exact Fubgun build-breaker predicate via `uv run pytest tests/integration/equipment/test_uat_build_breaker.py`
- [x] 11.5 Execute UAT scenario testing post-swap Flameblast staff with fire spell damage confirming NOT rejected under staff exception via `uv run pytest tests/integration/equipment/test_uat_staff_exception.py`
- [x] 11.6 Execute UAT scenario testing two-handed staff displacing conflicting set-1 slots while preserving set-2 crossbow setup intact (with both weapons occupying both hand slots and zero quiver contribution) via `uv run pytest tests/integration/equipment/test_uat_two_handed_projection.py`
- [x] 11.7 Execute UAT scenario testing unknown fire modifier applicability blocking `EQUIP_NOW` and emitting `CONDITIONAL_UPGRADE` with `HIGH_RISK` warning via `uv run pytest tests/integration/equipment/test_uat_unknown_build_breaker.py`
- [x] 11.8 Execute UAT scenario testing full offline V1 workflow (draft loadout capture -> finalize loadout (rev 1) -> manual baseline set -> candidate evaluation -> explicit promotion increments revision to 2 and safely rebases raw resistance -> refresh baseline reanchors to rev 2) via `uv run pytest tests/integration/equipment/test_uat_offline_workflow.py`
- [x] 11.9 Run full project test suite to verify zero regressions across existing subsystems via `uv run pytest`

## 12. Loadout Revision Integrity, Decision-Relevant Fact Freshness, and History Snapshots

- [x] 12.1 Canonical Fact Predicate: Update `CharacterFact.is_known` to exclude `CONFLICTING`, `UNKNOWN`, and `STALE` verification states in `companion/equipment/baseline.py` and verify via `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py::test_character_fact_conflicting_is_not_known`
- [x] 12.2 Movement Speed Baseline Reconciliation: Implement movement speed delta calculation in `companion/equipment/reconciler.py` recording `DERIVED_CALCULATION` when baseline is known or marking `STALE` without fabricating values, and verify via `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py::test_movement_speed_reconciliation_promotion`
- [x] 12.3 Decision-Relevant Fact Dependencies: Implement `RecommendationFactDependencies` and `determine_recommendation_fact_dependencies` in `companion/equipment/fact_dependencies.py` and integrate with `analyze_data_sufficiency` in `companion/equipment/data_sufficiency.py` and `companion/equipment/engine.py` so only decision-relevant stale/unknown/conflicting facts gate confidence while unrelated stale facts do not globally block recommendations, and verify via `uv run pytest tests/unit/equipment/test_data_sufficiency.py tests/unit/equipment/test_loadout_revision_integrity.py`
- [x] 12.4 Local Defense Regression and Trade-off Precedence: Implement `check_defense_regression` in `companion/equipment/precedence.py` and integrate with `companion/equipment/engine.py` ensuring negative local defense deltas (Armour, Evasion, ES) produce `MIXED_TRADEOFF` and `CONDITIONAL_UPGRADE` rather than clean `EQUIP_NOW` or `DOMINANT_IMPROVEMENT`, and verify via `uv run pytest tests/unit/equipment/test_precedence.py tests/unit/equipment/test_loadout_revision_integrity.py`
- [x] 12.5 Authoritative Loadout Transition Wrapper & CLI History Snapshots: Route CLI promotion and slot mutations in `companion/cli.py` and `companion/equipment/loadout_cli.py` through `run_loadout_promote_candidate` to snapshot revision `N` to `loadout_history` before advancing to `N+1`, attach `LoadoutTransitionResult`, and emit state-accurate CLI output, and verify via `uv run pytest tests/unit/equipment/test_loadout_cli.py tests/unit/equipment/test_loadout_revision_integrity.py`
- [x] 12.6 OpenSpec Documentation Alignment: Update `design.md`, `spec.md`, and `tasks.md` under `openspec/changes/poe2-companion-equipment-intelligence/` to document loadout revision integrity, fact freshness separation, decision-relevant fact dependencies, defense trade-offs, movement speed reconciliation, and history snapshots, validated via `openspec validate poe2-companion-equipment-intelligence --strict --json`
