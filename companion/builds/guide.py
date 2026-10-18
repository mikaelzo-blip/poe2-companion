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


CANONICAL_SLOTS = frozenset({
    "Helmet", "Body Armour", "Gloves", "Boots", "Amulet", "Belt", "Ring 1", "Ring 2",
    "Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap",
})
_SLOT_BY_LOWER = {s.lower(): s for s in CANONICAL_SLOTS}


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
            raise ValueError(f"regex tidak valid: {exc}") from exc
        return v

    @field_validator("from_level")
    @classmethod
    def _valid_level(cls, v: int) -> int:
        if not 1 <= v <= 100:
            raise ValueError("from_level harus 1-100")
        return v

    @field_validator("exclude_slots")
    @classmethod
    def _canonical_slots(cls, v: list[str]) -> list[str]:
        canon = [_SLOT_BY_LOWER.get(s.strip().lower()) for s in v]
        bad = [s for s, c in zip(v, canon) if c is None]
        if bad:
            raise ValueError(f"slot tidak dikenal: {bad}")
        return list(dict.fromkeys(canon))


class GemNote(BaseModel):
    """One section of the guide's gem progression text ("Act 1": its steps)."""
    title: str
    steps: list[str] = []


class QuestReward(BaseModel):
    """A permanent quest buff the guide takes ("Act 2", "Medallion": "+1 Charm Slot")."""
    act: str
    area: str = ""
    quest: str
    reward: str


class PassiveNotable(BaseModel):
    """One entry of the guide's notable priority list (kind: NOTABLE, KEY_STONE, ASCENDANCY_LARGE...)."""
    name: str
    kind: str = "NOTABLE"


class GuideStage(BaseModel):
    id: str
    title: str
    min_level: int = 1
    max_level: int = 100
    auto: bool = True
    items: dict[str, StageItem] = {}
    main_skill: str | None = None
    weapon_classes: dict[int, list[str]] = {}
    notables: list[PassiveNotable] = []


class GuideProfile(BaseModel):
    slug: str
    name: str
    source_url: str | None = None
    imported_at: str
    stages: list[GuideStage]
    has_pob: bool = False
    pob_stage_id: str | None = None
    breaker_rules: list[BreakerRule] = []
    gem_notes: list[GemNote] = []
    vendor_regex: str | None = None
    quest_rewards: list[QuestReward] = []
    tree_hints: list[str] = []

    @field_validator("stages")
    @classmethod
    def _non_empty(cls, v: list[GuideStage]) -> list[GuideStage]:
        if not v:
            raise ValueError("stages must be non-empty")
        return v
