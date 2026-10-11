from pathlib import Path

import pytest

from companion.builds.guide import BreakerRule
from companion.builds.known_rules import KNOWN_RULES
from companion.builds.store import load_guide
from companion.dashboard_api import import_guide_payload
from companion.equipment.safety import breaker_reasons, weapon_not_in_guide

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "guides"
PROBE = ["+40 to maximum Life", "Adds 12 to 22 Fire Damage to Attacks", "+20% to Fire Resistance"]
FUB = "fubgun-flameblast-oil-grenade"


def _load(tmp_path, slug):
    import_guide_payload({"text": (FIX / f"{slug}.json").read_text(encoding="utf-8")}, tmp_path)
    return load_guide(tmp_path, slug)


@pytest.fixture
def fubgun(tmp_path):
    return _load(tmp_path, FUB)


@pytest.fixture
def navira(tmp_path):
    return _load(tmp_path, "naviras-fracturing-varashta-league-starter")


def test_audit_probe_gloves_rejected_for_fubgun_post_swap(fubgun):
    assert breaker_reasons(PROBE, fubgun, 53, "Gloves") == [KNOWN_RULES[FUB][0].reason]


def test_probe_safe_pre_swap_and_in_set1(fubgun):
    assert breaker_reasons(PROBE, fubgun, 40, "Gloves") == []
    assert breaker_reasons(PROBE, fubgun, 60, "Weapon 1") == []


def test_probe_not_vetoed_for_navira(navira):
    assert breaker_reasons(PROBE, navira, 53, "Gloves") == []


def test_unknown_level_applies_and_no_profile(fubgun):
    assert breaker_reasons(PROBE, fubgun, None, "Gloves")
    assert breaker_reasons(PROBE, None, 60, "Gloves") == []


def test_weapon_not_in_guide(fubgun):
    assert weapon_not_in_guide("Bow", fubgun) == "Senjata tidak dipakai guide (Bow)"
    assert weapon_not_in_guide("Crossbow", fubgun) is None
    assert weapon_not_in_guide("Gloves", fubgun) is None
    assert weapon_not_in_guide("Bow", None) is None


def test_breaker_rule_rejects_unknown_slot_and_level():
    with pytest.raises(ValueError):
        BreakerRule(pattern="x", reason="r", exclude_slots=["Hat"])
    with pytest.raises(ValueError):
        BreakerRule(pattern="x", reason="r", from_level=0)
    with pytest.raises(ValueError):
        BreakerRule(pattern="x", reason="r", from_level=101)
