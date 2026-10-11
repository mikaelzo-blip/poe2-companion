import pytest

from companion.builds.store import load_guide, save_guide
from companion.equipment.evaluation import evaluate
from tests.unit.eval_helpers import (
    FIX,
    FUB,
    Failing,
    Flat,
    Ring2Empty,
    Stub,
    _install,
    _item,
    _write_char,
)

PROBE_GLOVES = _item("Gloves", "Wool Gloves", ["+40 to maximum Life", "Adds 12 to 22 Fire Damage to Attacks", "+20% to Fire Resistance"])
RING_TEXT = _item("Rings", "Iron Ring", ["+30 to maximum Life", "+10% to Cold Resistance"])
BOOTS_TEXT = _item("Boots", "Wool Shoes", ["+30 to maximum Life", "+10% to Cold Resistance"])
CROSSBOW_TEXT = _item("Crossbows", "Makeshift Crossbow", ["+40 to maximum Life"])


def test_audit_probe_rejected_on_both_engines(tmp_path, positive_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=53)
    for sess in (positive_pob_stub, None):
        r = evaluate(PROBE_GLOVES, "BOMSHAK", runtime_dir=tmp_path, pob_session=sess, source="manual")
        assert r.verdict == "REJECT" and "Oil Grenade" in r.safety[0]


def test_same_probe_not_vetoed_with_navira(tmp_path, positive_pob_stub):
    _install(tmp_path, "naviras-fracturing-varashta-league-starter", char="SORC", level=53)
    r = evaluate(PROBE_GLOVES, "SORC", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="manual")
    assert r.safety == [] and r.verdict == "EQUIP_NOW"


def test_manual_and_auto_identical(tmp_path, positive_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    a = evaluate(RING_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="manual")
    b = evaluate(RING_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="auto")
    assert a.model_dump() == b.model_dump()


def test_tactical_cannot_promote(tmp_path, flat_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    r = evaluate(BOOTS_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=flat_pob_stub, source="manual")
    assert r.verdict == "CONDITIONAL_UPGRADE"


def test_character_only_mode_when_no_guide(tmp_path, positive_pob_stub):
    _write_char(tmp_path, "X", level=30)
    r = evaluate(BOOTS_TEXT, "X", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="manual")
    assert r.guide is None and r.verdict == "EQUIP_NOW"


def test_pob_failure_falls_back_with_reason(tmp_path, failing_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    r = evaluate(BOOTS_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=failing_pob_stub, source="manual")
    assert r.engine == "heuristic" and r.engine_reason


def test_heuristic_weapon_is_insufficient(tmp_path):
    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    r = evaluate(CROSSBOW_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=None, source="manual")
    assert r.verdict == "INSUFFICIENT_DATA"


def test_empty_ring_slot_wins(tmp_path, ring2_empty_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    r = evaluate(RING_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=ring2_empty_stub, source="auto")
    assert r.slot == "Ring 2"


def test_guide_signal_reports_stage_and_priority(tmp_path, positive_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=20)
    r = evaluate(BOOTS_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="manual")
    assert r.guide.stage_title == "lvl 15-32" and r.guide.priority_match is not None


def test_unparseable_item_raises_value_error(tmp_path):
    _write_char(tmp_path, "X", level=30)
    with pytest.raises(ValueError):
        evaluate("not an item", "X", runtime_dir=tmp_path, pob_session=None, source="manual")


def _seed_boots_and_life(tmp_path, char, equipped_text, life=1000):
    from companion.equipment.baseline import BaselineSource, CharacterFact, CharacterStatBaseline
    from companion.equipment.baseline_cli import save_baseline
    from companion.equipment.loadout import EquippedLoadout
    from companion.equipment.loadout_cli import save_loadout
    from companion.equipment.parser import parse_item_text
    from companion.equipment.schema import SlotType
    from companion.state.provenance import VerificationState

    lo = EquippedLoadout.create_draft(character_id=char)
    lo.set_slot(SlotType.BOOTS, parse_item_text(equipped_text, target_slot=SlotType.BOOTS))
    save_loadout(tmp_path, lo)
    base = CharacterStatBaseline.create_empty(character_id=char, anchored_loadout_revision=lo.revision)
    fact = CharacterFact[int](
        value=life, source=BaselineSource.MANUAL_USER_INPUT, observed_at="2026-01-01T00:00:00+00:00",
        verification=VerificationState.VERIFIED,
    )
    save_baseline(tmp_path, base.model_copy(update={"life": fact}))


def test_heuristic_path_projects_life_from_baseline_and_loadout(tmp_path):
    _write_char(tmp_path, "H", level=30)
    old = _item("Boots", "Wool Shoes", ["+5% to Cold Resistance"], name="Old Tread")
    _seed_boots_and_life(tmp_path, "H", old)
    r = evaluate(BOOTS_TEXT, "H", runtime_dir=tmp_path, pob_session=None, source="manual")
    assert r.engine == "heuristic" and r.engine_reason == "PoB2 tidak tersedia"
    assert r.verdict == "EQUIP_NOW" and r.slot == "Boots"
    assert r.dims["life"] == 30 and r.dims["ehp_pct"] == pytest.approx(0.03)
    assert r.dims["dps_pct"] == 0 and r.dims["cold_res"] == 5


def test_already_equipped_detects_same_rare_but_not_magic(tmp_path):
    _write_char(tmp_path, "A", level=30)
    _seed_boots_and_life(tmp_path, "A", BOOTS_TEXT)
    r = evaluate(BOOTS_TEXT, "A", runtime_dir=tmp_path, pob_session=None, source="manual")
    assert r.verdict == "ALREADY_EQUIPPED" and r.slot == "Boots"
    magic = _item("Boots", "Wool Shoes", ["+30 to maximum Life"], rarity="Magic", name="Sturdy Wool Shoes of Life")
    _seed_boots_and_life(tmp_path, "A", magic)
    r = evaluate(magic, "A", runtime_dir=tmp_path, pob_session=None, source="manual")
    assert r.verdict != "ALREADY_EQUIPPED"


class LethalResDrop(Stub):
    """Clearly EQUIP_NOW by policy (+5% DPS, +3% EHP, no cap breach) but loses fire res in a fire-lethal zone."""

    def measure(self, slot, raw, candidate_id, **kw):
        return super().measure(slot, raw, candidate_id, **kw).model_copy(update={"fire_res_delta": -10})


def test_tactical_zone_veto_downgrades_equip_now_to_reject(tmp_path):
    _write_char(tmp_path, "X", level=19)
    r = evaluate(BOOTS_TEXT, "X", runtime_dir=tmp_path, pob_session=LethalResDrop(), source="manual", zone="G2_1")
    assert r.per_slot[0].verdict == "EQUIP_NOW"  # policy alone would equip
    assert r.verdict == "REJECT"
    assert r.tactical_advice["tactical_headline"] in r.reasons


def test_already_equipped_has_indonesian_reason(tmp_path):
    _write_char(tmp_path, "A", level=30)
    _seed_boots_and_life(tmp_path, "A", BOOTS_TEXT)
    r = evaluate(BOOTS_TEXT, "A", runtime_dir=tmp_path, pob_session=None, source="manual")
    assert r.reasons == ["Item ini sudah terpasang di Boots"]


def test_guide_signal_carries_priority_counts(tmp_path, positive_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=20)
    r = evaluate(BOOTS_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="manual")
    assert r.guide.priority_matched == 0
    assert r.guide.priority_total == 1
    assert r.guide.priority_match == 0 / 1


def test_already_equipped_has_chosen_per_slot(tmp_path):
    _write_char(tmp_path, "A", level=30)
    _seed_boots_and_life(tmp_path, "A", BOOTS_TEXT)
    r = evaluate(BOOTS_TEXT, "A", runtime_dir=tmp_path, pob_session=None, source="manual")
    assert r.verdict == "ALREADY_EQUIPPED"
    assert [s.slot for s in r.per_slot] == [r.slot]


def test_current_item_base_type_on_result(tmp_path):
    _write_char(tmp_path, "H", level=30)
    old = _item("Boots", "Wool Shoes", ["+5% to Cold Resistance"], name="Old Tread")
    _seed_boots_and_life(tmp_path, "H", old)
    r = evaluate(BOOTS_TEXT, "H", runtime_dir=tmp_path, pob_session=None, source="manual")
    assert r.current_item_base_type == "Wool Shoes"


def test_target_fit_on_pob_stage(tmp_path, positive_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    profile = load_guide(tmp_path, FUB)
    save_guide(tmp_path, profile, pob_xml="<PathOfBuilding><ItemSet id='1'/></PathOfBuilding>")
    pob_stage = profile.pob_stage_id
    assert pob_stage is not None

    r = evaluate(
        BOOTS_TEXT,
        "BOMSHAK",
        runtime_dir=tmp_path,
        pob_session=positive_pob_stub,
        source="manual",
        stage_override=pob_stage,
    )
    assert r.verdict == "EQUIP_NOW"
    assert r.guide is not None
    assert r.guide.target_fit == {
        "dps_pct": pytest.approx(0.10),
        "ehp_pct": pytest.approx(0.04),
    }

    # Compare against run without guide XML (verdict unchanged)
    (tmp_path / "guides" / f"{FUB}.xml").unlink()
    r_no_xml = evaluate(
        BOOTS_TEXT,
        "BOMSHAK",
        runtime_dir=tmp_path,
        pob_session=positive_pob_stub,
        source="manual",
        stage_override=pob_stage,
    )
    assert r.verdict == r_no_xml.verdict


def test_no_guide_measure_off_pob_stage(tmp_path, positive_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=20)
    profile = load_guide(tmp_path, FUB)
    save_guide(tmp_path, profile, pob_xml="<PathOfBuilding><ItemSet id='1'/></PathOfBuilding>")
    # level 20 resolves to stage "1" (lvl 15-32), not pob_stage_id ("DoT Cap")
    r = evaluate(
        BOOTS_TEXT,
        "BOMSHAK",
        runtime_dir=tmp_path,
        pob_session=positive_pob_stub,
        source="manual",
    )
    assert all(c.get("base_xml") is None for c in positive_pob_stub.calls)
    assert r.guide is not None
    assert r.guide.target_fit is None


def test_target_fit_none_when_guide_xml_missing(tmp_path, positive_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    profile = load_guide(tmp_path, FUB)
    pob_stage = profile.pob_stage_id
    assert profile.has_pob is True
    # Delete the .xml file
    (tmp_path / "guides" / f"{FUB}.xml").unlink(missing_ok=True)

    r = evaluate(
        BOOTS_TEXT,
        "BOMSHAK",
        runtime_dir=tmp_path,
        pob_session=positive_pob_stub,
        source="manual",
        stage_override=pob_stage,
    )
    assert r.guide is not None
    assert r.guide.target_fit is None
    assert r.verdict == "EQUIP_NOW"


def test_target_fit_failure_keeps_verdict(tmp_path, positive_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    profile = load_guide(tmp_path, FUB)
    save_guide(tmp_path, profile, pob_xml="<PathOfBuilding><ItemSet id='1'/></PathOfBuilding>")
    pob_stage = profile.pob_stage_id

    # Baseline run
    r_baseline = evaluate(
        BOOTS_TEXT,
        "BOMSHAK",
        runtime_dir=tmp_path,
        pob_session=positive_pob_stub,
        source="manual",
        stage_override=pob_stage,
    )

    # 1. Stub returns None for base_xml
    positive_pob_stub.none_guide = True
    r_none = evaluate(
        BOOTS_TEXT,
        "BOMSHAK",
        runtime_dir=tmp_path,
        pob_session=positive_pob_stub,
        source="manual",
        stage_override=pob_stage,
    )
    assert r_none.guide is not None
    assert r_none.guide.target_fit is None
    assert r_none.verdict == r_baseline.verdict
    assert [s.model_dump() for s in r_none.per_slot] == [s.model_dump() for s in r_baseline.per_slot]

    # 2. Stub raises exception for base_xml
    positive_pob_stub.none_guide = False
    positive_pob_stub.fail_guide = True
    r_raise = evaluate(
        BOOTS_TEXT,
        "BOMSHAK",
        runtime_dir=tmp_path,
        pob_session=positive_pob_stub,
        source="manual",
        stage_override=pob_stage,
    )
    assert r_raise.guide is not None
    assert r_raise.guide.target_fit is None
    assert r_raise.verdict == r_baseline.verdict
    assert [s.model_dump() for s in r_raise.per_slot] == [s.model_dump() for s in r_baseline.per_slot]





def test_target_fit_none_when_guide_xml_unreadable(tmp_path, positive_pob_stub, monkeypatch):
    import companion.equipment.evaluation as ev

    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    profile = load_guide(tmp_path, FUB)
    save_guide(tmp_path, profile, pob_xml="<PathOfBuilding><ItemSet id='1'/></PathOfBuilding>")

    def boom(*_a, **_k):
        raise OSError("disk read failed")

    monkeypatch.setattr(ev, "load_guide_xml", boom)
    r = evaluate(BOOTS_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=positive_pob_stub,
                 source="manual", stage_override=profile.pob_stage_id)
    assert r.verdict == "EQUIP_NOW"
    assert r.guide.target_fit is None


def test_fubgun_lvl60_crossbow_fire_breaker_rejected_in_set2(tmp_path):
    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    xbow = _item("Crossbows", "Makeshift Crossbow", ["Adds 12 to 22 Fire Damage to Attacks", "+40 to maximum Life"])
    r = evaluate(xbow, "BOMSHAK", runtime_dir=tmp_path, pob_session=None, source="manual")
    assert r.slot == "Weapon 1 Swap"
    assert r.verdict == "REJECT"
    assert any("Oil Grenade" in s for s in r.safety)


def test_fubgun_lvl20_preswap_crossbow_routes_to_set1_without_veto(tmp_path, positive_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=20)
    xbow = _item("Crossbows", "Makeshift Crossbow", ["Adds 12 to 22 Fire Damage to Attacks", "+40 to maximum Life"])
    r = evaluate(xbow, "BOMSHAK", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="manual")
    assert r.slot == "Weapon 1"
    assert r.verdict == "EQUIP_NOW"
    assert r.safety == []


def test_fubgun_lvl60_non_attack_fire_ring_not_vetoed(tmp_path, positive_pob_stub):
    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    ring = _item("Rings", "Iron Ring", ["25% increased Fire Damage", "Adds 10 to 20 Fire Damage to Spells", "+30 to maximum Life"])
    r = evaluate(ring, "BOMSHAK", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="manual")
    assert r.slot == "Ring 1"
    assert r.verdict == "EQUIP_NOW"
    assert r.safety == []


def test_fubgun_lvl60_bow_rejected_off_guide(tmp_path):
    _install(tmp_path, FUB, char="BOMSHAK", level=60)
    bow = _item("Bows", "Short Bow", ["+10 to Dexterity"])
    r = evaluate(bow, "BOMSHAK", runtime_dir=tmp_path, pob_session=None, source="manual")
    assert r.slot == "Weapon 1"
    assert r.verdict == "REJECT"
    assert "Senjata tidak dipakai guide (Bow)" in r.reasons

