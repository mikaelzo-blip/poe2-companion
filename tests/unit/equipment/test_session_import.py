import json
import threading
from pathlib import Path
import time
from unittest.mock import MagicMock

from companion.equipment.baseline import BaselineSource, CharacterFact, CharacterStatBaseline
from companion.equipment.baseline_cli import load_baseline, save_baseline
from companion.equipment.loadout_cli import get_loadout_history_dir, load_loadout, save_loadout
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.pob_item_text import pob_item_to_clipboard
from companion.equipment.session_import import apply_session_to_runtime

# Real engine get_equipped output (tests/fixtures/pob); PoB's internal format, not clipboard text.
EQUIPPED = json.loads((Path(__file__).parents[2] / "fixtures" / "pob" / "get_equipped.json").read_text(encoding="utf-8"))
HELM_RAW = EQUIPPED["Helmet"]["raw"]
STAFF_RAW = EQUIPPED["Weapon 1"]["raw"]
BOOTS_RAW = EQUIPPED["Boots"]["raw"]


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
    text = lo.get_slot(SlotType.HELMET).item.raw_text
    assert text == pob_item_to_clipboard(HELM_RAW).strip() and text.startswith("Item Class: Helmets\nRarity: Rare")
    assert "{" not in text and "Evasion Rating: 37" in text
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


def test_weapon_and_swap_slots_map_to_weapon_sets(tmp_path):
    sess = _sess()
    sess.equipped_items = {
        "Weapon 1": {"equipped": True, "raw": STAFF_RAW},
        "Weapon 1 Swap": {"equipped": True, "raw": STAFF_RAW.replace("Cataclysm Call", "Swap Song")},
    }
    assert apply_session_to_runtime(tmp_path, "T", sess) == []
    lo = load_loadout(tmp_path, "T")
    assert lo.weapon_set_1[SlotType.MAIN_HAND.value].item.name == "Cataclysm Call"
    assert lo.weapon_set_2[SlotType.MAIN_HAND.value].item.name == "Swap Song"


def test_finalized_loadout_multi_slot_change_bumps_revision_once_with_snapshot(tmp_path):
    apply_session_to_runtime(tmp_path, "T", _sess())
    assert load_loadout(tmp_path, "T").revision == 1
    sess = _sess(HELM_RAW.replace("Plague Crest", "Other Crest"))
    sess.equipped_items["Boots"] = {"equipped": True, "raw": BOOTS_RAW}
    apply_session_to_runtime(tmp_path, "T", sess)
    lo = load_loadout(tmp_path, "T")
    assert lo.revision == 2
    assert len(list(get_loadout_history_dir(tmp_path, "T").glob("rev_*.json"))) == 1


def test_decision_equal_item_gets_pob_raw_text_without_revision_bump(tmp_path):
    apply_session_to_runtime(tmp_path, "T", _sess())
    lo = load_loadout(tmp_path, "T")
    entry = lo.get_slot(SlotType.HELMET)
    lo.shared_slots[SlotType.HELMET.value] = entry.model_copy(update={"item": entry.item.model_copy(update={"raw_text": "importer text"})})
    save_loadout(tmp_path, lo)
    apply_session_to_runtime(tmp_path, "T", _sess())
    lo = load_loadout(tmp_path, "T")
    assert lo.revision == 1
    assert lo.get_slot(SlotType.HELMET).item.raw_text == pob_item_to_clipboard(HELM_RAW).strip()


def test_pob_item_with_fewer_known_mods_never_replaces_stored_item(tmp_path, caplog):
    apply_session_to_runtime(tmp_path, "T", _sess())
    before = load_loadout(tmp_path, "T").get_slot(SlotType.HELMET).item
    degraded = HELM_RAW.split("Implicits: 0\n")[0] + "Implicits: 0\nzzz qqq unrecognised line"
    with caplog.at_level("WARNING"):
        for _ in range(2):
            apply_session_to_runtime(tmp_path, "T", _sess(degraded))
    lo = load_loadout(tmp_path, "T")
    assert lo.revision == 1 and lo.get_slot(SlotType.HELMET).item == before
    assert sum("fewer known mods" in r.message for r in caplog.records) == 1


def test_attribute_requirements_survive_when_same_item_is_reimported(tmp_path):
    from companion.equipment.loadout_cli import load_loadout as _ld
    apply_session_to_runtime(tmp_path, "T", _sess())
    lo = _ld(tmp_path, "T")
    entry = lo.get_slot(SlotType.HELMET)
    lo.shared_slots[SlotType.HELMET.value] = entry.model_copy(update={"item": entry.item.model_copy(update={"required_dex": 10})})
    save_loadout(tmp_path, lo)
    apply_session_to_runtime(tmp_path, "T", _sess())
    lo = _ld(tmp_path, "T")
    assert lo.revision == 1 and lo.get_slot(SlotType.HELMET).item.required_dex == 10


def test_slot_pob_reports_unequipped_is_cleared_through_transition(tmp_path):
    sess = _sess()
    sess.equipped_items["Boots"] = {"equipped": True, "raw": BOOTS_RAW}
    apply_session_to_runtime(tmp_path, "T", sess)
    assert load_loadout(tmp_path, "T").get_slot(SlotType.BOOTS) is not None
    apply_session_to_runtime(tmp_path, "T", _sess())  # Boots now {"equipped": False}
    lo = load_loadout(tmp_path, "T")
    assert lo.get_slot(SlotType.BOOTS) is None and lo.revision == 2
    assert len(list(get_loadout_history_dir(tmp_path, "T").glob("rev_*.json"))) == 1


def test_preserved_manual_facts_go_stale_when_gear_changes(tmp_path):
    from companion.equipment.baseline_gate import check_baseline_consistency
    from companion.state.provenance import VerificationState
    apply_session_to_runtime(tmp_path, "T", _sess())
    base = load_baseline(tmp_path, "T")
    base.life = CharacterFact[int].create(500, source=BaselineSource.MANUAL_USER_INPUT)
    save_baseline(tmp_path, base)
    # unchanged gear: manual fact stays as entered
    apply_session_to_runtime(tmp_path, "T", _sess())
    assert load_baseline(tmp_path, "T").life.verification == VerificationState.VERIFIED
    # gear changes: manual value kept but no longer certified
    sess = _sess()
    sess.equipped_items["Boots"] = {"equipped": True, "raw": BOOTS_RAW}
    apply_session_to_runtime(tmp_path, "T", sess)
    b, lo = load_baseline(tmp_path, "T"), load_loadout(tmp_path, "T")
    assert b.life.value == 500 and b.life.source == BaselineSource.MANUAL_USER_INPUT
    assert b.life.verification == VerificationState.STALE
    assert b.armour.verification == VerificationState.VERIFIED  # fresh PoB value
    assert check_baseline_consistency(b, lo.revision, lo.compute_fingerprint()).is_consistent


def test_manual_raw_res_keeps_effective_pair_coherent(tmp_path):
    base = CharacterStatBaseline(baseline_id="b", character_id="T", anchored_loadout_revision=1)
    base.raw_fire_res = CharacterFact[int].create(23, source=BaselineSource.MANUAL_USER_INPUT)
    save_baseline(tmp_path, base)
    apply_session_to_runtime(tmp_path, "T", _sess())
    b = load_baseline(tmp_path, "T")
    assert b.raw_fire_res.value == 23 and b.effective_fire_res.value is None


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
