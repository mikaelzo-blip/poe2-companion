import threading
import time
from unittest.mock import MagicMock

from companion.equipment.baseline import BaselineSource, CharacterFact, CharacterStatBaseline
from companion.equipment.baseline_cli import load_baseline, save_baseline
from companion.equipment.loadout_cli import get_loadout_history_dir, load_loadout
from companion.equipment.schema import SlotType, WeaponSetContext
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
    sess.equipped_items = {"Helmet": {"equipped": True, "raw": raw}, "Boots": {"equipped": False}}
    sess.get_equipped_item.side_effect = lambda s: sess.equipped_items.get(s, {"equipped": False})
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


STAFF_RAW = """Item Class: Staves
Rarity: Rare
Doom Song
Gothic Staff
--------
Item Level: 20
--------
+10 to maximum Mana
"""
BOOTS_RAW = """Item Class: Boots
Rarity: Rare
Brimstone Greaves
Iron Greaves
--------
Armour: 52
--------
Requirements:
Level: 14
Str: 12
--------
+16% to Fire Resistance
+18 to maximum Life
"""


def test_weapon_and_swap_slots_map_to_weapon_sets(tmp_path):
    sess = _sess()
    sess.equipped_items = {
        "Weapon 1": {"equipped": True, "raw": STAFF_RAW},
        "Weapon 1 Swap": {"equipped": True, "raw": STAFF_RAW.replace("Doom Song", "Swap Song")},
    }
    assert apply_session_to_runtime(tmp_path, "T", sess) == []
    lo = load_loadout(tmp_path, "T")
    assert lo.weapon_set_1[SlotType.MAIN_HAND.value].item.name == "Doom Song"
    assert lo.weapon_set_2[SlotType.MAIN_HAND.value].item.name == "Swap Song"


def test_finalized_loadout_multi_slot_change_bumps_revision_once_with_snapshot(tmp_path):
    apply_session_to_runtime(tmp_path, "T", _sess())
    assert load_loadout(tmp_path, "T").revision == 1
    sess = _sess(HELM_RAW.replace("Brimstone Veil", "Other Veil"))
    sess.equipped_items["Boots"] = {"equipped": True, "raw": BOOTS_RAW}
    apply_session_to_runtime(tmp_path, "T", sess)
    lo = load_loadout(tmp_path, "T")
    assert lo.revision == 2
    assert len(list(get_loadout_history_dir(tmp_path, "T").glob("rev_*.json"))) == 1


def test_decision_equal_item_gets_pob_raw_text_without_revision_bump(tmp_path):
    apply_session_to_runtime(tmp_path, "T", _sess())
    new_raw = HELM_RAW.replace("Rare\n", "Rare\n\n", 1)  # cosmetic blank line, same item
    apply_session_to_runtime(tmp_path, "T", _sess(new_raw))
    lo = load_loadout(tmp_path, "T")
    assert lo.revision == 1
    assert lo.get_slot(SlotType.HELMET).item.raw_text == new_raw.strip()


def test_apply_waits_for_character_runtime_lock(tmp_path):
    from companion.equipment.loadout_cli import character_runtime_lock
    lock = character_runtime_lock("T")
    lock.acquire()
    t = threading.Thread(target=apply_session_to_runtime, args=(tmp_path, "T", _sess()))
    t.start()
    time.sleep(0.3)
    assert load_baseline(tmp_path, "T") is None
    lock.release()
    t.join(5)
    assert load_baseline(tmp_path, "T") is not None
