"""Raw Pydantic models for PoE2 .build file structures.

Mirrors the PoE2 .build JSON schema without data loss, allowing arbitrary
extra/unmodeled fields via ConfigDict(extra="allow").
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class RawBaseModel(BaseModel):
    """Base model that allows extra unknown fields and preserves them."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class RawPassiveEntry(RawBaseModel):
    """Raw passive skill node specification."""
    id: str | int
    weapon_set: int | None = None

    @property
    def passive_id_str(self) -> str:
        return str(self.id)


class RawSupportSkill(RawBaseModel):
    """Raw support gem attached to a skill gem."""
    id: str | int
    level_interval: Any = None

    @property
    def support_id_str(self) -> str:
        return str(self.id)


class RawSkillEntry(RawBaseModel):
    """Raw active skill gem socket and attached support gems."""
    id: str | int
    level_interval: Any = None
    support_skills: list[RawSupportSkill] = Field(default_factory=list)

    @property
    def skill_id_str(self) -> str:
        return str(self.id)


class RawInventorySlot(RawBaseModel):
    """Raw inventory/gear equipment slot recommendation."""
    inventory_id: str | int | None = None
    slot_x: int | None = None
    slot_y: int | None = None
    level_interval: Any = None
    unique_name: str | None = None
    additional_text: str | None = None


class RawBuild(RawBaseModel):
    """Top-level raw .build snapshot data model."""
    author: str | None = None
    link: str | None = None
    ascendancy: str | None = None
    name: str | None = None
    passives: list[RawPassiveEntry] = Field(default_factory=list)
    skills: list[RawSkillEntry] = Field(default_factory=list)
    inventory_slots: list[RawInventorySlot] = Field(default_factory=list)
