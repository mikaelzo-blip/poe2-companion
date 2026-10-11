"""Guide profile models: a build guide as level-resolved stages."""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator

from companion.equipment.api_adapter import ITEM_CLASS_PLURAL


_SINGULAR = {v: k for k, v in ITEM_CLASS_PLURAL.items()}


def singular_item_class(label: str) -> str:
    """Clipboard plural class label ("Crossbows") -> the singular vocabulary guides use."""
    if label in _SINGULAR:
        return _SINGULAR[label]
    return label[:-1] if label.endswith("s") else label


def weapon_classes_of(items: dict) -> dict[int, list[str]]:
    """Weapon classes per weapon set (1 = Weapon 1/2, 2 = swap slots) from a stage's items."""
    wc = {
        n: sorted({items[s].item_class for s in slots if s in items})
        for n, slots in ((1, ("Weapon 1", "Weapon 2")), (2, ("Weapon 1 Swap", "Weapon 2 Swap")))
    }
    return {n: c for n, c in wc.items() if c}


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
