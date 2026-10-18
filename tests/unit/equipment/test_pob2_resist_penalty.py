"""Act-based elemental resistance penalty written into the PoB2 baseline XML."""
from __future__ import annotations

from companion.equipment.pob2_equipment_advisor import _set_resist_penalty_in_xml, resist_penalty_for_zone
from tests.unit.equipment.test_pob2_measure import _make

TWO_SETS = (
    '<PathOfBuilding><Config activeConfigSet="2"><ConfigSet id="1"/>'
    '<ConfigSet id="2"><Input name="resistancePenalty" number="-60"/></ConfigSet></Config></PathOfBuilding>'
)


def _penalties(xml: str) -> list[str]:
    return [chunk.split('"')[0] for chunk in xml.split('name="resistancePenalty" number="')[1:]]


def test_penalty_follows_campaign_act():
    assert resist_penalty_for_zone("Clearfell") == 0
    assert resist_penalty_for_zone("The Titan Grotto") == -10
    assert resist_penalty_for_zone("The Azak Bog") == -20
    assert resist_penalty_for_zone("Kingsmarch") == -30
    assert resist_penalty_for_zone("The Refuge") == -50  # interlude (act 6)
    assert resist_penalty_for_zone(None) is None and resist_penalty_for_zone("Felled Hideout") is None


def test_penalty_replaces_the_active_config_set_input_only():
    xml = _set_resist_penalty_in_xml(TWO_SETS, -10)
    assert _penalties(xml) == ["-10"]
    assert '<ConfigSet id="1" />' in xml


def test_penalty_creates_config_when_missing():
    assert _penalties(_set_resist_penalty_in_xml("<PathOfBuilding/>", -20)) == ["-20"]


def test_apply_zone_rebuilds_baseline_once_and_survives_a_resync():
    s = _make()
    assert s.apply_zone("The Titan Grotto") is True
    assert _penalties(s.xml) == ["-10"] and s.resist_penalty == -10
    assert s.apply_zone("The Titan Grotto") is False  # unchanged act: no engine reimport
    assert s.apply_zone("Felled Hideout") is False  # unknown act keeps the last penalty
    assert s.sync_character() is True
    assert _penalties(s.xml) == ["-10"]
