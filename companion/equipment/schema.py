"""Domain schemas and models for PoE2 Equipment Intelligence."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from companion.state.provenance import VerificationState


class SlotType(str, Enum):
    """Recognized equipment slots in PoE2."""

    HELMET = "helmet"
    BODY_ARMOUR = "body_armour"
    GLOVES = "gloves"
    BOOTS = "boots"
    AMULET = "amulet"
    RING_1 = "ring1"
    RING_2 = "ring2"
    BELT = "belt"
    MAIN_HAND = "main_hand"
    OFF_HAND = "off_hand"

    @classmethod
    def from_str(cls, val: str) -> SlotType:
        """Parse slot from various user and system formats."""
        normalized = val.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in ("ring_1", "ring1", "ring"):
            return cls.RING_1
        if normalized in ("ring_2", "ring2"):
            return cls.RING_2
        if normalized in ("helm", "helmet"):
            return cls.HELMET
        if normalized in ("body", "body_armour", "chest", "bodyarmour", "body_armor"):
            return cls.BODY_ARMOUR
        if normalized in ("glove", "gloves"):
            return cls.GLOVES
        if normalized in ("boot", "boots"):
            return cls.BOOTS
        if normalized in ("amulet", "neck", "necklace"):
            return cls.AMULET
        if normalized in ("belt",):
            return cls.BELT
        if normalized in ("main_hand", "mainhand", "mh", "weapon1", "weapon_1", "weapon"):
            return cls.MAIN_HAND
        if normalized in ("off_hand", "offhand", "oh", "shield", "quiver", "offhand2", "weapon2", "weapon_2"):
            return cls.OFF_HAND
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(f"Unknown slot type: {val}")


class WeaponSetContext(str, Enum):
    """Context identifying weapon set 1 or 2."""

    WEAPON_SET_1 = "weapon_set_1"
    WEAPON_SET_2 = "weapon_set_2"

    @classmethod
    def from_val(cls, val: int | str | WeaponSetContext) -> WeaponSetContext:
        if isinstance(val, cls):
            return val
        if isinstance(val, int):
            if val == 1:
                return cls.WEAPON_SET_1
            if val == 2:
                return cls.WEAPON_SET_2
        str_val = str(val).lower().strip().replace("-", "_")
        if str_val in ("1", "set_1", "weapon_set_1", "set1"):
            return cls.WEAPON_SET_1
        if str_val in ("2", "set_2", "weapon_set_2", "set2"):
            return cls.WEAPON_SET_2
        raise ValueError(f"Unknown weapon set context: {val}")


class SlotOccupancy(str, Enum):
    """Classification of item handedness and slot occupancy."""

    SINGLE_SLOT = "SINGLE_SLOT"
    MAIN_HAND = "MAIN_HAND"
    OFF_HAND = "OFF_HAND"
    TWO_HAND = "TWO_HAND"
    SHARED_EQUIPMENT_SLOT = "SHARED_EQUIPMENT_SLOT"
    UNKNOWN_OCCUPANCY = "UNKNOWN_OCCUPANCY"


class SlotConflictTopology(BaseModel):
    """Exact slot topology describing occupied and conflicting slots."""

    model_config = ConfigDict(frozen=True)

    occupied_slots: list[SlotType] = Field(default_factory=list)
    conflicting_slots: list[SlotType] = Field(default_factory=list)
    allowed_companion_slots: list[SlotType] = Field(default_factory=list)
    is_known: bool = True


class ModifierScope(str, Enum):
    """Scope of application for an item modifier."""

    LOCAL_ITEM_STAT = "LOCAL_ITEM_STAT"
    GLOBAL_CHARACTER_STAT = "GLOBAL_CHARACTER_STAT"
    REQUIREMENT = "REQUIREMENT"
    BUILD_MECHANIC = "BUILD_MECHANIC"
    CONDITIONAL = "CONDITIONAL"
    UNKNOWN_SCOPE = "UNKNOWN_SCOPE"


class NormalizedModifierType(str, Enum):
    """Semantic modifier types for character evaluation."""

    MAXIMUM_LIFE = "MAXIMUM_LIFE"
    FIRE_RESISTANCE = "FIRE_RESISTANCE"
    COLD_RESISTANCE = "COLD_RESISTANCE"
    LIGHTNING_RESISTANCE = "LIGHTNING_RESISTANCE"
    CHAOS_RESISTANCE = "CHAOS_RESISTANCE"
    LOCAL_ARMOUR = "LOCAL_ARMOUR"
    LOCAL_EVASION = "LOCAL_EVASION"
    LOCAL_ENERGY_SHIELD = "LOCAL_ENERGY_SHIELD"
    LOCAL_ARMOUR_AND_EVASION = "LOCAL_ARMOUR_AND_EVASION"
    MOVEMENT_SPEED = "MOVEMENT_SPEED"
    STRENGTH = "STRENGTH"
    DEXTERITY = "DEXTERITY"
    INTELLIGENCE = "INTELLIGENCE"
    FLAT_FIRE_DAMAGE_ATTACK = "FLAT_FIRE_DAMAGE_ATTACK"
    FLAT_FIRE_DAMAGE_SPELL = "FLAT_FIRE_DAMAGE_SPELL"
    EXTRA_FIRE_DAMAGE = "EXTRA_FIRE_DAMAGE"
    INCREASED_FIRE_DAMAGE = "INCREASED_FIRE_DAMAGE"
    FIRE_SPELL_LEVEL = "FIRE_SPELL_LEVEL"
    ALL_SPELL_LEVEL = "ALL_SPELL_LEVEL"
    SPECIAL_MECHANIC = "SPECIAL_MECHANIC"
    UNKNOWN_MODIFIER = "UNKNOWN_MODIFIER"


class NormalizedModifier(BaseModel):
    """Normalized representation of a parsed item modifier."""

    model_config = ConfigDict(frozen=True)

    modifier_type: NormalizedModifierType
    scope: ModifierScope
    value: float
    raw_text: str
    is_implicit: bool = False
    verification_state: VerificationState = VerificationState.VERIFIED
    mechanic_id: str | None = None


class ItemCandidate(BaseModel):
    """Parsed and normalized item candidate."""

    model_config = ConfigDict(frozen=True)

    item_id: str
    name: str
    base_type: str
    slot: SlotType
    slot_occupancy: SlotOccupancy = SlotOccupancy.SINGLE_SLOT
    slot_conflict_topology: SlotConflictTopology = Field(
        default_factory=lambda: SlotConflictTopology(occupied_slots=[])
    )
    rarity: str = "normal"
    item_level: int | None = None
    required_level: int = 1
    required_str: int = 0
    required_dex: int = 0
    required_int: int = 0
    local_armour: int = 0
    local_evasion: int = 0
    local_energy_shield: int = 0
    modifiers: list[NormalizedModifier] = Field(default_factory=list)
    annotations: list[str] = Field(default_factory=list)
    flavor_text: str | None = None
    raw_text: str = ""
    weapon_set: WeaponSetContext | None = None
