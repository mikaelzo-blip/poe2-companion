"""Single guide-aware evaluation pipeline: safety gate, slot plans, measurement, policy, tactical veto."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from companion.builds.guide import GuideStage
from companion.builds.priorities import PrioritySignal, priority_signal
from companion.builds.stages import resolve_stage
from companion.builds.store import get_assignment, load_guide
from companion.equipment.baseline_cli import load_baseline
from companion.equipment.current_item import character_level_and_zone, get_current_item_info, get_current_raw
from companion.equipment.loadout_cli import load_loadout
from companion.equipment.parser import parse_item_text
from companion.equipment.partial_projection import project_candidate_on_loadout
from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
from companion.equipment.policy import VERDICT_RANK, SlotResult, decide, insufficient, rejected
from companion.equipment.safety import breaker_reasons, weapon_not_in_guide
from companion.equipment.schema import SlotType
from companion.equipment.slot_resolver import SlotPlan, item_class_of, resolve_slots
from companion.equipment.tactical_advisor import generate_tactical_advice, merge_verdicts

logger = logging.getLogger(__name__)

_WEAPON_SLOTS = ("Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap")
_FALLBACK_REASON = "PoB2 tidak memberi hasil; memakai estimasi"
_RES_KEYS = ("fire", "cold", "lightning", "chaos")


class GuideSignal(BaseModel):
    name: str
    stage_title: str
    priority_match: float | None = None
    must_have_missing: list[str] = []
    target_fit: dict[str, float] | None = None  # Phase 4


class EvaluationResult(BaseModel):
    verdict: str
    engine: str
    engine_reason: str | None = None
    slot: str
    slot_reason: str
    per_slot: list[SlotResult]
    dims: dict[str, float] = {}
    guide: GuideSignal | None = None
    safety: list[str] = []
    reasons: list[str] = []
    trade_offs: list[str] = []
    gains: list[str] = []
    tactical_advice: dict | None = None
    current_item_name: str | None = None
    item_name: str
    base_type: str


def _fact(baseline: Any, name: str) -> int | None:
    fact = getattr(baseline, name, None)
    return fact.value if fact is not None and fact.is_known else None


def _unmet_requirements(candidate: Any, level: int | None, baseline: Any) -> list[str]:
    unmet = []
    if level is not None and candidate.required_level > level:
        unmet.append(f"Level {candidate.required_level} (karakter level {level})")
    for label, need, attr in (
        ("Str", candidate.required_str, "strength"),
        ("Dex", candidate.required_dex, "dexterity"),
        ("Int", candidate.required_int, "intelligence"),
    ):
        have = _fact(baseline, attr)
        if need and have is not None and need > have:
            unmet.append(f"{label} {need} (karakter {have})")
    return unmet


def _heuristic_delta(runtime_dir: Path, char_id: str, candidate: Any, slot: str, baseline: Any) -> PobEquipmentDelta | None:
    proj = project_candidate_on_loadout(load_loadout(runtime_dir, char_id), candidate, SlotType.from_str(slot), baseline)
    if not proj.life.is_absolute_known:
        return None
    life_after = int(proj.life.projected_absolute)
    life_before = life_after - int(proj.life.delta)
    res_before: dict[str, float] = {}
    res_after: dict[str, float] = {}
    for key in _RES_KEYS:
        stat = getattr(proj, f"{key}_res")
        if stat.is_absolute_known:
            res_after[key] = stat.projected_absolute
            res_before[key] = stat.projected_absolute - stat.delta
    return PobEquipmentDelta(
        slot=slot, candidate_id=0, candidate_name=candidate.name or candidate.base_type,
        life_delta=life_after - life_before, armour_delta=int(proj.armour.delta),
        evasion_delta=int(proj.evasion.delta), es_delta=int(proj.energy_shield.delta),
        fire_res_delta=int(proj.fire_res.delta), cold_res_delta=int(proj.cold_res.delta),
        lightning_res_delta=int(proj.lightning_res.delta), chaos_res_delta=int(proj.chaos_res.delta),
        movement_speed_delta=float(proj.movement_speed.delta),
        strength_delta=int(proj.strength.delta), dexterity_delta=int(proj.dexterity.delta),
        intelligence_delta=int(proj.intelligence.delta),
        life_before=life_before, life_after=life_after, ehp_before=float(life_before),
        ehp_after=float(life_after), ehp_delta=float(life_after - life_before),
        res_before=res_before, res_after=res_after,
    )


def _read_char(runtime_dir: Path, char_id: str) -> dict[str, Any]:
    path = runtime_dir / "characters" / f"{char_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        logger.warning("Failed to read character file %s", char_id, exc_info=True)
        return {}


def _resolve_guide(runtime_dir: Path, char_id: str, level: int | None, stage_override: str | None):
    slug, stored_override = get_assignment(runtime_dir, char_id)
    profile = load_guide(runtime_dir, slug) if slug else None
    if profile is None or not profile.stages:
        return None, GuideStage(id="all", title="Karakter saja")
    return profile, resolve_stage(profile, level, stage_override or stored_override)


def evaluate(
    raw_text: str,
    character_id: str,
    *,
    runtime_dir: Path,
    pob_session: Any | None,
    source: Literal["manual", "auto", "cli"],
    locked_slot: str | None = None,
    zone: str | None = None,
    stage_override: str | None = None,
) -> EvaluationResult:
    try:
        candidate = parse_item_text(raw_text)
    except Exception as exc:
        raise ValueError(f"Item tidak bisa dibaca: {exc}") from exc

    runtime_dir = Path(runtime_dir)
    char_data = _read_char(runtime_dir, character_id)
    file_level, file_zone = character_level_and_zone(char_data)
    pob_level = getattr(pob_session, "level", None)
    levels = [v for v in (file_level, pob_level) if isinstance(v, int)]
    level = max(levels, default=None)
    zone = zone or file_zone
    baseline = load_baseline(runtime_dir, character_id)
    profile, stage = _resolve_guide(runtime_dir, character_id, level, stage_override)

    item_class = item_class_of(raw_text)
    plans, slot_reason = resolve_slots(candidate, item_class, stage, locked_slot)
    mods = [m.raw_text for m in candidate.modifiers]
    pob_ok = pob_session is not None and bool(getattr(pob_session, "is_available", False))
    state = {"pob_ok": pob_ok, "reason": None if pob_ok else "PoB2 tidak tersedia", "cid": None}
    raws: dict[str, str] = {}

    def current_raw(slot: str) -> str:
        if slot not in raws:
            raws[slot] = get_current_raw(runtime_dir, character_id, slot, pob_session if pob_ok else None)
        return raws[slot]

    def is_empty(slot: str, via_pob: bool) -> bool:
        if via_pob:
            try:
                return bool(pob_session.is_slot_empty(slot))
            except Exception:
                logger.warning("PoB2 is_slot_empty failed for %s", slot, exc_info=True)
        return current_raw(slot) == ""

    def measure_pob(plan: SlotPlan) -> PobEquipmentDelta | None:
        try:
            if state["cid"] is None:
                state["cid"] = pob_session.submit_candidate(raw_text, candidate.name, plans[0].slot, source)
            return pob_session.measure(plan.slot, raw_text, state["cid"], source=source, clear_slots=plan.clear_slots)
        except Exception:
            logger.warning("PoB2 measurement failed for %s", plan.slot, exc_info=True)
            return None

    weapon_veto = weapon_not_in_guide(item_class, profile)
    unmet = _unmet_requirements(candidate, level, baseline)
    results: list[SlotResult] = []
    signals: dict[str, PrioritySignal | None] = {}
    vetoed: set[str] = set()
    heuristic_used = False
    for plan in plans:
        slot = plan.slot
        signals[slot] = priority_signal(stage.items.get(slot), mods)
        reasons = [weapon_veto] if weapon_veto else breaker_reasons(mods, profile, level, slot)
        if reasons:
            vetoed.add(slot)
            results.append(rejected(slot, reasons))
            continue
        empty = is_empty(slot, state["pob_ok"])
        if not empty:
            cur = current_raw(slot)
            try:
                parsed = parse_item_text(cur) if cur else None
            except Exception:
                logger.warning("Current item in %s unparseable", slot, exc_info=True)
                parsed = None
            if parsed and candidate.rarity in ("rare", "unique") and (parsed.name, parsed.base_type) == (candidate.name, candidate.base_type):
                return EvaluationResult(
                    verdict="ALREADY_EQUIPPED", engine="pob2" if pob_ok else "heuristic",
                    engine_reason=state["reason"], slot=slot, slot_reason=slot_reason, per_slot=[],
                    item_name=candidate.name or candidate.base_type, base_type=candidate.base_type,
                    current_item_name=parsed.name or parsed.base_type,
                )
        delta = None
        if state["pob_ok"]:
            delta = measure_pob(plan)
            if delta is None:
                state["pob_ok"], state["reason"] = False, _FALLBACK_REASON
                empty = current_raw(slot) == ""
        if delta is None:
            heuristic_used = True
            if slot in _WEAPON_SLOTS:
                results.append(insufficient(slot, "Tanpa PoB2 senjata tidak bisa dinilai"))
                continue
            delta = _heuristic_delta(runtime_dir, character_id, candidate, slot, baseline)
            if delta is None:
                results.append(insufficient(slot, "Life baseline belum diketahui"))
                continue
        results.append(decide(delta, unmet_requirements=unmet, priority=signals[slot], is_empty=empty))

    chosen = max(results, key=lambda r: (r.is_empty and r.verdict != "REJECT", VERDICT_RANK[r.verdict], r.dps_pct, r.ehp_pct))
    verdict, tactical_dump, reasons = chosen.verdict, None, list(chosen.reasons)
    if chosen.delta is not None:
        stats = {**char_data, **(baseline.model_dump() if baseline else {})}
        tactical = generate_tactical_advice(
            chosen.delta, raw_text, current_raw(chosen.slot), zone, level, base_verdict=chosen.verdict, character_stats=stats,
        )
        verdict = merge_verdicts(chosen.verdict, tactical.verdict)
        tactical_dump = tactical.model_dump(mode="json")
        if verdict != chosen.verdict:
            reasons.append(tactical.tactical_headline)

    d = chosen.delta
    dims = {} if d is None else {
        "dps_pct": chosen.dps_pct, "ehp_pct": chosen.ehp_pct, "life": d.life_delta, "armour": d.armour_delta,
        "evasion": d.evasion_delta, "energy_shield": d.es_delta, "fire_res": d.fire_res_delta,
        "cold_res": d.cold_res_delta, "lightning_res": d.lightning_res_delta, "chaos_res": d.chaos_res_delta,
        "movement_speed": d.movement_speed_delta,
    }
    sig = signals.get(chosen.slot)
    current_name = get_current_item_info(runtime_dir, character_id, chosen.slot, pob_session if pob_ok else None)[0]
    return EvaluationResult(
        verdict=verdict,
        engine="heuristic" if heuristic_used or not pob_ok else "pob2",
        engine_reason=state["reason"], slot=chosen.slot, slot_reason=slot_reason, per_slot=results, dims=dims,
        guide=None if profile is None else GuideSignal(
            name=profile.name, stage_title=stage.title, priority_match=sig.ratio if sig else None,
            must_have_missing=list(sig.must_have_missing) if sig else [],
        ),
        safety=list(chosen.reasons) if chosen.slot in vetoed else [],
        reasons=reasons, trade_offs=chosen.trade_offs, gains=chosen.gains, tactical_advice=tactical_dump,
        current_item_name=None if current_name == "Slot Kosong" else current_name,
        item_name=candidate.name or candidate.base_type, base_type=candidate.base_type,
    )
