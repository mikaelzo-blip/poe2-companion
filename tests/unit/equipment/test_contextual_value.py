from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.contextual_value import (
    DeficiencyImpact,
    MarginalValueTier,
    evaluate_contextual_resistance,
    evaluate_contextual_attribute,
    evaluate_loadout_contextual_analysis,
)
from companion.equipment.resistance import ResistanceType, ResistanceTarget


def test_resistance_same_item_different_character():
    # Scenario A: Character with 30% Lightning Res, target 75%
    baseline_a = CharacterStatBaseline.create_partial(
        baseline_id="b_a", character_id="char_a", anchored_loadout_revision=1,
        lightning_res=30, lightning_raw=30, max_lightning_res=75
    )
    # +30 Lightning Res improves deficit from 45 to 15
    res_a = evaluate_contextual_resistance(baseline_a, ResistanceType.LIGHTNING, delta=30.0)
    assert res_a.impact == DeficiencyImpact.IMPROVES
    assert res_a.tier in (MarginalValueTier.HIGH, MarginalValueTier.CRITICAL)

    # Scenario B: Character with 105% raw, 75% effective, target 75%
    baseline_b = CharacterStatBaseline.create_partial(
        baseline_id="b_b", character_id="char_b", anchored_loadout_revision=1,
        lightning_res=75, lightning_raw=105, max_lightning_res=75
    )
    # +30 Lightning Res is just more overcap (surplus)
    res_b = evaluate_contextual_resistance(baseline_b, ResistanceType.LIGHTNING, delta=30.0)
    assert res_b.impact == DeficiencyImpact.UNCHANGED
    assert res_b.tier in (MarginalValueTier.LOW, MarginalValueTier.NO_IMMEDIATE_VALUE)


def test_attribute_same_item_different_character():
    # Scenario A: Dex 88, requires 95 (deficit 7). Candidate +10 Dex -> resolves deficit!
    baseline_a = CharacterStatBaseline.create_partial(
        baseline_id="b_a", character_id="char_a", anchored_loadout_revision=1,
        dexterity=88
    )
    attr_a = evaluate_contextual_attribute(baseline_a, "dex", delta=10.0, highest_required=95)
    assert attr_a.impact == DeficiencyImpact.RESOLVES
    assert attr_a.tier in (MarginalValueTier.CRITICAL, MarginalValueTier.HIGH)

    # Scenario B: Dex 180, requires 95 (surplus 85). Candidate +10 Dex -> low value
    baseline_b = CharacterStatBaseline.create_partial(
        baseline_id="b_b", character_id="char_b", anchored_loadout_revision=1,
        dexterity=180
    )
    attr_b = evaluate_contextual_attribute(baseline_b, "dex", delta=10.0, highest_required=95)
    assert attr_b.impact == DeficiencyImpact.UNCHANGED
    assert attr_b.tier == MarginalValueTier.LOW


def test_resistance_deficit_resolves_and_worsens():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b_res", character_id="char_res", anchored_loadout_revision=1,
        fire_res=50, fire_raw=50, max_fire_res=75,
        cold_res=75, cold_raw=75, max_cold_res=75
    )
    # Fire: +25 resolves deficit exactly
    res_resolve = evaluate_contextual_resistance(baseline, ResistanceType.FIRE, delta=25.0)
    assert res_resolve.impact == DeficiencyImpact.RESOLVES
    assert res_resolve.tier == MarginalValueTier.CRITICAL
    assert res_resolve.deficit_before == 25
    assert res_resolve.deficit_after == 0

    # Fire: -10 worsens deficit
    res_worsen = evaluate_contextual_resistance(baseline, ResistanceType.FIRE, delta=-10.0)
    assert res_worsen.impact == DeficiencyImpact.WORSENS
    assert res_worsen.tier == MarginalValueTier.CRITICAL
    assert res_worsen.deficit_before == 25
    assert res_worsen.deficit_after == 35

    # Cold: -10 drops capped resistance below cap, creating new deficiency
    res_create = evaluate_contextual_resistance(baseline, ResistanceType.COLD, delta=-10.0)
    assert res_create.impact == DeficiencyImpact.CREATES_NEW_DEFICIENCY
    assert res_create.tier == MarginalValueTier.CRITICAL
    assert res_create.deficit_before == 0
    assert res_create.deficit_after == 10


def test_resistance_overcap_beyond_buffer_low_value():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b_over", character_id="char_over", anchored_loadout_revision=1,
        fire_res=75, fire_raw=120, max_fire_res=75
    )
    target = ResistanceTarget(target_effective=75, target_overcap_buffer=20, max_res=75)
    # Raw is 120 (45 overcap buffer, well above 20 buffer). Losing 15 keeps 30 buffer.
    res_loss = evaluate_contextual_resistance(baseline, ResistanceType.FIRE, delta=-15.0, target=target)
    assert res_loss.impact == DeficiencyImpact.UNCHANGED
    assert res_loss.tier == MarginalValueTier.LOW
    assert res_loss.deficit_before == 0
    assert res_loss.deficit_after == 0
    assert res_loss.projected_effective == 75
    assert res_loss.overcap_buffer_after == 30

    # Adding +20 more when already at 120 raw is NO_IMMEDIATE_VALUE
    res_add = evaluate_contextual_resistance(baseline, ResistanceType.FIRE, delta=+20.0, target=target)
    assert res_add.impact == DeficiencyImpact.UNCHANGED
    assert res_add.tier == MarginalValueTier.NO_IMMEDIATE_VALUE


def test_resistance_unknown_baseline():
    res_unknown = evaluate_contextual_resistance(None, ResistanceType.FIRE, delta=20.0)
    assert res_unknown.impact == DeficiencyImpact.UNKNOWN
    assert res_unknown.tier == MarginalValueTier.UNKNOWN
    assert res_unknown.is_known is False


def test_attribute_deficit_improved_and_creates_deficiency():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b_attr", character_id="char_attr", anchored_loadout_revision=1,
        strength=70, dexterity=100
    )
    # Str: requires 100, current 70. Delta +15 improves deficit from 30 to 15.
    attr_imp = evaluate_contextual_attribute(baseline, "strength", delta=15.0, highest_required=100)
    assert attr_imp.impact == DeficiencyImpact.IMPROVES
    assert attr_imp.tier == MarginalValueTier.HIGH
    assert attr_imp.deficit_before == 30
    assert attr_imp.deficit_after == 15

    # Dex: requires 95, current 100. Delta -15 drops to 85, creating new deficiency of 10.
    attr_create = evaluate_contextual_attribute(baseline, "dexterity", delta=-15.0, highest_required=95)
    assert attr_create.impact == DeficiencyImpact.CREATES_NEW_DEFICIENCY
    assert attr_create.tier == MarginalValueTier.CRITICAL
    assert attr_create.deficit_before == 0
    assert attr_create.deficit_after == 10


def test_attribute_unknown_baseline():
    attr_unknown = evaluate_contextual_attribute(None, "strength", delta=10.0, highest_required=50)
    assert attr_unknown.impact == DeficiencyImpact.UNKNOWN
    assert attr_unknown.tier == MarginalValueTier.UNKNOWN
    assert attr_unknown.is_known is False


def test_loadout_contextual_analysis_case_d_detection():
    # Case D scenario: character has critical lightning deficit, candidate provides 0 lightning.
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b_case_d", character_id="char_case_d", anchored_loadout_revision=1,
        lightning_res=30, lightning_raw=30, max_lightning_res=75,
        fire_res=75, fire_raw=80, max_fire_res=75,
        cold_res=75, cold_raw=80, max_cold_res=75,
        strength=100, dexterity=100, intelligence=100
    )
    # Candidate provides 0 lightning res, +100 life
    analysis = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={ResistanceType.LIGHTNING: 0.0, ResistanceType.FIRE: 0.0, ResistanceType.COLD: 0.0},
        delta_attrs={"strength": 0.0, "dexterity": 0.0, "intelligence": 0.0},
        highest_attribute_requirements={"strength": 90, "dexterity": 90, "intelligence": 90}
    )
    assert analysis.has_critical_deficiency is True
    assert analysis.has_unchanged_critical_deficiency is True
    assert analysis.has_worsened_deficiency is False
    assert analysis.resistances[ResistanceType.LIGHTNING].deficit_before == 45
    assert analysis.resistances[ResistanceType.LIGHTNING].deficit_after == 45
    assert analysis.resistances[ResistanceType.LIGHTNING].impact == DeficiencyImpact.UNCHANGED
