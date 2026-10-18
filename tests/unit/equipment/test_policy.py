import pytest

from companion.builds.priorities import PrioritySignal
from companion.equipment.policy import VERDICT_RANK, decide, insufficient, rejected
from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta


def _delta(dps_b, dps_a, ehp_b, ehp_a, res_b=None, res_a=None, **extra):
    return PobEquipmentDelta(
        slot="Gloves", candidate_id=1, candidate_name="x",
        dps_before=dps_b, dps_after=dps_a, dps_delta=dps_a - dps_b,
        ehp_before=ehp_b, ehp_after=ehp_a, ehp_delta=ehp_a - ehp_b,
        res_before=res_b or {}, res_after=res_a or {}, **extra,
    )


@pytest.mark.parametrize("dps_b,dps_a,ehp_b,ehp_a,res_b,res_a,unmet,expected", [
    (1000, 1010, 500, 496, {}, {}, [], "EQUIP_NOW"),            # +1% DPS, -0.8% EHP
    (1000, 996, 500, 510, {}, {}, [], "EQUIP_NOW"),             # +2% EHP, -0.4% DPS
    (1000, 990, 500, 500, {}, {}, [], "REJECT"),                # -1% DPS, EHP flat
    (1000, 1005, 500, 500, {}, {}, [], "CONDITIONAL_UPGRADE"),  # below both bars
    (1000, 1000, 500, 500, {"fire": 75}, {"fire": 68}, [], "REJECT"),
    (1000, 1020, 500, 500, {"fire": 75}, {"fire": 68}, [], "CONDITIONAL_UPGRADE"),
    (1000, 1100, 500, 600, {}, {}, ["Level 40/42"], "REJECT"),
    (0, 5, 0, 0, {}, {}, [], "EQUIP_NOW"),                      # level-1 baseline: no ZeroDivisionError
    (100, 12, 1000, 1016, {}, {}, [], "REJECT"),                # BOMSHAK crossbow: -88% DPS, +1.6% EHP
    (100, 79, 1000, 1049, {}, {}, [], "REJECT"),                # -21% DPS, +4.9% EHP
    (100, 79, 1000, 1050, {}, {}, [], "CONDITIONAL_UPGRADE"),   # -21% DPS, +5% EHP compensates
    (100, 80, 1000, 1016, {}, {}, [], "CONDITIONAL_UPGRADE"),   # -20% DPS is not beyond the bar
])
def test_policy_table(dps_b, dps_a, ehp_b, ehp_a, res_b, res_a, unmet, expected):
    d = _delta(dps_b, dps_a, ehp_b, ehp_a, res_b, res_a)
    assert decide(d, unmet_requirements=unmet).verdict == expected


def test_must_have_caps_equip_now():
    sig = PrioritySignal(matched=1, total=2, must_have_missing=["25% increased Movement Speed"])
    r = decide(_delta(1000, 1100, 500, 600), priority=sig)
    assert r.verdict == "CONDITIONAL_UPGRADE"
    assert "Prioritas guide kurang: 25% increased Movement Speed" in r.trade_offs
    assert r.reasons == ["Mod wajib dari guide belum ada.", "Peningkatan melewati ambang tanpa trade-off besar."]


def test_percent_labels():
    r = decide(_delta(1000, 1032, 500, 500))
    assert "+3.2% DPS" in r.gains
    assert not any("EHP" in t for t in r.gains + r.trade_offs)  # zero pct is not listed


def test_flat_stats_and_breach_texts():
    d = _delta(1000, 1000, 500, 510, {"fire": 75}, {"fire": 68}, life_delta=25, fire_res_delta=-12,
               crit_chance_delta=2.5, average_hit_pct=-4.24)
    r = decide(d, unmet_requirements=["Level 40/42"])
    assert r.gains == ["+2.0% EHP", "+25 maximum Life", "+2.5% Critical Hit Chance"]
    assert r.trade_offs == [
        "-12% Fire Resistance", "-4.2% Average Hit", "Fire Resistance turun di bawah cap (75% → 68%)",
        "Kebutuhan belum terpenuhi: Level 40/42",
    ]
    assert r.delta is d and r.reasons


def test_helpers_and_rank():
    assert insufficient("Helmet", "x").verdict == "INSUFFICIENT_DATA"
    r = rejected("Helmet", ["a", "b"])
    assert (r.verdict, r.reasons) == ("REJECT", ["a", "b"])
    assert VERDICT_RANK["EQUIP_NOW"] > VERDICT_RANK["CONDITIONAL_UPGRADE"] > VERDICT_RANK["INSUFFICIENT_DATA"] > VERDICT_RANK["REJECT"]


def test_deltas_that_round_to_zero_are_not_listed():
    r = decide(_delta(1000, 1000, 500, 500, average_hit_pct=0.04, movement_speed_delta=-1e-9))
    assert r.gains == [] and r.trade_offs == []
