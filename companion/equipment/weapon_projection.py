"""Weapon set projection and conflict topology validation."""

from __future__ import annotations

from companion.equipment.loadout import EquippedLoadout, EquippedSlotEntry
from companion.equipment.schema import ItemCandidate, SlotOccupancy, SlotType, WeaponSetContext


def is_bow(item: ItemCandidate | None) -> bool:
    if not item:
        return False
    bt = (item.base_type or "").lower()
    nm = (item.name or "").lower()
    return "bow" in bt or "bow" in nm


def is_crossbow(item: ItemCandidate | None) -> bool:
    if not item:
        return False
    bt = (item.base_type or "").lower()
    nm = (item.name or "").lower()
    return "crossbow" in bt or "crossbow" in nm


def is_quiver(item: ItemCandidate | None) -> bool:
    if not item:
        return False
    bt = (item.base_type or "").lower()
    nm = (item.name or "").lower()
    return "quiver" in bt or "quiver" in nm


def is_staff(item: ItemCandidate | None) -> bool:
    if not item:
        return False
    bt = (item.base_type or "").lower()
    nm = (item.name or "").lower()
    return "staff" in bt or "stave" in bt or "staff" in nm


def validate_weapon_pairing(
    main_hand: ItemCandidate | None,
    off_hand: ItemCandidate | None,
) -> tuple[bool, str]:
    if main_hand is None and off_hand is None:
        return True, ""

    if main_hand:
        if is_staff(main_hand) or (main_hand.slot_occupancy == SlotOccupancy.TWO_HAND and not is_bow(main_hand)):
            if off_hand is not None:
                if is_crossbow(main_hand) and is_quiver(off_hand):
                    return False, "Crossbow cannot pair with quiver."
                return False, "Two-handed weapon occupies both slots and cannot pair with an off-hand item."

        if is_crossbow(main_hand):
            if off_hand is not None:
                return False, "Crossbow cannot pair with quiver."

        if is_bow(main_hand):
            if off_hand is not None and not is_quiver(off_hand):
                return False, "Bows can only pair with a quiver in the off-hand."

    if off_hand and is_quiver(off_hand):
        if not is_bow(main_hand):
            return False, "Quivers require wielding a bow and cannot pair with crossbows or melee weapons."

    return True, ""


def project_weapon_set_swap(
    loadout: EquippedLoadout,
    candidate: ItemCandidate,
    target_set: WeaponSetContext,
) -> EquippedLoadout:
    """Project a weapon swap into target weapon set without touching the other weapon set."""
    projected = loadout.model_copy(deep=True)
    weapon_dict = (
        projected.weapon_set_1
        if target_set == WeaponSetContext.WEAPON_SET_1
        else projected.weapon_set_2
    )

    mh_entry = weapon_dict.get(SlotType.MAIN_HAND.value)

    if candidate.slot_occupancy == SlotOccupancy.TWO_HAND:
        weapon_dict[SlotType.MAIN_HAND.value] = EquippedSlotEntry(
            item=candidate,
            slot=SlotType.MAIN_HAND,
            weapon_set=target_set,
        )
        weapon_dict[SlotType.OFF_HAND.value] = None
    elif candidate.slot == SlotType.MAIN_HAND:
        weapon_dict[SlotType.MAIN_HAND.value] = EquippedSlotEntry(
            item=candidate,
            slot=SlotType.MAIN_HAND,
            weapon_set=target_set,
        )
        if mh_entry and mh_entry.item.slot_occupancy == SlotOccupancy.TWO_HAND:
            weapon_dict[SlotType.OFF_HAND.value] = None
    elif candidate.slot == SlotType.OFF_HAND:
        weapon_dict[SlotType.OFF_HAND.value] = EquippedSlotEntry(
            item=candidate,
            slot=SlotType.OFF_HAND,
            weapon_set=target_set,
        )
        if mh_entry and mh_entry.item.slot_occupancy == SlotOccupancy.TWO_HAND:
            weapon_dict[SlotType.MAIN_HAND.value] = None

    return projected
