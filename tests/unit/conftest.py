"""Shared evaluation fixtures for unit tests."""

import json
from pathlib import Path

import pytest

from companion.builds.store import set_assignment
from companion.dashboard_api import import_guide_payload
from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "guides"
FUB = "fubgun-flameblast-oil-grenade"


def _item(item_class, base, mods, rarity="Rare", name="Doom Name"):
    return (
        f"Item Class: {item_class}\nRarity: {rarity}\n{name}\n{base}\n--------\n"
        "Requires: Level 10\n--------\n" + "\n".join(mods) + "\n"
    )


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
