"""Stage level ranges derived from variant titles, and level -> stage resolution."""

from __future__ import annotations

import logging
import re

from companion.builds.guide import GuideProfile, GuideStage

logger = logging.getLogger(__name__)

_ACTS = {1: (1, 15), 2: (16, 29), 3: (30, 44), 4: (45, 55)}
_INTERLUDE = (56, 64)
_ENDGAME_START = 65

_LVL_RANGE = re.compile(r"\b(?:lvl|level|lv)\.?\s*(\d+)\s*[-–—]\s*(\d+)\b", re.I)
_LVL_ONE = re.compile(r"\b(?:lvl|level|lv)\.?\s*(\d+)\b", re.I)
_BARE_RANGE = re.compile(r"\b(\d+)\s*[-–—]\s*(\d+)\b")
_ACT_TO_END = re.compile(r"\bact\s*(\d)\s*to\s*endgame\b", re.I)
_ACT_PAIR = re.compile(r"\bact\s*(\d)\s*(?:&|and|[-–—])\s*([1-6])\b", re.I)
_ACT_ONE = re.compile(r"\bact\s*(\d)\b", re.I)
_INTERLUDE_RE = re.compile(r"\binterlude\b", re.I)
_KEYWORD = re.compile(
    r"\b(?:endgame|maps?|t\d{1,2}|mageblood|dot cap|pinnacle|uber)\b", re.I
)


def _act(n: str) -> tuple[int, int] | None:
    return _ACTS.get(int(n))


def parse_level_range(title: str) -> tuple[int | None, int | None, bool]:
    """Return (min, max, is_endgame_keyword) parsed from a variant title."""
    if m := _LVL_RANGE.search(title):
        return int(m[1]), int(m[2]), False
    if m := _LVL_ONE.search(title):
        return int(m[1]), int(m[1]), False
    if m := _ACT_TO_END.search(title):
        if a := _act(m[1]):
            return a[0], _INTERLUDE[1], False
    if m := _ACT_PAIR.search(title):
        lo, hi = _act(m[1]), _act(m[2])
        if lo and hi:
            return lo[0], hi[1], False
    if m := _ACT_ONE.search(title):
        if a := _act(m[1]):
            return a[0], a[1], False
    if _INTERLUDE_RE.search(title):
        return _INTERLUDE[0], _INTERLUDE[1], False
    if m := _BARE_RANGE.search(title):
        return int(m[1]), int(m[2]), False
    if _KEYWORD.search(title):
        return _ENDGAME_START, None, True
    return None, None, False


def assign_level_ranges(profile: GuideProfile) -> GuideProfile:
    """Return a new profile with min_level/max_level/auto set from stage titles."""
    if not profile.stages:
        return profile
    parsed = [parse_level_range(s.title) for s in profile.stages]
    out: list[GuideStage] = []
    prev_max = 0
    kw_min: int | None = None
    for i, (stage, (lo, hi, kw)) in enumerate(zip(profile.stages, parsed)):
        if kw:
            auto = kw_min is None
            if kw_min is None:
                kw_min = max(_ENDGAME_START, prev_max + 1)
            lo, hi = kw_min, 100
        else:
            unparsed = parsed[i] == (None, None, False)
            lo = lo if lo is not None else prev_max + 1
            nxt = parsed[i + 1] if i + 1 < len(parsed) else None
            if unparsed:  # split the gap to the next parsed/keyword stage evenly over the run
                j = i
                while j < len(parsed) and parsed[j] == (None, None, False):
                    j += 1
                after = parsed[j] if j < len(parsed) else None
                if after is None:
                    end = 100
                elif after[2]:
                    end = _ENDGAME_START - 1
                else:
                    end = after[0] - 1
                hi = lo + max(1, (end - lo + 1) // (j - i)) - 1
            elif nxt and not nxt[2] and nxt[0] is not None:
                hi = nxt[0] - 1
            elif hi is None:
                hi = 100
            hi = max(hi, lo)
            auto = True
        out.append(stage.model_copy(update={"min_level": lo, "max_level": hi, "auto": auto}))
        prev_max = hi
    # Normalize auto stages so levels 1-100 are covered exactly once, in guide order.
    prev_auto_max = 0
    kw_first: int | None = None
    for i, st in enumerate(out):
        if parsed[i][2] and kw_first is None:
            kw_first = i
        if not st.auto:
            continue
        lo = prev_auto_max + 1
        want = min(100, st.min_level)
        if prev_auto_max and want > lo:  # gap: stretch the previous auto stage, keep this min
            out[last_ok] = out[last_ok].model_copy(update={"max_level": want - 1})
            lo = want
        if lo > 100:
            out[i] = st.model_copy(update={"auto": False, "min_level": out[last_ok].min_level,
                                           "max_level": 100})
            continue
        hi = min(100, max(lo, st.max_level))
        out[i] = st.model_copy(update={"min_level": lo, "max_level": hi})
        prev_auto_max, last_ok = hi, i
    out[last_ok] = out[last_ok].model_copy(update={"max_level": 100})
    for i, st in enumerate(out):  # non-auto keyword duplicates mirror the first keyword stage
        if parsed[i][2] and not st.auto and i != kw_first:
            out[i] = st.model_copy(update={"min_level": out[kw_first].min_level,
                                           "max_level": out[kw_first].max_level})
    return profile.model_copy(update={"stages": out})


def resolve_stage(profile: GuideProfile, level: int | None, override_id: str | None = None) -> GuideStage:
    if override_id is not None:
        for s in profile.stages:
            if s.id == override_id:
                return s
        target = override_id.strip().casefold()
        for s in profile.stages:
            if s.title.strip().casefold() == target:
                return s
        logger.warning(
            "Stage override %r did not match any stage id or title; falling back to level-based stage",
            override_id,
        )
    if level is None:
        return profile.stages[0]
    autos = [s for s in profile.stages if s.auto]
    for s in autos:
        if s.min_level <= level <= s.max_level:
            return s
    # ponytail: out-of-range level falls back to the nearest auto stage below, else first stage
    below = [s for s in autos if s.min_level <= level]
    return below[-1] if below else profile.stages[0]
