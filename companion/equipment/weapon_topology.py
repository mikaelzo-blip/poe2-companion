"""Canonical, build-agnostic weapon topology resolver and compatibility engine.

RESPONSIBILITY BOUNDARY:
- Build-agnostic canonical PoE2 equipment topology and slot compatibility only.
- 1H vs 2H handedness rules and multi-slot occupancy.
- Bow + Quiver canonical compatibility (Bows allow Quivers; Crossbows and Staves do not).
- Staff and Crossbow incompatible off-hand clearing.
- Weapon Set 1 ("Weapon 1", "Weapon 2") vs Weapon Set 2 ("Weapon 1 Swap", "Weapon 2 Swap") slot mapping.
- Strictly prohibited from containing Fubgun, Flameblast, Oil Grenade, or progression-stage policy.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from companion.equipment.schema import ItemCandidate, SlotOccupancy, SlotType, WeaponSetContext


class WeaponArchetype(str, Enum):
    TWO_HAND_STAFF = "TWO_HAND_STAFF"
    TWO_HAND_CROSSBOW = "TWO_HAND_CROSSBOW"
    TWO_HAND_BOW = "TWO_HAND_BOW"
    TWO_HAND_OTHER = "TWO_HAND_OTHER"
    ONE_HAND_WEAPON = "ONE_HAND_WEAPON"
    OFF_HAND_SHIELD = "OFF_HAND_SHIELD"
    OFF_HAND_FOCUS = "OFF_HAND_FOCUS"
    OFF_HAND_QUIVER = "OFF_HAND_QUIVER"
    UNKNOWN_WEAPON = "UNKNOWN_WEAPON"


def derive_weapon_archetype(item: ItemCandidate | None) -> WeaponArchetype:
    """Derive canonical weapon archetype from base type, item class, and name."""
    if not item:
        return WeaponArchetype.UNKNOWN_WEAPON

    raw_text = " ".join([
        item.name or "",
        item.base_type or "",
        item.raw_text or "",
    ]).lower()

    # Check quivers first before bows (since a quiver is an offhand accessory)
    if "quiver" in raw_text:
        return WeaponArchetype.OFF_HAND_QUIVER

    # Crossbows before bows (crossbow contains 'bow' substring)
    if "crossbow" in raw_text:
        return WeaponArchetype.TWO_HAND_CROSSBOW

    if "bow" in raw_text:
        return WeaponArchetype.TWO_HAND_BOW

    if "staff" in raw_text or "stave" in raw_text or "quarterstaff" in raw_text:
        return WeaponArchetype.TWO_HAND_STAFF

    if "shield" in raw_text:
        return WeaponArchetype.OFF_HAND_SHIELD

    if "focus" in raw_text:
        return WeaponArchetype.OFF_HAND_FOCUS

    if any(k in raw_text for k in ("wand", "sceptre", "dagger", "claw")):
        return WeaponArchetype.ONE_HAND_WEAPON

    # Check two-hand indicators
    if "two hand" in raw_text or "two-hand" in raw_text or "twohanded" in raw_text or item.slot_occupancy == SlotOccupancy.TWO_HAND:
        return WeaponArchetype.TWO_HAND_OTHER

    if item.slot_occupancy == SlotOccupancy.MAIN_HAND or item.slot in (SlotType.MAIN_HAND, SlotType.OFF_HAND):
        return WeaponArchetype.ONE_HAND_WEAPON

    return WeaponArchetype.UNKNOWN_WEAPON


class WeaponTopologyPlan(BaseModel):
    """Canonical equipment topology and mutation plan for a weapon swap."""

    model_config = ConfigDict(frozen=True)

    target_set: WeaponSetContext
    target_slot: str  # "Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap"
    clear_slots: tuple[str, ...] = ()
    displaced_slots: tuple[str, ...] = ()
    archetype: WeaponArchetype
    is_valid_pairing: bool = True
    invalidation_reason: str = ""
    is_ambiguous_placement: bool = False
    alternative_slots: tuple[str, ...] = ()


class WeaponTopologyResolver:
    """Build-agnostic resolver for weapon slot occupancy, pairing legality, and clear targets."""

    @staticmethod
    def get_set_slots(target_set: WeaponSetContext) -> tuple[str, str]:
        """Return (main_hand_slot, off_hand_slot) for the target weapon set."""
        if target_set == WeaponSetContext.WEAPON_SET_2:
            return "Weapon 1 Swap", "Weapon 2 Swap"
        return "Weapon 1", "Weapon 2"

    def validate_pairing(
        self,
        main_hand: ItemCandidate | None,
        off_hand: ItemCandidate | None,
    ) -> tuple[bool, str]:
        """Validate if two weapon candidates can legally pair together canonically."""
        if main_hand is None and off_hand is None:
            return True, ""

        mh_arch = derive_weapon_archetype(main_hand)
        oh_arch = derive_weapon_archetype(off_hand)

        if mh_arch == WeaponArchetype.TWO_HAND_BOW:
            if off_hand is not None and oh_arch != WeaponArchetype.OFF_HAND_QUIVER:
                return False, "Bows can only pair with a quiver in the off-hand."
            return True, ""

        if mh_arch == WeaponArchetype.TWO_HAND_CROSSBOW:
            if off_hand is not None:
                if oh_arch == WeaponArchetype.OFF_HAND_QUIVER:
                    return False, "Crossbow cannot pair with quiver."
                return False, "Crossbow is a two-handed weapon and cannot pair with an off-hand item."
            return True, ""

        if mh_arch in (WeaponArchetype.TWO_HAND_STAFF, WeaponArchetype.TWO_HAND_OTHER):
            if off_hand is not None:
                return False, "Two-handed weapon occupies both slots and cannot pair with an off-hand item."
            return True, ""

        if oh_arch == WeaponArchetype.OFF_HAND_QUIVER:
            if mh_arch != WeaponArchetype.TWO_HAND_BOW:
                return False, "Quivers require wielding a bow and cannot pair with crossbows or melee weapons."

        return True, ""

    def resolve_topology(
        self,
        candidate: ItemCandidate,
        target_set: WeaponSetContext,
        currently_equipped: dict[str, str | None] | None = None,
        preferred_slot: str | None = None,
    ) -> WeaponTopologyPlan:
        """Resolve canonical slot assignment, displaced items, and off-hand clears.

        BUILD-AGNOSTIC INVARIANT: Does NOT accept or use progression stage or build profile.
        """
        equipped = currently_equipped or {}
        mh_slot, oh_slot = self.get_set_slots(target_set)
        archetype = derive_weapon_archetype(candidate)

        # 1. Quiver candidate
        if archetype == WeaponArchetype.OFF_HAND_QUIVER:
            current_mh = equipped.get(mh_slot)
            # If current main hand is known and not a bow (e.g. crossbow or staff), pairing is invalid
            if current_mh and ("crossbow" in current_mh.lower() or "staff" in current_mh.lower() or "stave" in current_mh.lower()):
                return WeaponTopologyPlan(
                    target_set=target_set,
                    target_slot=oh_slot,
                    archetype=archetype,
                    is_valid_pairing=False,
                    invalidation_reason="Quivers require wielding a bow and cannot pair with crossbows or staves.",
                )
            displaced = (oh_slot,) if equipped.get(oh_slot) else ()
            return WeaponTopologyPlan(
                target_set=target_set,
                target_slot=oh_slot,
                displaced_slots=displaced,
                archetype=archetype,
                is_valid_pairing=True,
            )

        # 2. Off-hand shield or focus
        if archetype in (WeaponArchetype.OFF_HAND_SHIELD, WeaponArchetype.OFF_HAND_FOCUS):
            displaced = (oh_slot,) if equipped.get(oh_slot) else ()
            return WeaponTopologyPlan(
                target_set=target_set,
                target_slot=oh_slot,
                displaced_slots=displaced,
                archetype=archetype,
                is_valid_pairing=True,
            )

        # 3. Two-handed weapons (Staff, Crossbow, 2H Axe/Sword/Mace)
        if archetype in (
            WeaponArchetype.TWO_HAND_STAFF,
            WeaponArchetype.TWO_HAND_CROSSBOW,
            WeaponArchetype.TWO_HAND_OTHER,
        ):
            displaced_list = []
            if equipped.get(mh_slot):
                displaced_list.append(mh_slot)
            if equipped.get(oh_slot):
                displaced_list.append(oh_slot)

            # Two-handed weapon clears the off-hand slot in the SAME set
            clear_slots = (oh_slot,)
            return WeaponTopologyPlan(
                target_set=target_set,
                target_slot=mh_slot,
                clear_slots=clear_slots,
                displaced_slots=tuple(displaced_list) if displaced_list else (mh_slot,),
                archetype=archetype,
                is_valid_pairing=True,
            )

        # 4. Bow (Two-handed, but allows Quiver in off-hand)
        if archetype == WeaponArchetype.TWO_HAND_BOW:
            displaced_list = []
            if equipped.get(mh_slot):
                displaced_list.append(mh_slot)

            clear_slots_list = []
            current_oh = equipped.get(oh_slot)
            if current_oh and "quiver" not in current_oh.lower():
                # Non-quiver offhand must be cleared
                displaced_list.append(oh_slot)
                clear_slots_list.append(oh_slot)

            return WeaponTopologyPlan(
                target_set=target_set,
                target_slot=mh_slot,
                clear_slots=tuple(clear_slots_list),
                displaced_slots=tuple(displaced_list) if displaced_list else (mh_slot,),
                archetype=archetype,
                is_valid_pairing=True,
            )

        # 5. One-handed weapons (Wand, Sceptre, 1H Sword, etc.)
        if archetype == WeaponArchetype.ONE_HAND_WEAPON:
            if preferred_slot:
                target_slot = preferred_slot
            else:
                target_slot = mh_slot

            # Check ambiguity: if neither slot preferred and dual-wieldable or both occupied
            is_ambiguous = (preferred_slot is None)
            displaced = (target_slot,) if equipped.get(target_slot) else ()

            return WeaponTopologyPlan(
                target_set=target_set,
                target_slot=target_slot,
                clear_slots=(),
                displaced_slots=displaced or (target_slot,),
                archetype=archetype,
                is_valid_pairing=True,
                is_ambiguous_placement=is_ambiguous,
                alternative_slots=(oh_slot,) if target_slot == mh_slot else (mh_slot,),
            )

        # Fallback unknown archetype
        return WeaponTopologyPlan(
            target_set=target_set,
            target_slot=mh_slot,
            archetype=archetype,
            is_valid_pairing=True,
        )
