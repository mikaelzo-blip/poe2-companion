"""Unit tests for build-agnostic WeaponTopologyResolver and canonical weapon compatibility.

Enforces:
- Regressions A, B, C, D, E, F, and H.
- Build-agnostic invariant: WeaponTopologyResolver has no build-specific policy
  or stage dependencies.
"""

import pytest
from companion.equipment.parser import parse_item_text
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.weapon_topology import (
    WeaponArchetype,
    WeaponTopologyPlan,
    WeaponTopologyResolver,
    derive_weapon_archetype,
)

STAFF_TEXT = """Item Class: Two Hand Staves
Rarity: Rare
Volcano Pillar
Chiming Staff
--------
Physical Damage: 45-93
--------
Requirements:
Level: 52
--------
+20% to Fire Resistance
"""

CROSSBOW_TEXT = """Item Class: Crossbows
Rarity: Rare
Gloom Piercer
Bombard Crossbow
--------
Physical Damage: 30-75
--------
Requirements:
Level: 52
--------
+15% to Attack Speed
"""

BOW_TEXT = """Item Class: Bows
Rarity: Rare
Wind Bow
Short Bow
--------
Requirements:
Level: 30
--------
+10 to Dexterity
"""

QUIVER_TEXT = """Item Class: Quivers
Rarity: Rare
Eagle Flight
Broadhead Arrow Quiver
--------
Requirements:
Level: 45
--------
Adds 5 to 10 Physical Damage to Bow Attacks
"""

SHIELD_TEXT = """Item Class: Shields
Rarity: Rare
Aegis Barrier
Spiked Shield
--------
Requirements:
Level: 45
--------
+30% to Fire Resistance
"""

WAND_TEXT = """Item Class: Wands
Rarity: Rare
Spire Wand
Opal Wand
--------
Requirements:
Level: 45
--------
+15% to Lightning Resistance
"""

TWO_HAND_AXE_TEXT = """Item Class: Two Hand Axes
Rarity: Rare
Blood Cleaver
Headsman Axe
--------
Physical Damage: 80-160
--------
Requirements:
Level: 45
--------
+20 to Strength
"""


def test_derive_weapon_archetype():
    staff = parse_item_text(STAFF_TEXT)
    crossbow = parse_item_text(CROSSBOW_TEXT)
    bow = parse_item_text(BOW_TEXT)
    quiver = parse_item_text(QUIVER_TEXT)
    shield = parse_item_text(SHIELD_TEXT)
    wand = parse_item_text(WAND_TEXT)
    two_hand_axe = parse_item_text(TWO_HAND_AXE_TEXT)

    assert derive_weapon_archetype(staff) == WeaponArchetype.TWO_HAND_STAFF
    assert derive_weapon_archetype(crossbow) == WeaponArchetype.TWO_HAND_CROSSBOW
    assert derive_weapon_archetype(bow) == WeaponArchetype.TWO_HAND_BOW
    assert derive_weapon_archetype(quiver) == WeaponArchetype.OFF_HAND_QUIVER
    assert derive_weapon_archetype(shield) == WeaponArchetype.OFF_HAND_SHIELD
    assert derive_weapon_archetype(wand) == WeaponArchetype.ONE_HAND_WEAPON
    assert derive_weapon_archetype(two_hand_axe) == WeaponArchetype.TWO_HAND_OTHER


def test_regression_a_staff_in_weapon_set_1_topology():
    """Regression A: Staff in Set 1 occupies Weapon 1 and clears Weapon 2, leaving Set 2 untouched."""
    staff = parse_item_text(STAFF_TEXT)
    resolver = WeaponTopologyResolver()

    # When currently equipping 1H Wand + Shield in Set 1
    currently_equipped = {
        "Weapon 1": "Spire Wand",
        "Weapon 2": "Aegis Barrier",
        "Weapon 1 Swap": "Gloom Piercer",
        "Weapon 2 Swap": None,
    }

    plan = resolver.resolve_topology(
        candidate=staff,
        target_set=WeaponSetContext.WEAPON_SET_1,
        currently_equipped=currently_equipped,
    )

    assert plan.target_set == WeaponSetContext.WEAPON_SET_1
    assert plan.target_slot == "Weapon 1"
    assert "Weapon 2" in plan.clear_slots
    assert "Weapon 1" in plan.displaced_slots
    assert "Weapon 2" in plan.displaced_slots
    # Must NOT touch Weapon Set 2
    assert "Weapon 1 Swap" not in plan.clear_slots
    assert "Weapon 2 Swap" not in plan.clear_slots
    assert plan.is_valid_pairing is True


def test_regression_b_crossbow_in_weapon_set_2_topology():
    """Regression B: Crossbow in Set 2 occupies Weapon 1 Swap and clears Weapon 2 Swap, leaving Set 1 untouched."""
    crossbow = parse_item_text(CROSSBOW_TEXT)
    resolver = WeaponTopologyResolver()

    currently_equipped = {
        "Weapon 1": "Volcano Pillar",
        "Weapon 2": None,
        "Weapon 1 Swap": "Old Crossbow",
        "Weapon 2 Swap": "Eagle Flight",  # Invalid quiver from prior state
    }

    plan = resolver.resolve_topology(
        candidate=crossbow,
        target_set=WeaponSetContext.WEAPON_SET_2,
        currently_equipped=currently_equipped,
    )

    assert plan.target_set == WeaponSetContext.WEAPON_SET_2
    assert plan.target_slot == "Weapon 1 Swap"
    assert "Weapon 2 Swap" in plan.clear_slots
    assert "Weapon 1 Swap" in plan.displaced_slots
    assert "Weapon 1" not in plan.clear_slots
    assert "Weapon 2" not in plan.clear_slots
    assert plan.is_valid_pairing is True


def test_regression_c_bow_quiver_compatibility_vs_crossbow():
    """Regression C: Bow permits Quiver in offhand; Crossbow strictly does not permit Quiver."""
    resolver = WeaponTopologyResolver()
    bow = parse_item_text(BOW_TEXT)
    crossbow = parse_item_text(CROSSBOW_TEXT)
    quiver = parse_item_text(QUIVER_TEXT)

    # 1. Bow + Quiver pairing
    valid_bow, err_bow = resolver.validate_pairing(main_hand=bow, off_hand=quiver)
    assert valid_bow is True
    assert err_bow == ""

    # 2. Crossbow + Quiver pairing
    valid_xbow, err_xbow = resolver.validate_pairing(main_hand=crossbow, off_hand=quiver)
    assert valid_xbow is False
    assert "quiver" in err_xbow.lower() or "crossbow" in err_xbow.lower()

    # 3. Equipping quiver when wielding crossbow
    plan_quiver = resolver.resolve_topology(
        candidate=quiver,
        target_set=WeaponSetContext.WEAPON_SET_2,
        currently_equipped={"Weapon 1 Swap": "Bombard Crossbow", "Weapon 2 Swap": None},
    )
    assert plan_quiver.is_valid_pairing is False
    assert "quiver" in plan_quiver.invalidation_reason.lower()


def test_regression_d_two_hand_displacing_one_hand_and_shield():
    """Regression D: 2H weapon displacing 1H + Shield clears shield and records both as displaced."""
    staff = parse_item_text(STAFF_TEXT)
    resolver = WeaponTopologyResolver()

    currently_equipped = {
        "Weapon 1": "Spire Wand",
        "Weapon 2": "Aegis Barrier",
    }

    plan = resolver.resolve_topology(
        candidate=staff,
        target_set=WeaponSetContext.WEAPON_SET_1,
        currently_equipped=currently_equipped,
    )

    assert set(plan.displaced_slots) == {"Weapon 1", "Weapon 2"}
    assert plan.clear_slots == ("Weapon 2",)


def test_regression_e_one_hand_replacing_two_hand_leaves_offhand_empty():
    """Regression E: 1H replacing 2H equips in target slot, clears other slot if previously occupied by 2H, and does not invent offhand."""
    wand = parse_item_text(WAND_TEXT)
    resolver = WeaponTopologyResolver()

    currently_equipped = {
        "Weapon 1": "Volcano Pillar",  # 2H staff
        "Weapon 2": None,
    }

    plan = resolver.resolve_topology(
        candidate=wand,
        target_set=WeaponSetContext.WEAPON_SET_1,
        currently_equipped=currently_equipped,
        preferred_slot="Weapon 1",
    )

    assert plan.target_slot == "Weapon 1"
    # Replacing 2H with 1H displaces the 2H item from Weapon 1; Weapon 2 remains None
    assert plan.displaced_slots == ("Weapon 1",)
    assert plan.clear_slots == ()


def test_regression_f_opposing_set_isolation():
    """Regression F: Modifying Set 1 leaves Set 2 completely isolated, and vice versa."""
    resolver = WeaponTopologyResolver()
    staff = parse_item_text(STAFF_TEXT)
    crossbow = parse_item_text(CROSSBOW_TEXT)

    plan1 = resolver.resolve_topology(
        candidate=staff,
        target_set=WeaponSetContext.WEAPON_SET_1,
    )
    assert all("Swap" not in s for s in plan1.clear_slots)
    assert "Swap" not in plan1.target_slot

    plan2 = resolver.resolve_topology(
        candidate=crossbow,
        target_set=WeaponSetContext.WEAPON_SET_2,
    )
    assert plan2.target_slot == "Weapon 1 Swap"
    assert all("Swap" in s for s in plan2.clear_slots)


def test_regression_h_topology_resolver_is_build_agnostic():
    """Regression H: WeaponTopologyResolver is build-agnostic.

    The resolver interface accepts NO build-specific stage or Fubgun policy parameters,
    and returns identical topology plans regardless of any external build context.
    """
    staff = parse_item_text(STAFF_TEXT)
    crossbow = parse_item_text(CROSSBOW_TEXT)
    bow = parse_item_text(BOW_TEXT)
    resolver = WeaponTopologyResolver()

    # Verify method signature does NOT have 'stage', 'build_stage', or 'profile' parameters
    import inspect
    sig = inspect.signature(resolver.resolve_topology)
    assert "stage" not in sig.parameters
    assert "build_stage" not in sig.parameters
    assert "profile" not in sig.parameters

    # Resolver generates canonical plans based only on item candidate and target set
    plan_staff = resolver.resolve_topology(staff, target_set=WeaponSetContext.WEAPON_SET_1)
    plan_crossbow = resolver.resolve_topology(crossbow, target_set=WeaponSetContext.WEAPON_SET_2)
    plan_bow = resolver.resolve_topology(bow, target_set=WeaponSetContext.WEAPON_SET_1)

    assert plan_staff.archetype == WeaponArchetype.TWO_HAND_STAFF
    assert plan_crossbow.archetype == WeaponArchetype.TWO_HAND_CROSSBOW
    assert plan_bow.archetype == WeaponArchetype.TWO_HAND_BOW
    assert plan_staff.target_slot == "Weapon 1"
    assert plan_crossbow.target_slot == "Weapon 1 Swap"
    assert plan_bow.target_slot == "Weapon 1"
