"""Guide profile models: a build guide as level-resolved stages."""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator


class StageItem(BaseModel):
    slot: str
    name: str
    item_class: str
    is_unique: bool = False
    base_stats: dict[str, str] = {}
    mods: list[str] = []
    must_have: list[str] = []
    raw_text: str | None = None


class BreakerRule(BaseModel):
    pattern: str
    from_level: int = 1
    exclude_slots: list[str] = []
    reason: str

    @field_validator("pattern")
    @classmethod
    def _valid_regex(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc
        return v


class GuideStage(BaseModel):
    id: str
    title: str
    min_level: int = 1
    max_level: int = 100
    auto: bool = True
    items: dict[str, StageItem] = {}
    main_skill: str | None = None
    weapon_classes: dict[int, list[str]] = {}


class GuideProfile(BaseModel):
    slug: str
    name: str
    source_url: str | None = None
    imported_at: str
    stages: list[GuideStage]
    has_pob: bool = False
    pob_stage_id: str | None = None
    breaker_rules: list[BreakerRule] = []

    @field_validator("stages")
    @classmethod
    def _non_empty(cls, v: list[GuideStage]) -> list[GuideStage]:
        if not v:
            raise ValueError("stages must be non-empty")
        return v
