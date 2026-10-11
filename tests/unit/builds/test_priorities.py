import pytest

from companion.builds.guide import StageItem
from companion.builds.priorities import mod_family, priority_signal


def test_priority_signal_counts_families_and_missing_must_have():
    item = StageItem(slot="Boots", name="Leather Boots", item_class="Boots",
                     mods=["+30 to maximum Life", "25% increased Movement Speed", "+20% to Fire Resistance"],
                     must_have=["25% increased Movement Speed"])
    sig = priority_signal(item, ["+52 to maximum Life", "+31% to Fire Resistance"])
    assert (sig.matched, sig.total) == (2, 3)
    assert sig.must_have_missing == ["25% increased Movement Speed"]
    assert sig.ratio == pytest.approx(2 / 3)


def test_unknown_mod_family_ignores_numbers():
    assert mod_family("Gain 12(10-15) Rage on Hit") == mod_family("Gain 3 Rage on Hit")


def test_priority_signal_none_without_stage_item():
    assert priority_signal(None, ["+5 to Strength"]) is None


def test_mod_family_ignores_clipboard_tags():
    assert mod_family("Adds 1 to 4 Physical Damage to Attacks (implicit)") == mod_family("Adds 2 to 4 Physical Damage to Attacks")
    assert mod_family("+20 to Spirit (rune)") == mod_family("+30 to Spirit")


def test_mod_family_keeps_ranges_numeric():
    assert mod_family("Gain 12(10-15) Rage on Hit (implicit)") == mod_family("Gain 3 Rage on Hit")


def test_priority_signal_matches_implicit_candidate():
    item = StageItem(slot="Ring 1", name="Iron Ring", item_class="Ring",
                     mods=["Adds 2 to 4 Physical Damage to Attacks"])
    assert priority_signal(item, ["Adds 1 to 4 Physical Damage to Attacks (implicit)"]).matched == 1

