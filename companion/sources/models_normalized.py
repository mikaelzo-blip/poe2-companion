"""Normalized domain models for PoE2 build representations.

Transforms raw build data into typed structures with:
- Validated level intervals
- Passive deduplication preservation indexed by (passive_id, weapon_set_context)
- Normalized weapon-set contexts
- Explicit anomaly annotations (e.g. Cast on Dodge meta-gem)
"""

from __future__ import annotations

from collections import OrderedDict
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from companion.sources.interval import LevelInterval, parse_level_interval
from companion.sources.models_raw import (
    RawBuild,
    RawInventorySlot,
    RawPassiveEntry,
    RawSkillEntry,
    RawSupportSkill,
)


class WeaponSetContext(str, Enum):
    DEFAULT_OR_SHARED = "DEFAULT_OR_SHARED"
    SPECIALISATION_1 = "SPECIALISATION_1"
    SPECIALISATION_2 = "SPECIALISATION_2"
    UNKNOWN_RESERVED = "UNKNOWN_RESERVED"
    OTHER = "OTHER"


def map_weapon_set_context(raw_ws: int | None) -> tuple[WeaponSetContext, str | None]:
    """Map raw weapon_set integer to semantic WeaponSetContext enum.
    
    Returns (context, optional_warning).
    """
    if raw_ws is None:
        return WeaponSetContext.DEFAULT_OR_SHARED, None
    if raw_ws == 1:
        return WeaponSetContext.SPECIALISATION_1, None
    if raw_ws == 2:
        return WeaponSetContext.SPECIALISATION_2, None
    if raw_ws == 0:
        return WeaponSetContext.UNKNOWN_RESERVED, "Encountered reserved weapon_set value 0"
    return WeaponSetContext.OTHER, f"Encountered unexpected weapon_set value {raw_ws}"


def is_cast_on_dodge_id(gem_id: str | int | None) -> bool:
    """Detect if gem ID refers to Cast on Dodge meta-gem."""
    if gem_id is None:
        return False
    normalized = str(gem_id).strip().lower().replace("_", " ")
    return (
        "cast on dodge" in normalized
        or "castondodge" in normalized
        or normalized.endswith("skillgemcastondodge")
    )


class NormalizedPassiveEntry(BaseModel):
    """Normalized passive skill node with compound identity and duplicate audit."""
    model_config = ConfigDict(frozen=True)

    passive_id: str
    weapon_set_context: WeaponSetContext
    raw_weapon_set: int | None = None
    occurrences: int = 1
    original_indices: list[int] = Field(default_factory=list)

    @property
    def compound_key(self) -> tuple[str, WeaponSetContext]:
        return (self.passive_id, self.weapon_set_context)


class NormalizedSupportSkill(BaseModel):
    """Normalized support skill gem."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    level_interval: LevelInterval
    is_cast_on_dodge: bool = False
    raw_extra: dict[str, Any] = Field(default_factory=dict)


class NormalizedSkillEntry(BaseModel):
    """Normalized skill gem entry with child support gems."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    level_interval: LevelInterval
    support_skills: list[NormalizedSupportSkill] = Field(default_factory=list)
    is_cast_on_dodge: bool = False
    raw_extra: dict[str, Any] = Field(default_factory=dict)


class NormalizedInventorySlot(BaseModel):
    """Normalized inventory slot entry."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    inventory_id: str
    slot_x: int
    slot_y: int
    level_interval: LevelInterval
    unique_name: str | None = None
    additional_text: str | None = None
    raw_extra: dict[str, Any] = Field(default_factory=dict)


class NormalizedBuild(BaseModel):
    """Normalized build snapshot."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    logical_stage: str
    raw_name: str
    author: str | None = None
    ascendancy: str | None = None
    link: str | None = None
    passives: list[NormalizedPassiveEntry] = Field(default_factory=list)
    skills: list[NormalizedSkillEntry] = Field(default_factory=list)
    inventory_slots: list[NormalizedInventorySlot] = Field(default_factory=list)
    extra_fields: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def normalize_build(raw: RawBuild, logical_stage: str = "") -> NormalizedBuild:
    """Normalize a RawBuild into a NormalizedBuild without mutating raw data."""
    warnings: list[str] = []

    # 1. Process passives with (id, weapon_set_context) compound identity
    passive_map: OrderedDict[tuple[str, WeaponSetContext], dict[str, Any]] = OrderedDict()
    for idx, p in enumerate(raw.passives):
        pid = str(p.id)
        ws_ctx, warn = map_weapon_set_context(p.weapon_set)
        if warn:
            warnings.append(warn)
        key = (pid, ws_ctx)
        if key not in passive_map:
            passive_map[key] = {
                "passive_id": pid,
                "weapon_set_context": ws_ctx,
                "raw_weapon_set": p.weapon_set,
                "occurrences": 1,
                "original_indices": [idx],
            }
        else:
            passive_map[key]["occurrences"] += 1
            passive_map[key]["original_indices"].append(idx)

    normalized_passives = [
        NormalizedPassiveEntry(**item) for item in passive_map.values()
    ]

    # 2. Process skills
    normalized_skills: list[NormalizedSkillEntry] = []
    for s in raw.skills:
        s_id = str(s.id)
        s_interval = parse_level_interval(s.level_interval)
        s_cod = is_cast_on_dodge_id(s_id)

        normalized_supports: list[NormalizedSupportSkill] = []
        for sup in s.support_skills:
            sup_id = str(sup.id)
            sup_interval = parse_level_interval(sup.level_interval)
            sup_cod = is_cast_on_dodge_id(sup_id)
            sup_extra = sup.model_extra or {}
            normalized_supports.append(
                NormalizedSupportSkill(
                    id=sup_id,
                    level_interval=sup_interval,
                    is_cast_on_dodge=sup_cod,
                    raw_extra=dict(sup_extra),
                )
            )

        s_extra = s.model_extra or {}
        normalized_skills.append(
            NormalizedSkillEntry(
                id=s_id,
                level_interval=s_interval,
                support_skills=normalized_supports,
                is_cast_on_dodge=s_cod,
                raw_extra=dict(s_extra),
            )
        )

    # 3. Process inventory slots
    normalized_inv: list[NormalizedInventorySlot] = []
    for inv in raw.inventory_slots:
        inv_id = str(inv.inventory_id) if inv.inventory_id is not None else ""
        inv_interval = parse_level_interval(inv.level_interval)
        inv_extra = inv.model_extra or {}
        normalized_inv.append(
            NormalizedInventorySlot(
                inventory_id=inv_id,
                slot_x=inv.slot_x if inv.slot_x is not None else 0,
                slot_y=inv.slot_y if inv.slot_y is not None else 0,
                level_interval=inv_interval,
                unique_name=inv.unique_name,
                additional_text=inv.additional_text,
                raw_extra=dict(inv_extra),
            )
        )

    extra_fields = dict(raw.model_extra or {})

    return NormalizedBuild(
        logical_stage=logical_stage,
        raw_name=raw.name or "",
        author=raw.author,
        ascendancy=raw.ascendancy,
        link=raw.link,
        passives=normalized_passives,
        skills=normalized_skills,
        inventory_slots=normalized_inv,
        extra_fields=extra_fields,
        warnings=warnings,
    )
