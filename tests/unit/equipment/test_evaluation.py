import json
from pathlib import Path

import pytest

from companion.builds.store import set_assignment
from companion.dashboard_api import import_guide_payload
from companion.equipment.evaluation import evaluate
from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "guides"
FUB = "fubgun-flameblast-oil-grenade"


def _item(item_class, base, mods, rarity="Rare", name="Doom Name"):
    return (
        f"Item Class: {item_class}\nRarity: {rarity}\n{name}\n{base}\n--------\n"
        "Requires: Level 10\n--------\n" + "\n".join(mods) + "\n"
    )


PROBE_GLOVES = _item("Gloves", "Wool Gloves", ["+40 to maximum Life", "Adds 12 to 22 Fire Damage to Attacks", "+20% to Fire Resistance"])
RING_TEXT = _item("Rings", "Iron Ring", ["+30 to maximum Life", "+10% to Cold Resistance"])
BOOTS_TEXT = _item("Boots", "Wool Shoes", ["+30 to maximum Life", "+10% to Cold Resistance"])
CROSSBOW_TEXT = _item("Crossbows", "Makeshift Crossbow", ["+40 to maximum Life"])


def _write_char(tmp_path, char, level):
    d = tmp_path / "characters"
    d.mkdir(exist_ok=True)
    (d / f"{char}.json").write_text(json.dumps({"level": {"value": level}}), encoding="utf-8")


def _install(tmp_path, slug, char, level):
    import_guide_payload({"text": (FIX / f"{slug}.json").read_text(encoding="utf-8")}, tmp_path)
    _write_char(tmp_path, char, level)
    set_assignment(tmp_path, char, slug, None)


class Stub:
    is_available = True
    level = None
    dps_gain = 0.05
    ehp_gain = 0.03
    empty_slots: tuple[str, ...] = ()
    fail = False

    def submit_candidate(self, raw, candidate_name="", slot="Helmet", source="manual"):
        return 7

    def measure(self, slot, raw, candidate_id, *, source="manual", clear_slots=(), candidate_name=""):
        if self.fail:
            raise RuntimeError("pob exploded")
        return PobEquipmentDelta(
            slot=slot, candidate_id=candidate_id, candidate_name="x",
            dps_before=1000.0, dps_after=1000.0 * (1 + self.dps_gain),
            ehp_before=5000.0, ehp_after=5000.0 * (1 + self.ehp_gain), life_before=1000, life_after=1030,
            life_delta=30, res_before={"fire": 75}, res_after={"fire": 75},
        )

    def is_slot_empty(self, slot):
        return slot in self.empty_slots

    def get_equipped_item(self, slot):
        return None

    def get_current_item_name(self, slot):
        return None


class Flat(Stub):
    dps_gain, ehp_gain = 0.005, 0.0


class Failing(Stub):
    fail = True


class Ring2Empty(Stub):
    empty_slots = ("Ring 2",)


@pytest.fixture
def positive_pob_stub():
    return Stub()


@pytest.fixture
def flat_pob_stub():
    return Flat()


@pytest.fixture
def failing_pob_stub():
    return Failing()


@pytest.fixture
def ring2_empty_stub():
    return Ring2Empty()


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
