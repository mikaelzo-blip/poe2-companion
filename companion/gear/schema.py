"""Data models and schemas for gear analysis, item properties, and slot audit states."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from companion.state.provenance import VerificationState


class ItemSlot(str, Enum):
    """Recognized equipment slots."""

    MAIN_HAND = "main_hand"
    OFF_HAND = "off_hand"
    WEAPON_SET_2_MAIN = "weapon_set_2_main"
    WEAPON_SET_2_OFF = "weapon_set_2_off"
    HELMET = "helmet"
    BODY_ARMOUR = "body_armour"
    GLOVES = "gloves"
    BOOTS = "boots"
    AMULET = "amulet"
    RING_1 = "ring_1"
    RING_2 = "ring_2"
    BELT = "belt"


class ItemRarity(str, Enum):
    """Item rarity categories."""

    NORMAL = "normal"
    MAGIC = "magic"
    RARE = "rare"
    UNIQUE = "unique"


class ComparisonVerdict(str, Enum):
    """Semantic outcome of comparing candidate against verified target requirements."""

    SATISFIES_MORE_VERIFIED_REQUIREMENTS = "SATISFIES_MORE_VERIFIED_REQUIREMENTS"
    SATISFIES_FEWER_VERIFIED_REQUIREMENTS = "SATISFIES_FEWER_VERIFIED_REQUIREMENTS"
    EQUIVALENT_FOR_KNOWN_REQUIREMENTS = "EQUIVALENT_FOR_KNOWN_REQUIREMENTS"
    INCOMPARABLE = "INCOMPARABLE"
    UNKNOWN = "UNKNOWN"


class ModType(str, Enum):
    """Modifier classifications."""

    IMPLICIT = "implicit"
    EXPLICIT = "explicit"


class ItemMod(BaseModel):
    """Normalized modifier line."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_text: str
    mod_type: ModType = ModType.EXPLICIT
    key: str | None = None
    value: float | int | None = None


class EquippedItem(BaseModel):
    """Structured representation of an equipped or candidate item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: ItemSlot
    name: str | None = None
    base_type: str
    rarity: ItemRarity = ItemRarity.NORMAL
    level_req: int = 0
    item_level: int = 0
    required_str: int = 0
    required_dex: int = 0
    required_int: int = 0
    implicit_mods: list[ItemMod] = Field(default_factory=list)
    explicit_mods: list[ItemMod] = Field(default_factory=list)
    runes: list[str] = Field(default_factory=list)
    sockets: int = 0
    item_hash: str | None = None
    observed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    verification: VerificationState = VerificationState.UNKNOWN


class GearAuditState(BaseModel):
    """Aggregated equipment slot audit state for a character."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    character_id: str
    slots: dict[ItemSlot, EquippedItem] = Field(default_factory=dict)
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
