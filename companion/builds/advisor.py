"""Guide-driven objectives for the active character: resists per act, gem steps, slot gaps, vendor regex.

Replaces the legacy CURRENT_OBJECTIVE.json (built from one fixed build snapshot) for characters with a guide.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from companion.builds.guide import GuideProfile, GuideStage
from companion.builds.priorities import mod_family
from companion.builds.stages import resolve_stage
from companion.builds.store import get_assignment, load_guide
from companion.equipment.baseline import BaselineSource
from companion.equipment.baseline_cli import load_baseline
from companion.equipment.current_item import character_level_and_zone, get_current_raw
from companion.equipment.parser import parse_item_text
from companion.equipment.pob2_equipment_advisor import act_for_level, act_of_zone, resist_penalty_for_act

SOURCE = "Guide Advisor"
RES_TARGET = 75
_ELEMENTS = (("fire", "Fire Resistance"), ("cold", "Cold Resistance"), ("lightning", "Lightning Resistance"))
_WEAPON_SLOTS = ("Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap")
_ACT_TITLE = re.compile(r"\bact\s*(\d+)", re.I)


def _objective(oid: str, priority: int, title: str, action: str, rationale: str, cost: int = 2) -> dict[str, Any]:
    return {
        "id": f"guide:{oid}", "priority": priority, "title": title, "action": action, "rationale": rationale,
        "source": SOURCE, "evidence_trust": 3, "horizon": 1, "cost_of_ignoring": cost, "is_corrective": False,
        "metadata": {},
    }


def act_label(act: int) -> str:
    return "Interlude" if act == 6 else "Endgame" if act >= 10 else f"Act {act}"


def _next_act(act: int) -> int | None:
    return {1: 2, 2: 3, 3: 4, 4: 6, 6: 10}.get(act)


def _level_and_zone(runtime_dir: Path, char_id: str) -> tuple[Any, Any]:
    char_file = runtime_dir / "characters" / f"{char_id}.json"
    try:
        char_data = json.loads(char_file.read_text(encoding="utf-8")) if char_file.is_file() else {}
    except (OSError, ValueError):
        char_data = {}
    return character_level_and_zone(char_data)


def character_level_and_act(runtime_dir: Path, char_id: str) -> tuple[Any, int]:
    """The character's level and current act (zone first, level as fallback)."""
    level, zone = _level_and_zone(runtime_dir, char_id)
    return level, act_of_zone(zone) or act_for_level(level) or 1


def resist_by_act(baseline: Any, act: int, current_act: int) -> dict[str, int] | None:
    """Effective elemental resists the character would have in ``act``.

    PoB-derived facts carry the penalty recorded with them (unrecorded = PoB's endgame -60); in-game (manual)
    numbers carry the penalty of ``current_act``. Strip it, add ``act``'s penalty, cap at the max resist.
    """
    if baseline is None:
        return None
    target = resist_penalty_for_act(act)
    out = {}
    for el, _ in _ELEMENTS:
        fact = getattr(baseline, f"raw_{el}_res")
        if fact.value is None:
            return None
        if fact.source == BaselineSource.MANUAL_USER_INPUT:
            used = resist_penalty_for_act(current_act)
        else:
            used = -60 if baseline.resist_penalty is None else baseline.resist_penalty
        cap = getattr(baseline, f"max_{el}_res").value or RES_TARGET
        out[el] = min(fact.value - used + target, cap)
    return out


def _resist_objective(baseline: Any, act: int) -> dict[str, Any] | None:
    now = resist_by_act(baseline, act, act)
    if now is None:
        return None
    nxt = _next_act(act)
    target_act = nxt or act
    then = resist_by_act(baseline, target_act, act)
    gaps = {el: RES_TARGET - v for el, v in then.items() if v < RES_TARGET}
    if not gaps:
        return None
    names = dict(_ELEMENTS)
    title = f"Resistance untuk {act_label(target_act)}: kurang " + ", ".join(f"{names[el]} {g}%" for el, g in gaps.items())
    rationale = (f"Sekarang " + "/".join(f"{now[el]}%" for el, _ in _ELEMENTS)
                 + f" ({act_label(act)}, penalti Resistance {resist_penalty_for_act(act)}%).")
    if nxt:
        rationale += (f" Di {act_label(nxt)} penalti Resistance {resist_penalty_for_act(nxt)}%: jadi "
                      + "/".join(f"{then[el]}%" for el, _ in _ELEMENTS) + ".")
    critical = min(then.values()) < 30
    return _objective("resist", 5 if critical else 4, title,
                      "Cari Resistance + maximum Life di gloves, ring, helm, boots, belt (regex vendor di bawah).", rationale,
                      cost=4 if critical else 3)


def _gem_objective(profile: GuideProfile, act: int) -> dict[str, Any] | None:
    for note in profile.gem_notes:
        acts = [int(a) for a in _ACT_TITLE.findall(note.title)]
        if act in acts or (act == 6 and "interlude" in note.title.lower()):
            if note.steps:
                return _objective(f"gems:{act}", 4, f"Gem {note.title} (guide)", "\n".join(f"• {s}" for s in note.steps),
                                  f"Progres gem dari {profile.name}.")
    return None


_ALL_RES = {"FIRE_RESISTANCE", "COLD_RESISTANCE", "LIGHTNING_RESISTANCE"}


def _weight(mod: str) -> int:
    return 3 if "to level of" in mod.lower() else 1  # +skill levels outweigh every other leveling mod


def slot_gaps(runtime_dir: Path, char_id: str, stage: GuideStage) -> list[tuple[str, float, list[str]]]:
    """(slot, weighted share of guide mods still missing, missing mods), biggest gap first (weapons weigh 1.5x)."""
    out = []
    for slot, item in stage.items.items():
        if not item.mods or item.is_unique:
            continue
        raw = get_current_raw(runtime_dir, char_id, slot)
        try:
            have = {mod_family(m.raw_text) for m in parse_item_text(raw).modifiers} if raw else set()
        except Exception:
            have = set()
        if "ALL_ELEMENTAL_RESISTANCE" in have:
            have |= _ALL_RES
        missing = [m for m in item.mods if mod_family(m) not in have]
        gap = sum(map(_weight, missing)) / sum(map(_weight, item.mods))
        out.append((slot, gap, missing))
    return sorted(out, key=lambda t: -t[1] * (1.5 if t[0] in _WEAPON_SLOTS else 1))


def _slot_objectives(runtime_dir: Path, char_id: str, stage: GuideStage) -> list[dict[str, Any]]:
    out = []
    for slot, gap, missing in slot_gaps(runtime_dir, char_id, stage)[:3]:
        if gap < 0.4:
            break
        item = stage.items[slot]
        out.append(_objective(
            f"slot:{slot}", 4 if slot in _WEAPON_SLOTS else 3,
            f"Upgrade {slot}: {round((1 - gap) * 100)}% cocok guide",
            "Cari mod: " + "; ".join(sorted(missing, key=_weight, reverse=True)[:4]),
            f"Target guide: {item.name} ({item.item_class}). Cek kandidat dengan Ctrl+C di dashboard.",
        ))
    return out


def vendor_regex(profile: GuideProfile, need_resist: bool) -> str | None:
    """The guide's vendor regex, with resistances added to its mod group when resists are short."""
    rx = profile.vendor_regex
    if not rx or not need_resist or "resi" in rx:
        return rx
    groups = re.findall(r'"[^"]*"', rx)
    mods = next((g for g in groups if "|" in g and not g.startswith('"s:') and not g.startswith('"y:')), None)
    return rx.replace(mods, mods[:-1] + '|resi"', 1) if mods else f'{rx} "resi"'


def guide_objectives(runtime_dir: Path, char_id: str) -> dict[str, Any] | None:
    """Objectives from the character's assigned guide; None when it has no guide."""
    slug, override = get_assignment(runtime_dir, char_id)
    profile = load_guide(runtime_dir, slug) if slug else None
    if profile is None:
        return None
    level, act = character_level_and_act(runtime_dir, char_id)
    stage = resolve_stage(profile, level, override)
    baseline = load_baseline(runtime_dir, char_id)

    objectives = [o for o in (_resist_objective(baseline, act), _gem_objective(profile, act)) if o]
    objectives += _slot_objectives(runtime_dir, char_id, stage)
    rx = vendor_regex(profile, any(o["id"] == "guide:resist" for o in objectives))
    if rx:
        objectives.append(_objective("regex", 2, "Regex vendor (salin ke kotak cari vendor)", rx,
                                     "Dari guide; ditambah resist bila resist kurang."))
    objectives.sort(key=lambda o: -o["priority"])
    return {
        "character_id": char_id, "character_level": level, "act": act, "guide": profile.name,
        "primary_objective": objectives[0] if objectives else None,
        "all_objectives": objectives, "status": "guide",
    }


def rank_slots(runtime_dir: Path, char_id: str, pob_session: Any) -> dict[str, Any]:
    """PoB2 gain of putting each guide item into its slot: the slots whose upgrade pays most come first.

    Guide items are the guide's end-of-stage targets, so the numbers show potential, not a buy list.
    ponytail: one PoB measurement per slot (~seconds each); run on demand, never on the status poll.
    """
    slug, override = get_assignment(runtime_dir, char_id)
    profile = load_guide(runtime_dir, slug) if slug else None
    if profile is None:
        return {"error": "Karakter belum punya guide."}
    if pob_session is None or not getattr(pob_session, "is_available", False):
        return {"error": "PoB2 tidak tersedia."}
    level, zone = _level_and_zone(runtime_dir, char_id)
    stage = resolve_stage(profile, level, override)
    if hasattr(pob_session, "apply_zone"):
        pob_session.apply_zone(zone, level)
    rows, skipped = [], []
    for slot, item in stage.items.items():
        if not item.raw_text:
            skipped.append(f"{slot} ({item.name}): unique, teks item tidak ada")
            continue
        cid = pob_session.submit_candidate(item.raw_text, item.name, slot, "ranking")
        delta = pob_session.measure(slot, item.raw_text, cid, source="ranking", main_skill=stage.main_skill)
        if delta is None:
            skipped.append(f"{slot} ({item.name}): PoB2 gagal mengukur")
            continue
        dps = (delta.dps_after - delta.dps_before) / delta.dps_before if delta.dps_before else 0.0
        ehp = (delta.ehp_after - delta.ehp_before) / delta.ehp_before if delta.ehp_before else 0.0
        rows.append({"slot": slot, "guide_item": item.name, "current_item": delta.current_item_name,
                     "dps_pct": round(dps, 4), "ehp_pct": round(ehp, 4)})
    rows.sort(key=lambda r: -(r["dps_pct"] + r["ehp_pct"]))
    return {"success": True, "stage": stage.title, "main_skill": stage.main_skill, "rows": rows, "skipped": skipped}
