"""Observable mechanic conflict detection for equipped items."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict

from companion.gear.schema import EquippedItem, ItemSlot


class ConflictType(str, Enum):
    """Categorical conflict types."""

    UNMET_ATTRIBUTE = "unmet_attribute"
    WEAPON_ARCHETYPE_MISMATCH = "weapon_archetype_mismatch"
    MECHANIC_INCOMPATIBILITY = "mechanic_incompatibility"


class ConflictWarning(BaseModel):
    """Warning describing an observable mechanical conflict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: ItemSlot
    conflict_type: ConflictType
    description: str
    severity: str = "WARNING"


def detect_mechanic_conflicts(
    item: EquippedItem,
    character_attributes: dict[str, int] | None = None,
    target_weapon_archetype: str | None = None,
) -> list[ConflictWarning]:
    """Detect observable stat and archetype conflicts for an item."""
    conflicts: list[ConflictWarning] = []
    attrs = character_attributes or {}

    # 1. Attribute threshold checks
    str_have = attrs.get("str", 0)
    if item.required_str > 0 and str_have < item.required_str:
        conflicts.append(
            ConflictWarning(
                slot=item.slot,
                conflict_type=ConflictType.UNMET_ATTRIBUTE,
                description=(
                    f"Unmet Strength requirement: Item requires {item.required_str} Str, "
                    f"but observed character has {str_have} Str."
                ),
            )
        )

    dex_have = attrs.get("dex", 0)
    if item.required_dex > 0 and dex_have < item.required_dex:
        conflicts.append(
            ConflictWarning(
                slot=item.slot,
                conflict_type=ConflictType.UNMET_ATTRIBUTE,
                description=(
                    f"Unmet Dexterity requirement: Item requires {item.required_dex} Dex, "
                    f"but observed character has {dex_have} Dex."
                ),
            )
        )

    int_have = attrs.get("int", 0)
    if item.required_int > 0 and int_have < item.required_int:
        conflicts.append(
            ConflictWarning(
                slot=item.slot,
                conflict_type=ConflictType.UNMET_ATTRIBUTE,
                description=(
                    f"Unmet Intelligence requirement: Item requires {item.required_int} Int, "
                    f"but observed character has {int_have} Int."
                ),
            )
        )

    # 2. Weapon archetype check
    if target_weapon_archetype and item.slot in (
        ItemSlot.MAIN_HAND,
        ItemSlot.WEAPON_SET_2_MAIN,
    ):
        target_lower = target_weapon_archetype.lower()
        base_lower = item.base_type.lower()
        if target_lower not in base_lower:
            conflicts.append(
                ConflictWarning(
                    slot=item.slot,
                    conflict_type=ConflictType.WEAPON_ARCHETYPE_MISMATCH,
                    description=(
                        f"Weapon archetype mismatch: Build targets '{target_weapon_archetype}', "
                        f"but equipped item base is '{item.base_type}'."
                    ),
                )
            )

    return conflicts
