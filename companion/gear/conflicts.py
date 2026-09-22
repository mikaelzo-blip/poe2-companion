"""Observable mechanic conflict detection for equipped items."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict

from companion.gear.schema import EquippedItem, ItemSlot
from companion.state.provenance import ProvenancedField, VerificationState


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


def _extract_verified_attribute(
    attrs: Mapping[str, Any] | None,
    *keys: str,
) -> int | None:
    """Extract verified integer attribute value, rejecting unprovenanced or non-verified data."""
    if not attrs:
        return None

    val = None
    for key in keys:
        if key in attrs:
            val = attrs[key]
            break

    if val is None:
        return None

    # Plain numeric values carry no provenance metadata and cannot be authoritative facts
    if isinstance(val, (int, float)):
        return None

    # Check ProvenancedField
    if isinstance(val, ProvenancedField):
        if (
            val.value is not None
            and isinstance(val.value, (int, float))
            and val.verification_state == VerificationState.VERIFIED
            and not val.is_stale
            and bool(val.source)
            and val.source != "DEFAULT_INIT"
        ):
            return int(val.value)
        return None

    # Check OperandEvidence or similar duck-typed provenance container
    if hasattr(val, "verification_state") and hasattr(val, "value"):
        if (
            val.value is not None
            and isinstance(val.value, (int, float))
            and getattr(val, "verification_state", None) == VerificationState.VERIFIED
            and not getattr(val, "is_stale", False)
            and getattr(val, "in_scope", True)
            and bool(getattr(val, "source", None))
            and getattr(val, "source", None) != "DEFAULT_INIT"
        ):
            return int(val.value)

    return None


def detect_mechanic_conflicts(
    item: EquippedItem,
    character_attributes: Mapping[str, Any] | None = None,
    target_weapon_archetype: str | None = None,
) -> list[ConflictWarning]:
    """Detect observable stat and archetype conflicts for an item."""
    conflicts: list[ConflictWarning] = []
    attrs = character_attributes or {}

    # 1. Attribute threshold checks - require verified provenance on BOTH item and character
    if item.verification == VerificationState.VERIFIED:
        if item.required_str > 0:
            str_have = _extract_verified_attribute(attrs, "str", "strength")
            if str_have is not None and str_have < item.required_str:
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

        if item.required_dex > 0:
            dex_have = _extract_verified_attribute(attrs, "dex", "dexterity")
            if dex_have is not None and dex_have < item.required_dex:
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

        if item.required_int > 0:
            int_have = _extract_verified_attribute(attrs, "int", "intelligence")
            if int_have is not None and int_have < item.required_int:
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
