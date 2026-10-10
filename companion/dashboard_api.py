"""Web API endpoints for PoE2 Companion Dashboard local server."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import time
from pathlib import Path
from typing import Any

from companion.equipment.clipboard import get_clipboard_text
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.fubgun_priorities import evaluate_fubgun_weapon_policy, evaluate_fubgun_equipment_policy
from companion.equipment.recommendation import Verdict
from companion.equipment.tactical_advisor import TacticalAdvice, generate_tactical_advice, merge_verdicts
from companion.equipment.live_watcher import evaluate_live_candidate
from companion.equipment.parser import parse_item_text
from companion.equipment.pob2_equipment_advisor import (
    Pob2EquipmentSession,
    PobEquipmentDelta,
    load_pob_mcp_modules,
    normalize_and_validate_pob_slot,
    resolve_pob2_backend_path,
)
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore

logger = logging.getLogger(__name__)

_STAGE_MAP = {
    "lvl 1-14": BuildProgressionStage.LEVELING_1_14,
    "lvl 15-32": BuildProgressionStage.LEVELING_15_32,
    "lvl 33-51": BuildProgressionStage.LEVELING_33_51,
    "lvl 52 swap": BuildProgressionStage.SWAP_52,
    "lvl 53-68": BuildProgressionStage.LEVELING_53_68,
    "lvl 85": BuildProgressionStage.LEVEL_85,
    "endgame": BuildProgressionStage.ENDGAME,
    "mageblood": BuildProgressionStage.MAGEBLOOD,
    "dot cap": BuildProgressionStage.DOT_CAP,
    # Navira stages approximated onto the Fubgun stage enum (no Navira-specific policy exists).
    "act 1 & 2": BuildProgressionStage.LEVELING_1_14,
    "act 2": BuildProgressionStage.LEVELING_15_32,
    "act 3": BuildProgressionStage.LEVELING_15_32,
    "act 4 to endgame": BuildProgressionStage.LEVELING_33_51,
    "early endgame": BuildProgressionStage.LEVELING_53_68,
    "mid-endgame": BuildProgressionStage.LEVEL_85,
    "late endgame": BuildProgressionStage.LEVEL_85,
    "uber endgame": BuildProgressionStage.ENDGAME,
}


def _resolve_stage(stage_str: str | None, char_level: int | None) -> BuildProgressionStage:
    """Map a stage label to an enum; auto/legacy "lvl 1-14"/unknown labels infer from level."""
    from companion.equipment.fubgun_priorities import infer_stage_from_level

    key = (stage_str or "").strip().lower()
    if key in _STAGE_MAP and key != "lvl 1-14":
        return _STAGE_MAP[key]
    if char_level and char_level >= 15:
        return infer_stage_from_level(char_level)
    return BuildProgressionStage.LEVELING_1_14


def get_current_raw(
    runtime_dir: Path,
    char_id: str,
    slot_name: str,
    pob_session: Any | None = None,
) -> str:
    """Retrieve raw text of equipped item for given slot, from PoB session or local loadout."""
    if pob_session is not None:
        pob_slot_candidates = [slot_name]
        try:
            from companion.equipment.schema import SlotType
            st = SlotType.from_str(slot_name)
            pob_mapping = {
                SlotType.HELMET: "Helmet",
                SlotType.BODY_ARMOUR: "Body Armour",
                SlotType.GLOVES: "Gloves",
                SlotType.BOOTS: "Boots",
                SlotType.AMULET: "Amulet",
                SlotType.RING_1: "Ring 1",
                SlotType.RING_2: "Ring 2",
                SlotType.BELT: "Belt",
                SlotType.MAIN_HAND: "Weapon 1",
                SlotType.OFF_HAND: "Weapon 2",
            }
            if st in pob_mapping and pob_mapping[st] not in pob_slot_candidates:
                pob_slot_candidates.insert(0, pob_mapping[st])
        except Exception:
            pass

        for p_slot in pob_slot_candidates:
            try:
                eq = pob_session.get_equipped_item(p_slot)
                if isinstance(eq, dict) and eq.get("raw"):
                    from companion.equipment.pob_item_text import pob_item_to_clipboard
                    return pob_item_to_clipboard(eq["raw"])
            except Exception:
                pass  # includes PobItemTextError: fall back to the loadout text

    try:
        from companion.equipment.loadout_cli import load_loadout
        from companion.equipment.schema import SlotType, WeaponSetContext
        lo = load_loadout(runtime_dir, char_id)
        if lo:
            w_ctx = None
            norm = slot_name.lower().strip()
            if "set2" in norm or "swap" in norm:
                w_ctx = WeaponSetContext.WEAPON_SET_2
            elif "set1" in norm:
                w_ctx = WeaponSetContext.WEAPON_SET_1

            try:
                st = SlotType.from_str(slot_name)
                entry = lo.get_slot(st, weapon_set=w_ctx)
                if entry and entry.item and entry.item.raw_text:
                    return entry.item.raw_text
            except Exception:
                pass

            direct_keys = [
                slot_name.lower().replace(" ", "_"),
                slot_name.lower().replace(" ", "").replace("_", ""),
            ]
            for dk in direct_keys:
                entry = lo.shared_slots.get(dk)
                if entry and entry.item and entry.item.raw_text:
                    return entry.item.raw_text
    except Exception:
        pass
    return ""


def get_current_item_info(
    runtime_dir: Path,
    char_id: str,
    slot_name: str,
    pob_session: Any | None = None,
) -> tuple[str, str]:
    """Retrieve (item_name, base_type) of equipped item for given slot."""
    # 1. PoB session if available
    if pob_session is not None:
        try:
            p_name = pob_session.get_current_item_name(slot_name)
            if p_name and p_name != "Unobserved":
                return str(p_name), ""
        except Exception:
            pass

    # 2. Local loadout
    try:
        from companion.equipment.loadout_cli import load_loadout
        from companion.equipment.schema import SlotType, WeaponSetContext
        lo = load_loadout(runtime_dir, char_id)
        if lo:
            w_ctx = None
            norm = slot_name.lower().strip()
            if "set2" in norm or "swap" in norm:
                w_ctx = WeaponSetContext.WEAPON_SET_2
            elif "set1" in norm:
                w_ctx = WeaponSetContext.WEAPON_SET_1

            try:
                st = SlotType.from_str(slot_name)
                entry = lo.get_slot(st, weapon_set=w_ctx)
                if entry and entry.item and (entry.item.name or entry.item.base_type):
                    return entry.item.name or entry.item.base_type, entry.item.base_type or ""
            except Exception:
                pass

            direct_keys = [
                slot_name.lower().replace(" ", "_"),
                slot_name.lower().replace(" ", "").replace("_", ""),
            ]
            for dk in direct_keys:
                entry = lo.shared_slots.get(dk)
                if entry and entry.item and (entry.item.name or entry.item.base_type):
                    return entry.item.name or entry.item.base_type, entry.item.base_type or ""
    except Exception:
        pass

    # 3. Parse current raw item text
    try:
        raw = get_current_raw(runtime_dir, char_id, slot_name, pob_session)
        if raw:
            from companion.equipment.parser import parse_item_text
            parsed = parse_item_text(raw)
            if parsed.name or parsed.base_type:
                return parsed.name or parsed.base_type, parsed.base_type or ""
    except Exception:
        pass

    return "Slot Kosong", ""


def resolve_char_id(char_id: str | None, runtime_dir: Path) -> str:
    """Match a character ID case-insensitively against runtime/characters/*.json (default BOMSHAK)."""
    raw = str(char_id or "").strip() or "BOMSHAK"
    chars_dir = runtime_dir / "characters"
    if chars_dir.is_dir():
        for f in chars_dir.glob("*.json"):
            if f.stem.lower() == raw.lower():
                return f.stem
    return raw


def _stamp_evaluated(res: dict[str, Any]) -> dict[str, Any]:
    if res.get("success"):
        res.setdefault("evaluated_at", datetime.now(timezone.utc).isoformat())
    return res


_SLOT_DISPLAY = {
    "ring1": "Ring 1",
    "ring2": "Ring 2",
    "main_hand": "Main Hand",
    "off_hand": "Off Hand",
    "body_armour": "Body Armour",
    "weapon1": "Weapon 1",
    "weapon2": "Weapon 2",
    "weapon1_swap": "Weapon 1 Swap",
    "weapon2_swap": "Weapon 2 Swap",
}


@dataclass
class _EvalContext:
    """Everything an evaluation branch needs about the candidate, character and zone."""

    raw_text: str
    runtime_dir: Path
    char_id: str
    pob_session: Any
    candidate: Any
    requested_slot: str | None
    guide: str
    stage: BuildProgressionStage
    zone_id: str | None
    zone_profile: Any
    char_level: int | None
    char_stats: dict[str, Any]
    is_weapon: bool

    @property
    def name(self) -> str:
        return self.candidate.name or self.candidate.base_type

    def slot_key(self, default: str) -> str:
        return self.requested_slot or (self.candidate.slot.value if self.candidate.slot else default)

    def current_info(self, slot: str) -> tuple[str, str]:
        return get_current_item_info(self.runtime_dir, self.char_id, slot, self.pob_session)

    def tactical(self, delta: Any, slot: str) -> TacticalAdvice:
        return generate_tactical_advice(
            delta=delta,
            candidate_raw=self.raw_text,
            current_raw=get_current_raw(self.runtime_dir, self.char_id, slot, self.pob_session),
            zone_id=self.zone_id,
            character_level=self.char_level,
            stage=self.stage,
            character_stats=self.char_stats,
        )

    def result(self, engine: str, **fields: Any) -> dict[str, Any]:
        return {
            "success": True,
            "engine": engine,
            "item_name": self.name,
            "base_type": self.candidate.base_type,
            **fields,
        }


def character_level_and_zone(char_data: dict[str, Any]) -> tuple[int | None, str | None]:
    """Read level and current_zone from character JSON (each either {"value": x} or plain)."""
    def plain(v: Any) -> Any:
        return v.get("value") if isinstance(v, dict) else v

    lvl, zone = plain(char_data.get("level")), plain(char_data.get("current_zone"))
    return (lvl if isinstance(lvl, int) else None), (zone if isinstance(zone, str) else None)


def _build_eval_context(
    payload: dict[str, Any], raw_text: str, runtime_dir: Path, pob_session: Any | None
) -> _EvalContext | dict[str, Any]:
    """Load character/zone/stage context and parse the candidate (error dict on parse failure)."""
    from companion.equipment.zone_threats import get_zone_threat_profile

    char_id = resolve_char_id(payload.get("character_id"), runtime_dir)
    session_level = getattr(pob_session, "level", None) if pob_session is not None else None
    file_level = None
    zone_id = payload.get("zone")
    char_class = None
    char_stats: dict[str, Any] = {}
    try:
        char_file = runtime_dir / "characters" / f"{char_id}.json"
        if char_file.is_file():
            c_data = json.loads(char_file.read_text(encoding="utf-8"))
            char_class = c_data.get("character_class")
            char_stats.update(c_data)
            file_level, file_zone = character_level_and_zone(c_data)
            zone_id = zone_id or file_zone
    except Exception:
        logging.getLogger(__name__).warning("Failed to read character file %s", char_id, exc_info=True)
    char_level = max((v for v in (session_level, file_level) if v is not None), default=None)

    try:
        from companion.equipment.baseline_cli import load_baseline
        b_data = load_baseline(runtime_dir, char_id)
        if b_data:
            char_stats.update(b_data.model_dump())
    except Exception:
        logging.getLogger(__name__).warning("Failed to load baseline %s", char_id, exc_info=True)

    guide = payload.get("guide")
    if guide:
        guide = guide.lower().strip()
    elif char_class and "sorceress" in char_class.lower():
        guide = "navira_varashta"
    elif char_class and "mercenary" not in char_class.lower():
        guide = "generic_pob2"
    else:
        guide = "fubgun_flameblast"

    try:
        candidate = parse_item_text(raw_text)
    except Exception as exc:
        return {"error": f"Failed to parse item: {exc}"}

    is_weapon = candidate.slot in (SlotType.MAIN_HAND, SlotType.OFF_HAND) or any(
        w in candidate.base_type for w in ("Crossbow", "Staff", "Bow", "Wand", "Sceptre")
    )
    return _EvalContext(
        raw_text=raw_text,
        runtime_dir=runtime_dir,
        char_id=char_id,
        pob_session=pob_session,
        candidate=candidate,
        requested_slot=payload.get("slot"),
        guide=guide,
        stage=_resolve_stage(payload.get("stage", "lvl 1-14"), char_level),
        zone_id=zone_id,
        zone_profile=get_zone_threat_profile(zone_id, character_level=char_level),
        char_level=char_level,
        char_stats=char_stats,
        is_weapon=is_weapon,
    )


def _zone_reject_report(ctx: _EvalContext, slot: str, fallback_display: str, tactical: TacticalAdvice) -> str:
    """Report text used when zone-aware tactical advice overrides a non-REJECT policy verdict."""
    disp_slot = _SLOT_DISPLAY.get(slot.lower().replace(" ", ""), fallback_display)
    return (
        f"=== Zone-Aware Equipment Recommendation ===\n"
        f"Candidate : {ctx.name}\n"
        f"Slot      : {disp_slot}\n"
        f"Verdict   : REJECT (HOLD CURRENT GEAR)\n"
        f"Reason    : {tactical.tactical_headline}\n"
        f"Action    : {tactical.actionable_recommendation}\n"
    )


def _incompatible_weapon(
    ctx: _EvalContext, engine: str, reason: str, headline: str, action: str, formatted: str
) -> dict[str, Any]:
    tactical = TacticalAdvice(
        verdict=Verdict.REJECT,
        verdict_badge="🛑 SENJATA INKOMPATIBEL",
        tactical_headline=headline,
        zone_name=ctx.zone_profile.friendly_name,
        zone_threat_warning=ctx.zone_profile.survival_notes,
        actionable_recommendation=action,
        trade_off_bullets=[reason],
    )
    return ctx.result(
        engine,
        slot=ctx.slot_key("main_hand"),
        verdict=Verdict.REJECT.value,
        reason=reason,
        gains=[],
        trade_offs=[reason],
        formatted_report=formatted,
        dps_delta=0.0,
        life_delta=0,
        is_weapon=True,
        tactical_advice=tactical.model_dump(),
    )


def _pob2_generic_weapon(ctx: _EvalContext, delta: Any) -> dict[str, Any]:
    """Generic / Navira weapon verdict straight from PoB2 DPS, Life and EHP deltas."""
    dps = getattr(delta, "dps_delta", 0.0) or 0.0
    life = getattr(delta, "life_delta", 0.0) or 0.0
    ehp = getattr(delta, "ehp_delta", 0.0) or 0.0

    gains: list[str] = []
    trade_offs: list[str] = []
    for value, text in ((dps, f"{dps:.1f}% DPS"), (life, f"{life:.0f} Life"), (ehp, f"{ehp:.1f} EHP")):
        if value > 0:
            gains.append(f"+{text}")
        elif value < 0:
            trade_offs.append(text)

    prefix = "⚡ UPGRADE SORCERESS" if ctx.guide == "navira_varashta" else "⚔️ UPGRADE SENJATA"
    if dps > 0 and ehp >= -5.0:
        verdict = Verdict.EQUIP_NOW
        badge = f"{prefix} (PoB2)"
        headline = f"Senjata ini memberikan kenaikan {dps:+.1f}% DPS!"
        action = "Pasang sekarang ke slot senjata aktif Anda."
    elif dps > 0:
        verdict = Verdict.CONDITIONAL_UPGRADE
        badge = "⚖️ UPGRADE BERSYARAT (DPS NAIK)"
        headline = f"DPS naik {dps:+.1f}%, namun ada penurunan pertahanan."
        action = "Pertimbangkan jika Anda membutuhkan damage ekstra dan pertahanan masih cukup."
    elif dps < 0:
        verdict = Verdict.REJECT
        badge = "🛑 REJECT / DPS TURUN"
        headline = f"DPS turun {dps:.1f}% dibandingkan senjata saat ini."
        action = "Jangan pasang. Senjata saat ini memberikan output damage lebih tinggi."
    else:
        verdict = Verdict.CONDITIONAL_UPGRADE
        badge = "⚖️ STATS IDENTIK"
        headline = "DPS identik dengan senjata saat ini."
        action = "Bandingkan affix pendukung lainnya."

    tactical = TacticalAdvice(
        verdict=verdict,
        verdict_badge=badge,
        tactical_headline=headline,
        zone_name=ctx.zone_profile.friendly_name,
        zone_threat_warning=ctx.zone_profile.survival_notes,
        actionable_recommendation=action,
        gains_bullets=gains,
        trade_off_bullets=trade_offs,
    )
    policy_label = "Navira Varashta Optimizer" if ctx.guide == "navira_varashta" else "PoB2 Generic Optimizer"
    return ctx.result(
        "pob2",
        slot=ctx.slot_key("main_hand"),
        verdict=verdict.value,
        reason=headline,
        gains=gains,
        trade_offs=trade_offs,
        formatted_report=f"{badge}\n\n{ctx.name}\n\n{headline}\n{action}",
        policy_verdict=f"{policy_label}: {badge}",
        dps_delta=dps,
        life_delta=life,
        is_weapon=True,
        tactical_advice=tactical.model_dump(),
    )


def _pob2_ambiguous_1h(ctx: _EvalContext, route_res: Any, cid: Any) -> dict[str, Any] | None:
    """Simulate a 1H weapon in both hands of the target set and let the dual policy pick."""
    from companion.equipment.fubgun_priorities import evaluate_dual_weapon_policy

    dual_wep = ctx.pob_session.simulate_ambiguous_1h_weapon(
        raw_candidate=ctx.raw_text,
        candidate_id=cid,
        candidate_name=ctx.name,
        target_set=route_res.target_set,
        build_stage=ctx.stage,
    )
    if dual_wep is None or not dual_wep.slot1_delta or not dual_wep.slot2_delta:
        return None
    swap = route_res.target_set == WeaponSetContext.WEAPON_SET_2
    advice = evaluate_dual_weapon_policy(
        dual_wep.slot1_delta,
        dual_wep.slot2_delta,
        stage=ctx.stage,
        slot1_name="Weapon 1 Swap" if swap else "Weapon 1",
        slot2_name="Weapon 2 Swap" if swap else "Weapon 2",
    )
    if not advice:
        return None
    rec_slot = advice.recommended_slot or (
        "Weapon 1" if route_res.target_set == WeaponSetContext.WEAPON_SET_1 else "Weapon 1 Swap"
    )
    return ctx.result(
        "pob2",
        slot=rec_slot.lower().replace(" ", "_"),
        recommended_slot=advice.recommended_slot,
        verdict=advice.summary_verdict,
        reason=advice.summary_verdict,
        gains=advice.rec1.gains + advice.rec2.gains,
        trade_offs=advice.trade_off_notes,
        formatted_report=advice.formatted_output,
        is_weapon=True,
    )


def _pob2_fubgun_weapon(ctx: _EvalContext, pob_slot: str, cid: Any) -> dict[str, Any] | None:
    """Fubgun weapon routing (compatibility, target set, 1H ambiguity) plus PoB2 simulation."""
    from companion.equipment.fubgun_weapon_router import FubgunWeaponProfileRouter

    sess = ctx.pob_session
    req = ctx.requested_slot
    current_name = getattr(sess, "get_current_item_name", lambda s: None)
    route_res = FubgunWeaponProfileRouter().route_candidate(
        candidate=ctx.candidate,
        stage=ctx.stage,
        raw_text=ctx.raw_text,
        candidate_id=cid,
        currently_equipped={s: current_name(s) for s in ("Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap")},
    )
    if not route_res.is_valid:
        reason = route_res.rejection_reason
        header = "🔴 REJECT / INCOMPATIBLE" if "breaker" not in reason.lower() else "🔴 REJECT / BUILD BREAKER"
        return _incompatible_weapon(
            ctx,
            "pob2",
            reason,
            headline=f"Senjata ini ({ctx.name}) tidak kompatibel dengan build aktif!",
            action=f"Jangan pasang! {reason}. Tetap gunakan senjata yang sesuai dengan skill build Anda.",
            formatted=f"{header}\n\n{ctx.name}\n\nReason:\n{reason}",
        )

    if not req:
        pob_slot = route_res.target_slot or pob_slot

    current_in_target = current_name(pob_slot)
    if current_in_target and ctx.candidate.name == current_in_target:
        return ctx.result(
            "pob2",
            slot=req or pob_slot.lower().replace(" ", "_"),
            verdict="ALREADY_EQUIPPED",
            reason=f"{pob_slot} is already recorded as Current Weapon ({ctx.candidate.name}).",
            gains=[],
            trade_offs=[],
            formatted_report=f"⚪ ALREADY EQUIPPED\n\n{ctx.candidate.name} is already equipped in {pob_slot}.",
            is_weapon=True,
        )

    if (
        not req
        and route_res.topology_plan
        and route_res.topology_plan.is_ambiguous_placement
        and hasattr(sess, "simulate_ambiguous_1h_weapon")
    ):
        res = _pob2_ambiguous_1h(ctx, route_res, cid)
        if res is not None:
            return res

    if not req and route_res.context and hasattr(sess, "simulate_weapon_plan"):
        delta = sess.simulate_weapon_plan(route_res.context)
    else:
        delta = sess.simulate_item(slot=pob_slot, raw_candidate=ctx.raw_text, candidate_id=cid, candidate_name=ctx.name)
    if delta is None:
        return None

    rec = evaluate_fubgun_weapon_policy(
        delta,
        skill_context=route_res.skill_context if not req else None,
        stage=ctx.stage,
        use_color=False,
    )
    tactical = ctx.tactical(delta, pob_slot)
    final_verdict = merge_verdicts(rec.verdict, tactical.verdict)
    zone_override = final_verdict == "REJECT" and getattr(rec.verdict, "value", str(rec.verdict)) != "REJECT"
    slot_key = ctx.slot_key("main_hand")
    cur_name, cur_base = ctx.current_info(slot_key)
    return ctx.result(
        "pob2",
        current_item_name=getattr(delta, "current_item_name", None) or cur_name,
        current_item_base_type=cur_base,
        slot=slot_key,
        verdict=final_verdict,
        reason=tactical.tactical_headline if zone_override else rec.reason,
        gains=rec.gains,
        trade_offs=rec.trade_offs,
        formatted_report=rec.formatted_output,
        dps_delta=getattr(delta, "dps_delta", 0.0),
        life_delta=getattr(delta, "life_delta", 0),
        is_weapon=True,
        tactical_advice=tactical.model_dump(),
    )


def _pob2_weapon(ctx: _EvalContext) -> dict[str, Any] | None:
    req = ctx.requested_slot
    if req in ("set2_main_hand", "Weapon 1 Swap"):
        pob_slot = "Weapon 1 Swap"
    elif req in ("set2_off_hand", "Weapon 2 Swap"):
        pob_slot = "Weapon 2 Swap"
    elif req in ("off_hand", "Weapon 2") or ctx.candidate.slot == SlotType.OFF_HAND:
        pob_slot = "Weapon 2"
    else:
        pob_slot = "Weapon 1"

    cid = ctx.pob_session.submit_candidate(ctx.raw_text, candidate_name=ctx.name, slot=pob_slot)
    if ctx.guide in ("generic_pob2", "navira_varashta"):
        delta = ctx.pob_session.simulate_item(
            slot=pob_slot, raw_candidate=ctx.raw_text, candidate_id=cid, candidate_name=ctx.name
        )
        if delta is not None:
            return _pob2_generic_weapon(ctx, delta)
    return _pob2_fubgun_weapon(ctx, pob_slot, cid)


def _pob2_ring(ctx: _EvalContext) -> dict[str, Any] | None:
    """Simulate the ring in both ring slots and pick the better one."""
    from companion.equipment.fubgun_priorities import evaluate_dual_ring_policy

    sess = ctx.pob_session
    cid = sess.submit_candidate(ctx.raw_text, candidate_name=ctx.name, slot="Ring 1")
    dual_res = sess.simulate_ring_candidate(raw_candidate=ctx.raw_text, candidate_id=cid, candidate_name=ctx.name)
    if dual_res is None:
        return None
    advice = evaluate_dual_ring_policy(
        dual_res.ring1_delta,
        dual_res.ring2_delta,
        stage=ctx.stage,
        empty_ring1=sess.is_slot_empty("Ring 1"),
        empty_ring2=sess.is_slot_empty("Ring 2"),
    )
    if not advice:
        return None

    r1, r2 = advice.ring1_recommendation, advice.ring2_recommendation
    if advice.recommended_slot == "Ring 1":
        ring_verdict, gains, chosen_delta = r1.verdict.value, r1.gains, dual_res.ring1_delta
        trade_offs = r1.trade_offs + advice.trade_off_notes
    elif advice.recommended_slot == "Ring 2":
        ring_verdict, gains, chosen_delta = r2.verdict.value, r2.gains, dual_res.ring2_delta
        trade_offs = r2.trade_offs + advice.trade_off_notes
    else:
        both_reject = r1.verdict == Verdict.REJECT and r2.verdict == Verdict.REJECT
        ring_verdict = Verdict.REJECT.value if both_reject else Verdict.CONDITIONAL_UPGRADE.value
        gains = list(dict.fromkeys(r1.gains + r2.gains))
        trade_offs = advice.trade_off_notes or list(dict.fromkeys(r1.trade_offs + r2.trade_offs))
        chosen_delta = dual_res.ring1_delta

    tactical = ctx.tactical(chosen_delta, advice.recommended_slot or "Ring 1")
    final_verdict = merge_verdicts(ring_verdict, tactical.verdict)
    target_slot = (
        advice.recommended_slot.lower().replace(" ", "")
        if advice.recommended_slot
        else (ctx.requested_slot or "ring1")
    )
    cur_name, cur_base = ctx.current_info(target_slot)
    zone_override = final_verdict == "REJECT" and ring_verdict != "REJECT"
    return ctx.result(
        "pob2",
        current_item_name=getattr(chosen_delta, "current_item_name", None) or cur_name,
        current_item_base_type=cur_base,
        slot=target_slot,
        recommended_slot=advice.recommended_slot,
        verdict=final_verdict,
        reason=tactical.tactical_headline if zone_override else advice.summary_verdict,
        gains=gains,
        trade_offs=trade_offs,
        formatted_report=advice.formatted_output,
        is_weapon=False,
        tactical_advice=tactical.model_dump(),
    )


def _pob2_other(ctx: _EvalContext) -> dict[str, Any] | None:
    """Armour / jewellery slots: one PoB2 simulation against the Fubgun equipment policy."""
    pob_slot = normalize_and_validate_pob_slot(ctx.candidate.slot)
    cid = ctx.pob_session.submit_candidate(ctx.raw_text, candidate_name=ctx.name, slot=pob_slot)
    delta = ctx.pob_session.simulate_item(
        slot=pob_slot, raw_candidate=ctx.raw_text, candidate_id=cid, candidate_name=ctx.name
    )
    if delta is None:
        return None
    rec = evaluate_fubgun_equipment_policy(delta, stage=ctx.stage, use_color=False)
    tactical = ctx.tactical(delta, pob_slot)
    final_verdict = merge_verdicts(rec.verdict, tactical.verdict)
    zone_override = final_verdict == "REJECT" and "REJECT" not in str(getattr(rec, "verdict", ""))
    slot_key = ctx.slot_key(pob_slot.lower())
    cur_name, cur_base = ctx.current_info(slot_key)
    return ctx.result(
        "pob2",
        current_item_name=getattr(delta, "current_item_name", None) or cur_name,
        current_item_base_type=cur_base,
        slot=slot_key,
        verdict=final_verdict,
        reason=tactical.tactical_headline if zone_override else rec.reason,
        gains=rec.gains,
        trade_offs=rec.trade_offs,
        formatted_report=_zone_reject_report(ctx, pob_slot, pob_slot, tactical) if zone_override else rec.formatted_output,
        dps_delta=getattr(delta, "dps_delta", 0.0),
        life_delta=getattr(delta, "life_delta", 0),
        is_weapon=False,
        tactical_advice=tactical.model_dump(),
    )


def _known_delta(stat: Any) -> int:
    return int(stat.delta) if getattr(stat, "is_delta_known", False) else 0


def _evaluate_heuristic(ctx: _EvalContext) -> dict[str, Any]:
    """Local stat-projection engine; always available, used when PoB2 is absent or fails."""
    engine = EquipmentIntelligenceEngine(runtime_dir=ctx.runtime_dir)

    target_wset = None
    target_slot_param = ctx.requested_slot
    if ctx.requested_slot:
        req_clean = ctx.requested_slot.lower().strip()
        if req_clean.startswith("set2_") or req_clean.startswith("swap_"):
            target_wset = WeaponSetContext.WEAPON_SET_2
            target_slot_param = req_clean.replace("set2_", "").replace("swap_", "")
        elif req_clean in ("weapon_1_swap", "weapon 1 swap"):
            target_wset = WeaponSetContext.WEAPON_SET_2
            target_slot_param = "main_hand"
        elif req_clean in ("weapon_2_swap", "weapon 2 swap"):
            target_wset = WeaponSetContext.WEAPON_SET_2
            target_slot_param = "off_hand"
        elif ctx.is_weapon:
            target_wset = WeaponSetContext.WEAPON_SET_1

    formatted_report = evaluate_live_candidate(
        candidate_text=ctx.raw_text,
        engine=engine,
        runtime_dir=ctx.runtime_dir,
        character_id=ctx.char_id,
        stage=ctx.stage,
        target_weapon_set="set_2" if target_wset == WeaponSetContext.WEAPON_SET_2 else None,
    )
    rec = engine.evaluate_candidate(
        item_text=ctx.raw_text,
        character_id=ctx.char_id,
        stage=ctx.stage,
        target_slot=target_slot_param,
        target_weapon_set=target_wset,
    )

    proj = rec.projection
    gains: list[str] = []
    trade_offs: list[str] = []
    stat_specs = [
        (proj.life, "Life"),
        (proj.fire_res, "% Fire Res"),
        (proj.cold_res, "% Cold Res"),
        (proj.lightning_res, "% Lightning Res"),
        (proj.chaos_res, "% Chaos Res"),
        (proj.armour, "Armour"),
        (proj.evasion, "Evasion"),
        (proj.energy_shield, "Energy Shield"),
        (proj.movement_speed, "% Movement Speed"),
        (proj.strength, "Strength"),
        (proj.dexterity, "Dexterity"),
        (proj.intelligence, "Intelligence"),
    ]
    for sp, label in stat_specs:
        if getattr(sp, "is_delta_known", False) and sp.delta != 0:
            val = int(sp.delta)
            if val > 0:
                gains.append(f"+{val} {label}" if not label.startswith("%") else f"+{val}{label}")
            elif val < 0:
                trade_offs.append(f"{val} {label}" if not label.startswith("%") else f"{val}{label}")

    slot_value = ctx.slot_key("equipment")
    cur_name, cur_base = ctx.current_info(slot_value)
    out = ctx.result(
        "heuristic",
        current_item_name=cur_name,
        current_item_base_type=cur_base,
        slot=slot_value,
        verdict=rec.verdict.value if hasattr(rec.verdict, "value") else str(rec.verdict),
        reason=getattr(rec, "verdict_reason", None) or getattr(rec, "reason", "Evaluated by Equipment Intelligence Engine"),
        gains=gains,
        trade_offs=trade_offs,
        formatted_report=formatted_report,
        is_weapon=ctx.is_weapon,
    )

    try:
        delta_fb = PobEquipmentDelta(
            slot=ctx.candidate.slot.value if ctx.candidate.slot else "equipment",
            candidate_id=0,
            candidate_name=ctx.name,
            current_item_name=cur_name,
            life_delta=_known_delta(proj.life),
            fire_res_delta=_known_delta(proj.fire_res),
            cold_res_delta=_known_delta(proj.cold_res),
            lightning_res_delta=_known_delta(proj.lightning_res),
            chaos_res_delta=_known_delta(proj.chaos_res),
            armour_delta=_known_delta(proj.armour),
            evasion_delta=_known_delta(proj.evasion),
            es_delta=_known_delta(proj.energy_shield),
            ehp_delta=float(proj.life.delta) if getattr(proj.life, "is_delta_known", False) else 0.0,
            strength_delta=_known_delta(proj.strength),
            dexterity_delta=_known_delta(proj.dexterity),
            intelligence_delta=_known_delta(proj.intelligence),
        )
        tactical = ctx.tactical(delta_fb, slot_value)
    except Exception:
        return out

    out["tactical_advice"] = tactical.model_dump()
    tac_v = getattr(tactical.verdict, "value", str(tactical.verdict))
    if tac_v == "REJECT":
        out["verdict"] = "REJECT"
        if "REJECT" not in str(getattr(rec, "verdict", "")):
            out["reason"] = tactical.tactical_headline
            out["formatted_report"] = _zone_reject_report(ctx, slot_value, slot_value.capitalize(), tactical)
    elif tac_v == "EQUIP_NOW":
        out["verdict"] = "EQUIP_NOW"
        out["reason"] = tactical.tactical_headline
    elif tac_v == "CONDITIONAL_UPGRADE" and "INSUFFICIENT_DATA" in str(getattr(rec, "verdict", "")):
        out["verdict"] = "CONDITIONAL_UPGRADE"
        out["reason"] = tactical.tactical_headline
    return out


def _evaluate_item_payload_impl(
    payload: dict[str, Any],
    runtime_dir: Path,
    pob_session: Any | None = None,
) -> dict[str, Any]:
    """Execute real PoB2 and Fubgun equipment policy evaluation on submitted item text."""
    raw_text = payload.get("raw_text", "").strip()
    if not raw_text:
        return {"error": "Item raw text is empty."}

    ctx = _build_eval_context(payload, raw_text, runtime_dir, pob_session)
    if isinstance(ctx, dict):
        return ctx

    if ctx.is_weapon and ctx.guide == "navira_varashta" and "bow" in (ctx.candidate.base_type or "").lower():
        reason = (
            "Crossbow / Bow tidak cocok untuk Sorceress Navira's Fracturing Varashta! "
            "Gunakan Staff atau Wand/Focus yang memberikan Spell / Lightning Damage."
        )
        return _incompatible_weapon(
            ctx,
            "heuristic",
            reason,
            headline=f"Senjata ini ({ctx.name}) tidak kompatibel dengan build aktif Sorceress!",
            action=f"Jangan pasang! {reason} Tetap gunakan senjata yang sesuai dengan skill Sorceress.",
            formatted=f"🛑 REJECT / SENJATA INKOMPATIBEL\n\n{ctx.name}\n\nReason:\n{reason}",
        )

    # 1. PoB2 live simulation if session provided and available
    if pob_session is not None and getattr(pob_session, "is_available", False):
        if ctx.is_weapon:
            branch = _pob2_weapon
        elif ctx.candidate.slot in (SlotType.RING_1, SlotType.RING_2) or "ring" in ctx.candidate.base_type.lower():
            branch = _pob2_ring
        else:
            branch = _pob2_other
        try:
            res = branch(ctx)
        except Exception:
            logger.exception("PoB2 evaluation failed for %r; falling back to heuristic engine", ctx.name)
        else:
            if res is not None:
                return res
            logger.warning("PoB2 returned no delta for %r; falling back to heuristic engine", ctx.name)

    # 2. Standard Engine live candidate evaluation (always available locally)
    try:
        return _evaluate_heuristic(ctx)
    except Exception as exc:
        return {"error": f"Evaluation error: {exc}"}


def evaluate_item_payload(
    payload: dict[str, Any],
    runtime_dir: Path,
    pob_session: Any | None = None,
) -> dict[str, Any]:
    """Execute real PoB2 and Fubgun equipment policy evaluation on submitted item text."""
    res = _evaluate_item_payload_impl(payload, runtime_dir=runtime_dir, pob_session=pob_session)
    return _stamp_evaluated(res)


_LAST_SEEN_CLIPBOARD = ""

def check_auto_clipboard(
    runtime_dir: Path,
    char_id: str,
    stage_str: str,
    pob_session: Any | None = None,
    guide: str | None = None,
    zone: str | None = None,
    pob_session_resolver: Any | None = None,
) -> dict[str, Any]:
    """Poll OS clipboard automatically and evaluate if a new PoE2 item is detected."""
    global _LAST_SEEN_CLIPBOARD
    current_text = get_clipboard_text().strip()

    current_key = f"{current_text}::{char_id}::{stage_str}::{guide}::{zone}"
    if not current_text or _LAST_SEEN_CLIPBOARD in (current_text, current_key):
        return {"has_new_item": False}

    # Verify if it looks like a PoE item
    if "Rarity:" not in current_text and "Item Class:" not in current_text:
        return {"has_new_item": False}

    char_id = resolve_char_id(char_id, runtime_dir)

    _LAST_SEEN_CLIPBOARD = current_key

    if pob_session is None and callable(pob_session_resolver):
        try:
            pob_session = pob_session_resolver()
        except Exception:
            pob_session = None

    result = evaluate_item_payload(
        {"raw_text": current_text, "character_id": char_id, "stage": stage_str, "guide": guide, "zone": zone},
        runtime_dir=runtime_dir,
        pob_session=pob_session,
    )
    result["has_new_item"] = True
    result["raw_text"] = current_text
    return result


def update_loadout_item_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from companion.equipment.loadout_cli import character_runtime_lock
    with character_runtime_lock(payload.get("character_id", "BOMSHAK")):
        return _update_loadout_item_payload_locked(payload, runtime_dir)


def _update_loadout_item_payload_locked(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    """Equip or update an item in character loadout from web UI."""
    raw_text = payload.get("raw_text", "").strip()
    if not raw_text:
        return {"error": "Item text cannot be empty."}

    char_id = payload.get("character_id", "BOMSHAK")
    slot_name = payload.get("slot")
    weapon_set_name = payload.get("weapon_set")

    try:
        candidate = parse_item_text(raw_text)
    except Exception as exc:
        return {"error": f"Failed to parse item: {exc}"}

    # Resolve specific slot name
    target_slot = slot_name
    if not target_slot:
        if candidate.slot:
            target_slot = candidate.slot.value
        elif "crossbow" in candidate.base_type.lower() or "staff" in candidate.base_type.lower() or "bow" in candidate.base_type.lower():
            target_slot = "main_hand"
        elif "ring" in candidate.base_type.lower():
            target_slot = "ring1"
        else:
            return {"error": "Could not determine equipment slot for item."}

    # Map generic/prefixed names sent from UI
    norm_slot = target_slot.lower().strip()
    if norm_slot.startswith("set2_"):
        target_slot = norm_slot[5:]
        weapon_set_name = weapon_set_name or "weapon_set_2"
    elif norm_slot.startswith("swap_"):
        target_slot = norm_slot[5:]
        weapon_set_name = weapon_set_name or "weapon_set_2"
    elif norm_slot in ("ring", "ring_1", "ring1"):
        target_slot = "ring1"
    elif norm_slot in ("ring_2", "ring2"):
        target_slot = "ring2"
    elif norm_slot == "weapon":
        target_slot = "main_hand"

    from companion.equipment.loadout_cli import run_loadout_set_item
    try:
        updated_loadout = run_loadout_set_item(
            runtime_dir=runtime_dir,
            character_id=char_id,
            slot_name=target_slot,
            item_text=raw_text,
            weapon_set_name=weapon_set_name,
        )
        return {
            "success": True,
            "message": f"Berhasil memasang {candidate.name or candidate.base_type} ke slot {target_slot.upper()}.",
            "slot": target_slot,
            "item_name": candidate.name or candidate.base_type,
            "revision": updated_loadout.revision,
            "character_id": char_id,
        }
    except Exception as exc:
        return {"error": f"Gagal update loadout: {exc}"}


def import_character_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from companion.equipment.loadout_cli import character_runtime_lock
    with character_runtime_lock(payload.get("character_id", "BOMSHAK")):
        return _import_character_payload_locked(payload, runtime_dir)


def _import_character_payload_locked(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    """Import full character equipment JSON (from GGG get-items or export)."""
    char_id = payload.get("character_id", "BOMSHAK")
    raw_payload = payload.get("character_data") or payload
    if not isinstance(raw_payload, dict):
        return {"error": "Invalid character JSON data."}
    overwrite = payload.get("overwrite", True)

    from companion.equipment.api_adapter import GGGCharacterAPIAdapter
    from companion.equipment.loadout_cli import load_loadout, save_loadout
    from companion.equipment.baseline import BaselineSource
    from companion.equipment.baseline_cli import load_baseline, save_baseline

    current_loadout = load_loadout(runtime_dir, char_id)
    current_baseline = load_baseline(runtime_dir, char_id)
    loadout, baseline, warnings = GGGCharacterAPIAdapter.parse_character_payload(
        raw_payload=raw_payload,
        character_id=char_id,
        current_loadout=current_loadout,
        overwrite_conflicts=overwrite,
    )
    if loadout is None:
        return {"error": "; ".join(warnings) if warnings else "Gagal membaca item karakter dari JSON."}

    save_loadout(runtime_dir, loadout)
    if baseline is not None:
        if current_baseline is not None:
            same_gear = (
                current_loadout is not None and current_loadout.is_finalized
                and current_loadout.compute_fingerprint() == loadout.compute_fingerprint()
            )
            if same_gear:
                # Same gear: keep the previous anchor so the following apply does not stale every fact.
                baseline.anchored_loadout_fingerprint = current_baseline.anchored_loadout_fingerprint
            for attr_name in (
                "life", "armour", "evasion", "energy_shield", "mana", "spirit", "deflection",
                "raw_fire_res", "effective_fire_res", "max_fire_res", "fire_overcap_buffer",
                "raw_cold_res", "effective_cold_res", "max_cold_res", "cold_overcap_buffer",
                "raw_lightning_res", "effective_lightning_res", "max_lightning_res", "lightning_overcap_buffer",
                "raw_chaos_res", "effective_chaos_res", "max_chaos_res", "chaos_overcap_buffer",
                "strength", "dexterity", "intelligence", "movement_speed",
            ):
                old = getattr(current_baseline, attr_name, None)
                new = getattr(baseline, attr_name, None)
                if old is not None and getattr(old, "source", None) == BaselineSource.MANUAL_USER_INPUT:
                    setattr(baseline, attr_name, old if same_gear else old.mark_stale())
                elif new is not None and getattr(new, "is_known", False):
                    continue
                elif old is not None and getattr(old, "value", None) is not None:
                    setattr(baseline, attr_name, old.mark_stale())
        save_baseline(runtime_dir, baseline)

    # Persist or update CharacterState with name, class, level
    try:
        from companion.state.schema import CharacterState, ProvenancedField
        from companion.state.store import CharacterStateStore

        char_info = raw_payload.get("character") or {}
        char_level = char_info.get("level") or raw_payload.get("level")
        char_class = char_info.get("class") or raw_payload.get("class") or "Mercenary"
        char_name = char_info.get("name") or char_id

        store = CharacterStateStore(runtime_dir=runtime_dir)
        try:
            existing_state = store.load_character(char_id)
        except Exception:
            existing_state = None

        if existing_state:
            existing_state.character_name = char_name
            existing_state.character_class = char_class
            if char_level is not None:
                existing_state.level = ProvenancedField[int].create(int(char_level), source="OFFICIAL_API_POLL")
            store.save_character(existing_state)
        else:
            lvl_val = int(char_level) if char_level is not None else 1
            new_state = CharacterState(
                character_id=char_id,
                character_name=char_name,
                character_class=char_class,
                level=ProvenancedField[int].create(lvl_val, source="OFFICIAL_API_POLL"),
            )
            store.save_character(new_state)
    except Exception:
        pass

    return {
        "success": True,
        "character_id": char_id,
        "imported_slots": len(loadout.known_slots),
        "slots": [s.value if hasattr(s, "value") else str(s) for s in loadout.known_slots],
        "message": f"Berhasil mengimpor {len(loadout.known_slots)} slot perlengkapan untuk {char_id}!",
        "warnings": warnings,
    }


def update_character_stats_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from companion.equipment.loadout_cli import character_runtime_lock
    with character_runtime_lock(payload.get("character_id") or "BOMSHAK"):
        return _update_character_stats_payload_locked(payload, runtime_dir)


def _update_character_stats_payload_locked(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    """Update CharacterState and CharacterStatBaseline with live character stats from in-game / UI."""
    char_id = payload.get("character_id") or "BOMSHAK"

    from companion.state.schema import CharacterState, ProvenancedField
    from companion.state.store import CharacterStateStore
    from companion.equipment.fubgun_priorities import infer_stage_from_level

    store = CharacterStateStore(runtime_dir=runtime_dir)
    try:
        state = store.load_character(char_id)
    except Exception:
        state = CharacterState(
            character_id=char_id,
            character_name=payload.get("character_name") or char_id,
            character_class=payload.get("character_class") or "Mercenary",
            ascendancy=payload.get("ascendancy") or "Gemling Legionnaire",
        )

    if payload.get("character_name"):
        state.character_name = payload["character_name"]
    if payload.get("character_class"):
        state.character_class = payload["character_class"]
    if payload.get("ascendancy"):
        state.ascendancy = payload["ascendancy"]

    if payload.get("level") is not None:
        lvl_val = int(payload["level"])
        state.level = ProvenancedField[int].create(lvl_val, source="USER_IN_GAME_SYNC")
        stage_enum = infer_stage_from_level(lvl_val)
        display_map = {
            "LEVELING_1_14": "lvl 1-14",
            "LEVELING_15_32": "lvl 15-32",
            "LEVELING_33_51": "lvl 33-51",
            "SWAP_52": "lvl 52 Swap",
            "LEVELING_53_68": "lvl 53-68",
            "LEVEL_85": "lvl 85",
            "ENDGAME": "Endgame",
        }
        state.build_progression["active_stage"] = display_map.get(getattr(stage_enum, "value", str(stage_enum)), "lvl 33-51")


    # Attributes
    for attr in ("strength", "dexterity", "intelligence"):
        if payload.get(attr) is not None:
            val = int(payload[attr])
            state.attributes[attr] = ProvenancedField[int].create(val, source="USER_IN_GAME_SYNC")

    # Resources (mana, spirit)
    for res_key in ("mana", "spirit"):
        if payload.get(res_key) is not None:
            val = int(payload[res_key])
            state.resources[res_key] = ProvenancedField[int].create(val, source="USER_IN_GAME_SYNC")

    # Resistances
    for res in ("fire", "cold", "lightning", "chaos"):
        val = payload.get(f"{res}_res") if payload.get(f"{res}_res") is not None else payload.get(res)
        if val is not None:
            state.resistances[res] = ProvenancedField[int].create(int(val), source="USER_IN_GAME_SYNC")

    store.save_character(state)

    # 2. Update or create CharacterStatBaseline
    from companion.equipment.baseline import CharacterStatBaseline, CharacterFact, BaselineSource
    from companion.equipment.baseline_cli import load_baseline, save_baseline

    baseline = load_baseline(runtime_dir, char_id)
    if baseline is None:
        baseline = CharacterStatBaseline.create_empty(character_id=char_id, anchored_loadout_revision=1)

    # Update defensive stats
    if payload.get("life") is not None:
        baseline.life = CharacterFact[int].create(int(payload["life"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("armour") is not None:
        baseline.armour = CharacterFact[int].create(int(payload["armour"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("evasion") is not None:
        baseline.evasion = CharacterFact[int].create(int(payload["evasion"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("energy_shield") is not None:
        baseline.energy_shield = CharacterFact[int].create(int(payload["energy_shield"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("mana") is not None:
        baseline.mana = CharacterFact[int].create(int(payload["mana"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("spirit") is not None:
        baseline.spirit = CharacterFact[int].create(int(payload["spirit"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("deflection") is not None:
        baseline.deflection = CharacterFact[int].create(int(payload["deflection"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("movement_speed") is not None:
        baseline.movement_speed = CharacterFact[int].create(int(payload["movement_speed"]), source=BaselineSource.MANUAL_USER_INPUT)

    # Attributes on baseline
    if payload.get("strength") is not None:
        baseline.strength = CharacterFact[int].create(int(payload["strength"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("dexterity") is not None:
        baseline.dexterity = CharacterFact[int].create(int(payload["dexterity"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("intelligence") is not None:
        baseline.intelligence = CharacterFact[int].create(int(payload["intelligence"]), source=BaselineSource.MANUAL_USER_INPUT)

    # Resistances on baseline
    for res in ("fire", "cold", "lightning", "chaos"):
        val = payload.get(f"{res}_res") if payload.get(f"{res}_res") is not None else payload.get(res)
        if val is not None:
            int_val = int(val)
            setattr(baseline, f"raw_{res}_res", CharacterFact[int].create(int_val, source=BaselineSource.MANUAL_USER_INPUT))
            setattr(baseline, f"effective_{res}_res", CharacterFact[int].create(int_val, source=BaselineSource.MANUAL_USER_INPUT))
            setattr(baseline, f"max_{res}_res", CharacterFact[int].create(75, source=BaselineSource.MANUAL_USER_INPUT))

    save_baseline(runtime_dir, baseline)

    return {
        "success": True,
        "character_id": char_id,
        "message": f"Stat karakter {char_id} berhasil diperbarui secara live!",
    }



_OAUTH_REQUIRED_MSG = "Login PoE belum aktif/kedaluwarsa. Jalankan login via PoB2 MCP (poe_login_start)."
_API_CHARS_TTL = 300.0
_API_CHARS_CACHE: dict[str, Any] = {}


def _list_api_characters(now: float | None = None) -> list[dict[str, Any]]:
    """Characters from the official GGG API via PoB2 MCP, cached for 300 s. [] on any failure."""
    now = time.monotonic() if now is None else now
    cached = _API_CHARS_CACHE.get("entry")
    if cached and now - cached[0] < _API_CHARS_TTL:
        return list(cached[1])
    modules = load_pob_mcp_modules()
    if modules is None:
        logger.warning("PoB2 MCP not found; cannot list GGG characters")
        return []
    poe_api, poe_oauth = modules
    try:
        if not poe_oauth.get_valid_token():
            logger.warning("No valid PoE OAuth token; cannot list GGG characters")
            return []
        chars = [
            {
                "name": c["name"],
                "level": c.get("level", 1),
                "class": c.get("class", "Unknown"),
                "league": c.get("league", "Standard"),
            }
            for c in poe_api.list_characters()
            if c.get("name")
        ]
    except Exception as exc:
        logger.warning("GGG list_characters failed: %s", exc)
        return []
    _API_CHARS_CACHE["entry"] = (now, chars)
    return list(chars)


def fetch_public_profile(account_name: str, character_id: str, runtime_dir: Path, overwrite: bool = True) -> dict[str, Any]:
    """Import a character through the official GGG API (PoB2 MCP). Returns an error dict on failure."""
    character_id = character_id.strip()
    modules = load_pob_mcp_modules()
    if modules is None:
        return {"error": "POB2_MCP_NOT_FOUND", "message": "Folder path-of-building-2-mcp tidak ditemukan. Set POB2_MCP_PATH."}
    poe_api, poe_oauth = modules
    try:
        token = poe_oauth.get_valid_token()
    except Exception as exc:
        logger.info("get_valid_token raised: %s", exc)
        token = None
    if not token:
        return {"error": "OAUTH_REQUIRED", "message": _OAUTH_REQUIRED_MSG}
    try:
        raw_data = poe_api.fetch_character_raw(character_id)
        parsed_data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
    except Exception as exc:
        logger.warning("GGG fetch_character_raw failed for %s: %s", character_id, exc)
        return {"error": "GGG_API_ERROR", "message": str(exc)}
    res = import_character_payload({"character_id": character_id, "character_data": parsed_data, "overwrite": overwrite}, runtime_dir)
    if res.get("success"):
        res["message"] = f"Berhasil menarik {res.get('imported_slots')} slot perlengkapan resmi untuk {character_id} dari GGG PoE2 API!"
    return res


def get_dashboard_status(
    runtime_dir: Path,
    char_id: str | None = None,
    pob_session: Any | None = None,
) -> dict[str, Any]:
    """Gather live runtime status, active character, current objective, baseline, loadout, and engine health."""
    if not char_id:
        active_file = runtime_dir / "active_character.json"
        if active_file.is_file():
            try:
                active_data = json.loads(active_file.read_text(encoding="utf-8"))
                if active_data.get("active_character_id"):
                    char_id = active_data["active_character_id"]
            except Exception:
                pass

    status_data: dict[str, Any] = {"game_process_running": False}
    char_data: dict[str, Any] = {}
    obj_data: dict[str, Any] = {}
    loadout_data: dict[str, Any] = {}
    baseline_data: dict[str, Any] = {}

    status_file = runtime_dir / "runtime_status.json"
    if status_file.is_file():
        try:
            status_data = json.loads(status_file.read_text(encoding="utf-8"))
            if not char_id and status_data.get("active_character_id"):
                char_id = status_data["active_character_id"]
        except Exception:
            pass

    if not char_id:
        char_id = "BOMSHAK"

    status_data["active_character_id"] = char_id

    # Gather PoB2 engine health status
    engine_status: dict[str, Any] = {
        "available": False,
        "healthy": False,
        "unhealthy_reason": None,
    }
    target_pob = pob_session
    if target_pob is None and char_id:
        try:
            from companion.dashboard_server import _GLOBAL_POB_SESSIONS
            target_pob = _GLOBAL_POB_SESSIONS.get(char_id)
        except Exception:
            pass

    if target_pob is not None:
        engine_status["available"] = bool(getattr(target_pob, "is_available", False))
        engine_status["healthy"] = bool(getattr(target_pob, "is_healthy", False))
        engine_status["unhealthy_reason"] = getattr(target_pob, "unhealthy_reason", None)

    status_data["engine_healthy"] = engine_status["healthy"]

    char_file = runtime_dir / "characters" / f"{char_id}.json"
    if char_file.is_file():
        try:
            char_data = json.loads(char_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    obj_file = runtime_dir / "CURRENT_OBJECTIVE.json"
    if obj_file.is_file():
        try:
            obj_data = json.loads(obj_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    from companion.equipment.loadout_cli import load_loadout
    loadout = load_loadout(runtime_dir, char_id)
    if loadout:
        loadout_data = loadout.model_dump()

    from companion.equipment.baseline_cli import load_baseline
    baseline = load_baseline(runtime_dir, char_id)
    if baseline:
        baseline_data = baseline.model_dump()

    return {
        "status": status_data,
        "character": char_data,
        "objective": obj_data,
        "loadout": loadout_data,
        "baseline": baseline_data,
        "active_character_id": char_id,
        "engine_status": engine_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_account_characters(
    account_name: str = "mikaelzo#5674",
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    """Discover available characters for an account from the GGG API and local runtime files."""
    if runtime_dir is None:
        runtime_dir = Path(__file__).resolve().parent.parent / "runtime"

    characters: list[dict[str, Any]] = list(_list_api_characters())
    source = "api" if characters else "local"
    seen_names = {c["name"] for c in characters}

    char_dir = runtime_dir / "characters"
    if char_dir.is_dir():
        for f in char_dir.glob("*.json"):
            try:
                c_data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                logger.warning("Skipping unreadable character file %s: %s", f, exc)
                continue
            if not isinstance(c_data, dict):
                logger.warning("Skipping non-object character file %s", f)
                continue
            c_name = c_data.get("character_name") or c_data.get("character_id") or f.stem
            if c_name in seen_names:
                continue  # API entry wins
            seen_names.add(c_name)
            lvl_obj = c_data.get("level", 1)
            lvl_val = lvl_obj.get("value", 1) if isinstance(lvl_obj, dict) else (lvl_obj if isinstance(lvl_obj, int) else 1)
            characters.append({
                "name": c_name,
                "level": lvl_val,
                "class": c_data.get("character_class", "Unknown"),
                "league": "Local",
            })

    active_char_id = "BOMSHAK"
    active_file = runtime_dir / "active_character.json"
    if active_file.is_file():
        try:
            a_data = json.loads(active_file.read_text(encoding="utf-8"))
            if a_data.get("active_character_id"):
                active_char_id = a_data["active_character_id"]
        except Exception:
            pass

    return {
        "account": account_name,
        "characters": characters,
        "active_character_id": active_char_id,
        "source": source,
    }


def select_character_payload(
    payload: dict[str, Any],
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    """Switch the active character across the companion suite."""
    char_id = payload.get("character_id", "").strip()
    if not char_id:
        return {"error": "character_id is required."}

    if runtime_dir is None:
        runtime_dir = Path("runtime")

    account_name = payload.get("account_name", "mikaelzo#5674")

    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_dir = runtime_dir / "characters"
    char_dir.mkdir(parents=True, exist_ok=True)
    char_file = char_dir / f"{char_id}.json"
    active_file = runtime_dir / "active_character.json"
    active_data = {
        "active_character_id": char_id,
        "file_path": str(char_file.resolve()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    active_file.write_text(json.dumps(active_data, indent=2), encoding="utf-8")

    status_file = runtime_dir / "runtime_status.json"
    if status_file.is_file():
        try:
            s_data = json.loads(status_file.read_text(encoding="utf-8"))
            s_data["active_character_id"] = char_id
            status_file.write_text(json.dumps(s_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    if not char_file.is_file():
        acc_info = get_account_characters(account_name=account_name, runtime_dir=runtime_dir)
        found_meta = next((c for c in acc_info.get("characters", []) if c["name"].lower() == char_id.lower()), None)
        c_class = found_meta["class"] if found_meta else "Mercenary"
        c_level = found_meta["level"] if found_meta else 1

        try:
            from companion.state.schema import CharacterState, ProvenancedField
            from companion.state.store import CharacterStateStore
            store = CharacterStateStore(runtime_dir=runtime_dir)
            new_state = CharacterState(
                character_id=char_id,
                character_name=char_id,
                character_class=c_class,
                level=ProvenancedField[int].create(int(c_level), source="OFFICIAL_API_POLL"),
            )
            store.save_character(new_state)
        except Exception:
            pass

        try:
            fetch_public_profile(account_name=account_name, character_id=char_id, runtime_dir=runtime_dir)
        except Exception:
            pass

    try:
        from companion.dashboard_server import invalidate_pob_session
        invalidate_pob_session(char_id)
    except Exception:
        pass

    return {
        "success": True,
        "active_character_id": char_id,
        "message": f"Karakter aktif berhasil diubah menjadi {char_id}!",
    }


def get_available_guides(runtime_dir: Path, character_id: str | None = None) -> dict[str, Any]:
    """List imported guides and the guide/stage assigned to ``character_id``."""
    from companion.builds.store import get_assignment, list_guides

    guide, override = get_assignment(runtime_dir, character_id) if character_id else (None, None)
    return {
        "guides": [
            {
                "slug": g.slug,
                "name": g.name,
                "source_url": g.source_url,
                "has_pob": g.has_pob,
                "stages": [
                    {"id": s.id, "title": s.title, "min_level": s.min_level,
                     "max_level": s.max_level, "auto": s.auto}
                    for s in g.stages
                ],
                "breaker_rules": [r.model_dump() for r in g.breaker_rules],
            }
            for g in list_guides(runtime_dir)
        ],
        "active": {"guide": guide, "stage_override": override},
    }


def import_guide_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    """Import a guide from bookmarklet JSON, a pobb.in URL or a PoB2 share code."""
    from datetime import date

    from companion.builds import pob_code
    from companion.builds.mobalytics import parse_mobalytics_guide
    from companion.builds.store import load_guide, save_guide

    text = str(payload.get("text") or "").strip()
    if not text:
        return {"error": "Teks guide kosong."}
    warnings: list[str] = []
    try:
        if text.startswith("{"):
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("JSON guide tidak valid atau terpotong.") from exc
            profile, code, warnings = parse_mobalytics_guide(data)
            xml = None
            if code:
                try:
                    xml = pob_code.decode_share_code(code)
                except ValueError as exc:
                    warnings.append(f"Kode PoB2 dilewati: {exc}")
        else:
            if text.startswith("https://pobb.in/"):
                try:
                    code = pob_code.fetch_pobb_code(text)
                except OSError as exc:
                    raise ValueError(f"Gagal mengambil dari pobb.in: {exc}") from exc
            else:
                code = text
            xml = pob_code.decode_share_code(code)
            profile = pob_code.parse_pob_xml(xml, f"PoB Guide {date.today().isoformat()}")
        replaced = load_guide(runtime_dir, profile.slug) is not None
        saved = save_guide(runtime_dir, profile, pob_xml=xml)
        if replaced:
            warnings.append(
                f"Guide '{saved.name}' yang sudah ada ditimpa (aturan breaker dipertahankan)")
    except ValueError as exc:
        return {"error": str(exc)}
    return {"success": True, "slug": saved.slug, "name": saved.name,
            "stages": len(saved.stages), "warnings": warnings}


def delete_guide_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from companion.builds.store import delete_guide

    if not delete_guide(runtime_dir, str(payload.get("slug") or "")):
        return {"error": "Guide tidak ditemukan."}
    return {"success": True}


def update_guide_rules_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from pydantic import ValidationError

    from companion.builds.guide import BreakerRule
    from companion.builds.store import set_breaker_rules

    try:
        rules = [BreakerRule.model_validate(r) for r in payload.get("rules") or []]
    except ValidationError as exc:
        err = exc.errors()[0]
        if err["loc"] and err["loc"][-1] == "pattern":
            return {"error": f"Pola regex tidak valid: {err['msg'].removeprefix('Value error, ')}"}
        return {"error": f"Aturan tidak valid: {err['msg']}"}
    try:
        set_breaker_rules(runtime_dir, str(payload.get("slug") or ""), rules)
    except (KeyError, ValueError):
        return {"error": "Guide tidak ditemukan."}
    return {"success": True}


def set_character_guide_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from companion.builds.store import load_guide, set_assignment

    char_id, guide = payload.get("character_id"), payload.get("guide")
    override = payload.get("stage_override")
    if not char_id:
        return {"error": "character_id wajib diisi."}
    if guide is not None:
        profile = load_guide(runtime_dir, str(guide))
        if profile is None:
            return {"error": "Guide tidak ditemukan."}
        ids = {s.id for s in profile.stages}
        if override is not None and (not isinstance(override, str) or override not in ids):
            return {"error": "Tahap guide tidak dikenal."}
    elif override is not None:
        return {"error": "Tahap tidak bisa diatur tanpa guide."}
    set_assignment(runtime_dir, str(char_id), guide, override)
    return {"success": True}


