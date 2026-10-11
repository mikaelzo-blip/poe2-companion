"""Regression pin test for known_rules default rule behaviour on guide import."""

from __future__ import annotations

from pathlib import Path

from companion.builds.guide import BreakerRule
from companion.builds.store import load_guide, set_breaker_rules
from companion.dashboard_api import import_guide_payload

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "guides"


def test_defaults_only_when_no_rules(tmp_path: Path) -> None:
    fubgun_text = (FIX / "fubgun-flameblast-oil-grenade.json").read_text(encoding="utf-8")

    # Initial import installs known default breaker rules
    res1 = import_guide_payload({"text": fubgun_text}, tmp_path)
    assert res1.get("success") is True
    guide1 = load_guide(tmp_path, "fubgun-flameblast-oil-grenade")
    assert guide1 is not None
    assert len(guide1.breaker_rules) > 0

    # Overwrite stored rules with custom rules
    custom_rules = [
        BreakerRule(
            pattern=r"gain .*as extra fire damage",
            from_level=20,
            exclude_slots=["Boots"],
            reason="Custom fire test rule",
        )
    ]
    set_breaker_rules(tmp_path, "fubgun-flameblast-oil-grenade", custom_rules)
    assert load_guide(tmp_path, "fubgun-flameblast-oil-grenade").breaker_rules == custom_rules

    # Importing the Fubgun fixture when stored rules already exist keeps those rules
    res2 = import_guide_payload({"text": fubgun_text}, tmp_path)
    assert res2.get("success") is True
    guide_after = load_guide(tmp_path, "fubgun-flameblast-oil-grenade")
    assert guide_after is not None
    assert guide_after.breaker_rules == custom_rules

    # Importing the Navira fixture gives breaker_rules == []
    navira_text = (FIX / "naviras-fracturing-varashta-league-starter.json").read_text(encoding="utf-8")
    res_navira = import_guide_payload({"text": navira_text}, tmp_path)
    assert res_navira.get("success") is True
    guide_navira = load_guide(tmp_path, "naviras-fracturing-varashta-league-starter")
    assert guide_navira is not None
    assert guide_navira.breaker_rules == []
