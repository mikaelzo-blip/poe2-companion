"""Compare a candidate item's modifiers against a guide stage item's wanted mods."""

from __future__ import annotations

import re

from pydantic import BaseModel

from companion.builds.guide import StageItem
from companion.equipment.normalizer import (
    NormalizedModifierType,
    normalize_modifier,
    strip_mod_tags,
)

_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?(?:\s*\(\s*[+-]?\d+(?:\.\d+)?\s*-\s*[+-]?\d+(?:\.\d+)?\s*\))?%?")


def mod_family(line: str) -> str:
    mod = normalize_modifier(line)
    if mod is not None and mod.modifier_type != NormalizedModifierType.UNKNOWN_MODIFIER:
        return mod.modifier_type.value
    clean = strip_mod_tags(line)
    return " ".join(_NUMBER.sub("#", clean.lower()).split())


class PrioritySignal(BaseModel):
    matched: int
    total: int
    must_have_missing: list[str]

    @property
    def ratio(self) -> float | None:
        return self.matched / self.total if self.total else None


def priority_signal(stage_item: StageItem | None, candidate_lines: list[str]) -> PrioritySignal | None:
    if stage_item is None or not stage_item.mods:
        return None
    have = {mod_family(line) for line in candidate_lines}
    wanted = {mod_family(m) for m in stage_item.mods}
    return PrioritySignal(
        matched=len(wanted & have),
        total=len(wanted),
        must_have_missing=[m for m in stage_item.must_have if mod_family(m) not in have],
    )
