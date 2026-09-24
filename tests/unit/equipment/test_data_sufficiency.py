# tests/unit/equipment/test_data_sufficiency.py
from companion.equipment.baseline import CharacterFact, CharacterStatBaseline
from companion.equipment.data_sufficiency import (
    RecommendationDataSufficiency,
    analyze_data_sufficiency,
)
from companion.equipment.fact_dependencies import (
    RecommendationFactDependencies,
    determine_recommendation_fact_dependencies,
)
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.parser import parse_item_text
from companion.equipment.rules import BuildBreakerCertainty, BuildBreakerEvaluation
from companion.equipment.schema import (
    ItemCandidate,
    SlotConflictTopology,
    SlotOccupancy,
    SlotType,
)
from companion.state.provenance import VerificationState

SAMPLE_BOOTS = """Item Class: Boots\nRarity: Rare\nTest Boots\n--------\nRequirements:\nLevel: 45\n--------\n+30 to maximum Life\n"""


def make_test_loadout(boots: ItemCandidate | None = None, revision: int = 1) -> EquippedLoadout:
    loadout = EquippedLoadout.create_draft(character_id="test", loadout_id="l1")
    if boots is not None:
        loadout.set_slot(SlotType.BOOTS, boots)
    loadout.finalize()
    loadout.revision = revision
    return loadout


def test_unknown_slot_yields_insufficient_for_confident_equip():
    cand = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)
    loadout = make_test_loadout(boots=None, revision=1)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="test",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=loadout.compute_fingerprint(),
        life=1000,
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)

    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert res.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
    assert any("slot" in r.lower() for r in res.reasons)
    assert res.is_sufficient_for_equip_now is False


def test_stale_baseline_yields_insufficient_for_confident_equip():
    cand = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)
    loadout = make_test_loadout(boots=cand, revision=2)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="test",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=loadout.compute_fingerprint(),
        life=1000,
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)

    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert res.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
    assert any("stale" in r.lower() for r in res.reasons)
    assert res.is_sufficient_for_equip_now is False


def test_unknown_applicability_yields_insufficient_or_blocks_equip_now():
    cand = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)
    loadout = make_test_loadout(boots=cand, revision=1)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="test",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=loadout.compute_fingerprint(),
        life=1000,
        fire_res=75,
        cold_res=75,
        lightning_res=75,
        chaos_res=0,
    )
    unknown_safety = BuildBreakerEvaluation(
        certainty=BuildBreakerCertainty.UNKNOWN_APPLICABILITY,
        rule_name="Oil Grenade ignite risk",
        reason="Fire damage affix applicability unverified",
    )

    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=unknown_safety,
    )
    assert res.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
    assert res.is_sufficient_for_equip_now is False
    assert any("applicability" in r.lower() or "risk" in r.lower() or "build-breaker" in r.lower() for r in res.reasons)


def test_unknown_slot_topology_yields_insufficient():
    cand = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)
    # Give candidate unknown slot topology
    cand_unknown_topo = cand.model_copy(
        update={
            "slot_occupancy": SlotOccupancy.UNKNOWN_OCCUPANCY,
            "slot_conflict_topology": SlotConflictTopology(occupied_slots=[], is_known=False),
        }
    )
    loadout = make_test_loadout(boots=cand, revision=1)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="test",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=loadout.compute_fingerprint(),
        life=1000,
        fire_res=75,
        cold_res=75,
        lightning_res=75,
        chaos_res=0,
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)

    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand_unknown_topo,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert res.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
    assert res.is_sufficient_for_equip_now is False
    assert any("topology" in r.lower() or "occupancy" in r.lower() for r in res.reasons)


def test_missing_baseline_yields_insufficient():
    cand = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)
    loadout = make_test_loadout(boots=cand, revision=1)
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)

    res = analyze_data_sufficiency(
        baseline=None,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert res.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
    assert res.is_sufficient_for_equip_now is False
    assert any("baseline" in r.lower() for r in res.reasons)


def test_partial_safe_when_known_slot_and_safe_but_some_facts_unobserved():
    cand = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)
    loadout = make_test_loadout(boots=cand, revision=1)
    # Baseline has life and fire, but missing cold, lightning, chaos res
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="test",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=loadout.compute_fingerprint(),
        life=1000,
        fire_res=75,
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)

    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    # Partial safe allows partial swap analysis without confident equip_now
    assert res.sufficiency in (
        RecommendationDataSufficiency.PARTIAL_SAFE,
        RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP,
    )
    assert res.is_sufficient_for_equip_now is False


def test_fully_sufficient_all_facts_known():
    cand = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)
    loadout = make_test_loadout(boots=cand, revision=1)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="test",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=loadout.compute_fingerprint(),
        life=1000,
        armour=500,
        evasion=500,
        energy_shield=100,
        fire_res=75,
        cold_res=75,
        lightning_res=75,
        chaos_res=0,
        strength=100,
        dexterity=100,
        intelligence=100,
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)

    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert res.sufficiency == RecommendationDataSufficiency.SUFFICIENT
    assert res.is_sufficient_for_equip_now is True
    assert len(res.reasons) == 0


def test_sufficiency_gated_by_unmodeled_removed_mechanic():
    """Removing an unmodeled special mechanic (like Iron Reflexes) blocks confident equip in data sufficiency."""
    from companion.equipment.schema import ModifierScope, NormalizedModifier, NormalizedModifierType
    from companion.state.provenance import VerificationState

    cand = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)
    equipped_boots = cand.model_copy(
        update={
            "modifiers": [
                NormalizedModifier(
                    modifier_type=NormalizedModifierType.SPECIAL_MECHANIC,
                    scope=ModifierScope.BUILD_MECHANIC,
                    value=0.0,
                    raw_text="Iron Reflexes — Unscalable Value",
                    verification_state=VerificationState.UNKNOWN,
                    mechanic_id="iron_reflexes",
                )
            ]
        }
    )

    loadout = make_test_loadout(boots=equipped_boots, revision=1)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="test",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=loadout.compute_fingerprint(),
        life=1000,
        fire_res=75,
        cold_res=75,
        lightning_res=75,
        chaos_res=0,
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)

    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert res.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
    assert res.is_sufficient_for_equip_now is False
    assert res.is_mechanics_safe is False
    assert any("Iron Reflexes" in r for r in res.reasons)


def test_sufficiency_gated_by_unmodeled_added_mechanic():
    """Adding an unmodeled special mechanic blocks confident equip in data sufficiency."""
    from companion.equipment.schema import ModifierScope, NormalizedModifier, NormalizedModifierType
    from companion.state.provenance import VerificationState

    cand_plain = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)
    cand_special = cand_plain.model_copy(
        update={
            "modifiers": [
                NormalizedModifier(
                    modifier_type=NormalizedModifierType.SPECIAL_MECHANIC,
                    scope=ModifierScope.BUILD_MECHANIC,
                    value=0.0,
                    raw_text="Iron Reflexes — Unscalable Value",
                    verification_state=VerificationState.UNKNOWN,
                    mechanic_id="iron_reflexes",
                )
            ]
        }
    )

    loadout = make_test_loadout(boots=cand_plain, revision=1)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="test",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=loadout.compute_fingerprint(),
        life=1000,
        fire_res=75,
        cold_res=75,
        lightning_res=75,
        chaos_res=0,
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)

    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand_special,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert res.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP


def test_unknown_movement_speed_blocks_speed_changing_candidate():
    boots_ms = """Item Class: Boots\nRarity: Rare\nRunner Boots\n--------\nRequirements:\nLevel: 45\n--------\n+30 to maximum Life\n+10% increased Movement Speed\n"""
    cand = parse_item_text(boots_ms, target_slot=SlotType.BOOTS)
    curr_boots = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)

    loadout = make_test_loadout(boots=curr_boots, revision=1)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="test",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=loadout.compute_fingerprint(),
        life=1000,
        fire_res=75,
        cold_res=75,
        lightning_res=75,
        chaos_res=0,
    )
    # movement_speed is left unknown on baseline
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert res.is_sufficient_for_equip_now is False
    assert res.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
    assert any("movement speed is unknown" in r.lower() for r in res.reasons)
    assert res.fact_dependencies is not None
    assert res.fact_dependencies.needs_movement_speed is True


def test_conflicting_strength_blocks_candidate_requiring_strength():
    boots_req = """Item Class: Boots\nRarity: Rare\nHeavy Greaves\n--------\nRequirements:\nLevel: 45\nStrength: 65\n--------\n+30 to maximum Life\n"""
    cand = parse_item_text(boots_req, target_slot=SlotType.BOOTS)
    curr_boots = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)

    loadout = make_test_loadout(boots=curr_boots, revision=1)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="test",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=loadout.compute_fingerprint(),
        life=1000,
        fire_res=75,
        cold_res=75,
        lightning_res=75,
        chaos_res=0,
        strength=100,
    )
    # Set strength to conflicting
    baseline.strength = CharacterFact[int].create(
        value=100,
        verification=VerificationState.CONFLICTING,
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert res.is_sufficient_for_equip_now is False
    assert res.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
    assert any("strength is conflicting" in r.lower() for r in res.reasons)
    assert res.fact_dependencies is not None
    assert res.fact_dependencies.needs_strength is True
