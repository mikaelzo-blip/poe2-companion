from unittest.mock import MagicMock

from companion.equipment.baseline import BaselineSource, CharacterFact, CharacterStatBaseline
from companion.equipment.baseline_cli import load_baseline, save_baseline
from companion.equipment.loadout_cli import load_loadout
from companion.equipment.schema import SlotType
from companion.equipment.session_import import apply_session_to_runtime

HELM_RAW = """Item Class: Helmets
Rarity: Rare
Brimstone Veil
Advanced Chain Tiara
--------
Evasion Rating: 28
Energy Shield: 16
--------
Requirements:
Level: 14
Dex: 15
Int: 15
--------
Item Level: 18
--------
+35 to Accuracy Rating
+18 to maximum Mana
1.5 Life Regenerated per second
11% increased Item Rarity
"""


def _sess(raw=HELM_RAW):
    sess = MagicMock()
    sess.get_equipped_item.side_effect = lambda s: (
        {"equipped": True, "raw": raw} if s == "Helmet" else {"equipped": False}
    )
    sess.defenses_before = {"Life": 812, "Armour": 300, "Evasion": 450, "EnergyShield": 60, "Mana": 120}
    sess.stats_before = {"defense": {"FireResist": 82, "ColdResist": 40, "LightningResist": 75, "ChaosResist": -10}}
    return sess


def test_apply_session_writes_pob_item_text_and_baseline(tmp_path):
    assert apply_session_to_runtime(tmp_path, "T", _sess()) == []
    lo = load_loadout(tmp_path, "T")
    assert lo.get_slot(SlotType.HELMET).item.raw_text.strip() == HELM_RAW.strip()
    b = load_baseline(tmp_path, "T")
    assert b.life.value == 812 and b.raw_fire_res.value == 82 and b.effective_fire_res.value == 75
    assert b.raw_chaos_res.value == -10 and b.effective_chaos_res.value == -10
    assert b.life.source == BaselineSource.DERIVED_CALCULATION and b.life.evidence_ref == "pob2"


def test_apply_session_never_overwrites_manual_fact(tmp_path):
    base = CharacterStatBaseline(baseline_id="b", character_id="T", anchored_loadout_revision=1)
    base.life = CharacterFact[int].create(500, source=BaselineSource.MANUAL_USER_INPUT)
    save_baseline(tmp_path, base)
    apply_session_to_runtime(tmp_path, "T", _sess())
    b = load_baseline(tmp_path, "T")
    assert b.life.value == 500 and b.armour.value == 300


def test_apply_session_reports_unparseable_item_as_warning(tmp_path):
    warnings = apply_session_to_runtime(tmp_path, "T", _sess("garbage"))
    assert len(warnings) == 1 and "Helmet" in warnings[0]
