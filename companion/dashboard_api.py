"""Web API endpoints for PoE2 Companion Dashboard local server."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from companion.equipment.clipboard import get_clipboard_text
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.fubgun_priorities import evaluate_fubgun_weapon_policy, evaluate_fubgun_equipment_policy
from companion.equipment.tactical_advisor import generate_tactical_advice, merge_verdicts
from companion.equipment.live_watcher import evaluate_live_candidate
from companion.equipment.parser import parse_item_text
from companion.equipment.pob2_equipment_advisor import Pob2EquipmentSession, resolve_pob2_backend_path
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotType
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


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
                if isinstance(eq, dict) and "raw" in eq and eq["raw"]:
                    return eq["raw"]
            except Exception:
                pass

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


def _stamp_evaluated(res: dict[str, Any]) -> dict[str, Any]:
    if res.get("success"):
        res.setdefault("evaluated_at", datetime.now(timezone.utc).isoformat())
    return res


def _evaluate_item_payload_impl(
    payload: dict[str, Any],
    runtime_dir: Path,
    pob_session: Any | None = None,
) -> dict[str, Any]:
    """Execute real PoB2 and Fubgun equipment policy evaluation on submitted item text."""
    raw_text = payload.get("raw_text", "").strip()
    if not raw_text:
        return {"error": "Item raw text is empty."}

    char_id = payload.get("character_id", "BOMSHAK")
    chars_dir = runtime_dir / "characters"
    if chars_dir.is_dir():
        for f in chars_dir.glob("*.json"):
            if f.stem.lower() == str(char_id).lower():
                char_id = f.stem
                break
    stage_str = payload.get("stage", "lvl 1-14")
    requested_slot = payload.get("slot")

    # Map stage
    stage_map = {
        "lvl 1-14": BuildProgressionStage.LEVELING_1_14,
        "lvl 15-32": BuildProgressionStage.LEVELING_15_32,
        "lvl 33-51": BuildProgressionStage.LEVELING_33_51,
        "lvl 52 swap": BuildProgressionStage.SWAP_52,
        "lvl 53-68": BuildProgressionStage.LEVELING_53_68,
        "lvl 85": BuildProgressionStage.LEVEL_85,
        "endgame": BuildProgressionStage.ENDGAME,
        "mageblood": BuildProgressionStage.MAGEBLOOD,
        "dot cap": BuildProgressionStage.DOT_CAP,
    }

    from companion.equipment.fubgun_priorities import infer_stage_from_level
    char_level = getattr(pob_session, "level", None) if pob_session is not None else None
    zone_id = payload.get("zone")
    char_class = None
    char_stats_context: dict[str, Any] = {}
    try:
        char_file = runtime_dir / "characters" / f"{char_id}.json"
        if char_file.is_file():
            c_data = json.loads(char_file.read_text(encoding="utf-8"))
            char_class = c_data.get("character_class")
            char_stats_context.update(c_data)
            if not char_level:
                lvl = c_data.get("level")
                if isinstance(lvl, dict):
                    char_level = lvl.get("value")
                elif isinstance(lvl, int):
                    char_level = lvl
            if not zone_id:
                cz = c_data.get("current_zone")
                if isinstance(cz, dict):
                    zone_id = cz.get("value")
                elif isinstance(cz, str):
                    zone_id = cz
    except Exception:
        pass

    try:
        from companion.equipment.baseline_cli import load_baseline
        b_data = load_baseline(runtime_dir, char_id)
        if b_data:
            char_stats_context.update(b_data.model_dump())
    except Exception:
        pass

    guide = payload.get("guide")
    if not guide:
        if char_class and "sorceress" in char_class.lower():
            guide = "navira_varashta"
        elif char_class and "mercenary" not in char_class.lower():
            guide = "generic_pob2"
        else:
            guide = "fubgun_flameblast"
    else:
        guide = guide.lower().strip()

    from companion.equipment.zone_threats import get_zone_threat_profile
    zone_profile = get_zone_threat_profile(zone_id, character_level=char_level)

    if (stage_str.lower() in ("lvl 1-14", "default", "auto", "")) and char_level and char_level >= 15:
        stage = infer_stage_from_level(char_level)
    else:
        stage = stage_map.get(stage_str.lower(), BuildProgressionStage.LEVELING_1_14)

    def _get_current_raw(slot_name: str) -> str:
        return get_current_raw(runtime_dir, char_id, slot_name, pob_session)

    def _get_current_info(slot_name: str) -> tuple[str, str]:
        return get_current_item_info(runtime_dir, char_id, slot_name, pob_session)

    try:
        candidate = parse_item_text(raw_text)
    except Exception as exc:
        return {"error": f"Failed to parse item: {exc}"}

    is_weapon = (
        candidate.slot in (SlotType.MAIN_HAND, SlotType.OFF_HAND)
        or "Crossbow" in candidate.base_type
        or "Staff" in candidate.base_type
        or "Bow" in candidate.base_type
        or "Wand" in candidate.base_type
        or "Sceptre" in candidate.base_type
    )

    if is_weapon and guide == "navira_varashta":
        cand_base = (candidate.base_type or "").lower()
        if "crossbow" in cand_base or "bow" in cand_base:
            from companion.equipment.recommendation import Verdict
            from companion.equipment.tactical_advisor import TacticalAdvice
            reason = "Crossbow / Bow tidak cocok untuk Sorceress Navira's Fracturing Varashta! Gunakan Staff atau Wand/Focus yang memberikan Spell / Lightning Damage."
            tactical = TacticalAdvice(
                verdict=Verdict.REJECT,
                verdict_badge="🛑 SENJATA INKOMPATIBEL",
                tactical_headline=f"Senjata ini ({candidate.name or candidate.base_type}) tidak kompatibel dengan build aktif Sorceress!",
                zone_name=zone_profile.friendly_name,
                zone_threat_warning=zone_profile.survival_notes,
                actionable_recommendation=f"Jangan pasang! {reason} Tetap gunakan senjata yang sesuai dengan skill Sorceress.",
                trade_off_bullets=[reason],
            )
            return {
                "success": True,
                "item_name": candidate.name or candidate.base_type,
                "base_type": candidate.base_type,
                "slot": requested_slot or (candidate.slot.value if candidate.slot else "main_hand"),
                "verdict": Verdict.REJECT.value,
                "reason": reason,
                "gains": [],
                "trade_offs": [reason],
                "formatted_report": f"🛑 REJECT / SENJATA INKOMPATIBEL\n\n{candidate.name or candidate.base_type}\n\nReason:\n{reason}",
                "dps_delta": 0.0,
                "life_delta": 0,
                "is_weapon": True,
                "tactical_advice": tactical.model_dump(),
            }

    # 1. PoB2 live simulation if session provided and available
    if pob_session is not None and getattr(pob_session, "is_available", False):
        try:
            if is_weapon:
                from companion.equipment.recommendation import Verdict
                from companion.equipment.tactical_advisor import TacticalAdvice

                if requested_slot in ("set2_main_hand", "Weapon 1 Swap"):
                    pob_slot = "Weapon 1 Swap"
                elif requested_slot in ("set2_off_hand", "Weapon 2 Swap"):
                    pob_slot = "Weapon 2 Swap"
                elif requested_slot in ("off_hand", "Weapon 2") or candidate.slot == SlotType.OFF_HAND:
                    pob_slot = "Weapon 2"
                else:
                    pob_slot = "Weapon 1"

                cid = pob_session.submit_candidate(
                    raw_text,
                    candidate_name=candidate.name or candidate.base_type,
                    slot=pob_slot,
                )

                if guide in ("generic_pob2", "navira_varashta"):
                    delta = pob_session.simulate_item(
                        slot=pob_slot,
                        raw_candidate=raw_text,
                        candidate_id=cid,
                        candidate_name=candidate.name or candidate.base_type,
                    )
                    if delta is not None:
                        dps = getattr(delta, "dps_delta", 0.0) or 0.0
                        life = getattr(delta, "life_delta", 0.0) or 0.0
                        ehp = getattr(delta, "ehp_delta", 0.0) or 0.0

                        gains = []
                        trade_offs = []
                        if dps > 0:
                            gains.append(f"+{dps:.1f}% DPS")
                        elif dps < 0:
                            trade_offs.append(f"{dps:.1f}% DPS")
                        if life > 0:
                            gains.append(f"+{life:.0f} Life")
                        elif life < 0:
                            trade_offs.append(f"{life:.0f} Life")
                        if ehp > 0:
                            gains.append(f"+{ehp:.1f} EHP")
                        elif ehp < 0:
                            trade_offs.append(f"{ehp:.1f} EHP")

                        prefix = "⚡ UPGRADE SORCERESS" if guide == "navira_varashta" else "⚔️ UPGRADE SENJATA"
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
                            zone_name=zone_profile.friendly_name,
                            zone_threat_warning=zone_profile.survival_notes,
                            actionable_recommendation=action,
                            gains_bullets=gains,
                            trade_off_bullets=trade_offs,
                        )
                        formatted = f"{badge}\n\n{candidate.name or candidate.base_type}\n\n{headline}\n{action}"
                        policy_label = "Navira Varashta Optimizer" if guide == "navira_varashta" else "PoB2 Generic Optimizer"
                        return {
                            "success": True,
                            "item_name": candidate.name or candidate.base_type,
                            "base_type": candidate.base_type,
                            "slot": requested_slot or (candidate.slot.value if candidate.slot else "main_hand"),
                            "verdict": verdict.value,
                            "reason": headline,
                            "gains": gains,
                            "trade_offs": trade_offs,
                            "formatted_report": formatted,
                            "policy_verdict": f"{policy_label}: {badge}",
                            "dps_delta": dps,
                            "life_delta": life,
                            "is_weapon": True,
                            "tactical_advice": tactical.model_dump(),
                        }

                from companion.equipment.fubgun_weapon_router import FubgunWeaponProfileRouter
                from companion.equipment.schema import WeaponSetContext

                router = FubgunWeaponProfileRouter()
                currently_equipped_weapons = {
                    "Weapon 1": getattr(pob_session, "get_current_item_name", lambda s: None)("Weapon 1"),
                    "Weapon 2": getattr(pob_session, "get_current_item_name", lambda s: None)("Weapon 2"),
                    "Weapon 1 Swap": getattr(pob_session, "get_current_item_name", lambda s: None)("Weapon 1 Swap"),
                    "Weapon 2 Swap": getattr(pob_session, "get_current_item_name", lambda s: None)("Weapon 2 Swap"),
                }
                route_res = router.route_candidate(
                    candidate=candidate,
                    stage=stage,
                    raw_text=raw_text,
                    candidate_id=cid,
                    currently_equipped=currently_equipped_weapons,
                )
                if not route_res.is_valid:
                    header = "🔴 REJECT / INCOMPATIBLE" if "breaker" not in route_res.rejection_reason.lower() else "🔴 REJECT / BUILD BREAKER"
                    formatted = f"{header}\n\n{candidate.name or candidate.base_type}\n\nReason:\n{route_res.rejection_reason}"
                    from companion.equipment.tactical_advisor import TacticalAdvice
                    tactical = TacticalAdvice(
                        verdict=Verdict.REJECT,
                        verdict_badge="🛑 SENJATA INKOMPATIBEL",
                        tactical_headline=f"Senjata ini ({candidate.name or candidate.base_type}) tidak kompatibel dengan build aktif!",
                        zone_name=zone_profile.friendly_name,
                        zone_threat_warning=zone_profile.survival_notes,
                        actionable_recommendation=f"Jangan pasang! {route_res.rejection_reason}. Tetap gunakan senjata yang sesuai dengan skill build Anda.",
                        trade_off_bullets=[route_res.rejection_reason],
                    )
                    return {
                        "success": True,
                        "item_name": candidate.name or candidate.base_type,
                        "base_type": candidate.base_type,
                        "slot": requested_slot or (candidate.slot.value if candidate.slot else "main_hand"),
                        "verdict": Verdict.REJECT.value,
                        "reason": route_res.rejection_reason,
                        "gains": [],
                        "trade_offs": [route_res.rejection_reason],
                        "formatted_report": formatted,
                        "dps_delta": 0.0,
                        "life_delta": 0,
                        "is_weapon": True,
                        "tactical_advice": tactical.model_dump(),
                    }

                # If caller didn't explicitly request a specific slot, use router's target slot
                if not requested_slot:
                    pob_slot = route_res.target_slot or pob_slot

                # Check if matches current
                current_in_target = getattr(pob_session, "get_current_item_name", lambda s: None)(pob_slot)
                if current_in_target and candidate.name == current_in_target:
                    return {
                        "success": True,
                        "item_name": candidate.name or candidate.base_type,
                        "base_type": candidate.base_type,
                        "slot": requested_slot or pob_slot.lower().replace(" ", "_"),
                        "verdict": "ALREADY_EQUIPPED",
                        "reason": f"{pob_slot} is already recorded as Current Weapon ({candidate.name}).",
                        "gains": [],
                        "trade_offs": [],
                        "formatted_report": f"⚪ ALREADY EQUIPPED\n\n{candidate.name} is already equipped in {pob_slot}.",
                        "is_weapon": True,
                    }

                # Ambiguous placement (e.g. 1H weapon) when no specific slot requested
                if not requested_slot and route_res.topology_plan and route_res.topology_plan.is_ambiguous_placement and hasattr(pob_session, "simulate_ambiguous_1h_weapon"):
                    dual_wep = pob_session.simulate_ambiguous_1h_weapon(
                        raw_candidate=raw_text,
                        candidate_id=cid,
                        candidate_name=candidate.name or candidate.base_type,
                        target_set=route_res.target_set,
                        build_stage=stage,
                    )
                    if dual_wep is not None and dual_wep.slot1_delta and dual_wep.slot2_delta:
                        from companion.equipment.fubgun_priorities import evaluate_dual_weapon_policy
                        advice_dual = evaluate_dual_weapon_policy(
                            dual_wep.slot1_delta,
                            dual_wep.slot2_delta,
                            stage=stage,
                            slot1_name="Weapon 1 Swap" if route_res.target_set == WeaponSetContext.WEAPON_SET_2 else "Weapon 1",
                            slot2_name="Weapon 2 Swap" if route_res.target_set == WeaponSetContext.WEAPON_SET_2 else "Weapon 2",
                        )
                        if advice_dual:
                            rec_slot = advice_dual.recommended_slot or ("Weapon 1" if route_res.target_set == WeaponSetContext.WEAPON_SET_1 else "Weapon 1 Swap")
                            return {
                                "success": True,
                                "item_name": candidate.name or candidate.base_type,
                                "base_type": candidate.base_type,
                                "slot": rec_slot.lower().replace(" ", "_"),
                                "recommended_slot": advice_dual.recommended_slot,
                                "verdict": advice_dual.summary_verdict,
                                "reason": advice_dual.summary_verdict,
                                "gains": advice_dual.rec1.gains + advice_dual.rec2.gains,
                                "trade_offs": advice_dual.trade_off_notes,
                                "formatted_report": advice_dual.formatted_output,
                                "is_weapon": True,
                            }

                # Specific weapon simulation plan
                if not requested_slot and route_res.context and hasattr(pob_session, "simulate_weapon_plan"):
                    delta = pob_session.simulate_weapon_plan(route_res.context)
                else:
                    delta = pob_session.simulate_item(
                        slot=pob_slot,
                        raw_candidate=raw_text,
                        candidate_id=cid,
                        candidate_name=candidate.name or candidate.base_type,
                    )

                if delta is not None:
                    rec = evaluate_fubgun_weapon_policy(
                        delta,
                        skill_context=route_res.skill_context if not requested_slot else None,
                        stage=stage,
                        use_color=False,
                    )
                    from companion.equipment.recommendation import Verdict
                    tactical = generate_tactical_advice(
                        delta=delta,
                        candidate_raw=raw_text,
                        current_raw=_get_current_raw(pob_slot),
                        zone_id=zone_id,
                        character_level=char_level,
                        stage=stage,
                        character_stats=char_stats_context,
                    )
                    final_verdict = merge_verdicts(rec.verdict, tactical.verdict)
                    slot_key = requested_slot or (candidate.slot.value if candidate.slot else "main_hand")
                    cur_name, cur_base = _get_current_info(slot_key)
                    return {
                        "success": True,
                        "item_name": candidate.name or candidate.base_type,
                        "base_type": candidate.base_type,
                        "current_item_name": getattr(delta, "current_item_name", None) or cur_name,
                        "current_item_base_type": cur_base,
                        "slot": slot_key,
                        "verdict": final_verdict,
                        "reason": tactical.tactical_headline if final_verdict == "REJECT" and getattr(rec.verdict, "value", str(rec.verdict)) != "REJECT" else rec.reason,
                        "gains": rec.gains,
                        "trade_offs": rec.trade_offs,
                        "formatted_report": rec.formatted_output,
                        "dps_delta": getattr(delta, "dps_delta", 0.0),
                        "life_delta": getattr(delta, "life_delta", 0),
                        "is_weapon": True,
                        "tactical_advice": tactical.model_dump(),
                    }
            elif candidate.slot in (SlotType.RING_1, SlotType.RING_2) or "ring" in candidate.base_type.lower():
                cid = pob_session.submit_candidate(
                    raw_text,
                    candidate_name=candidate.name or candidate.base_type,
                    slot="Ring 1",
                )
                dual_res = pob_session.simulate_ring_candidate(
                    raw_candidate=raw_text,
                    candidate_id=cid,
                    candidate_name=candidate.name or candidate.base_type,
                )
                if dual_res is not None:
                    from companion.equipment.fubgun_priorities import evaluate_dual_ring_policy
                    advice = evaluate_dual_ring_policy(
                        dual_res.ring1_delta,
                        dual_res.ring2_delta,
                        stage=stage,
                        empty_ring1=pob_session.is_slot_empty("Ring 1"),
                        empty_ring2=pob_session.is_slot_empty("Ring 2"),
                    )
                    if advice:
                        from companion.equipment.recommendation import Verdict

                        if advice.recommended_slot == "Ring 1":
                            ring_verdict = advice.ring1_recommendation.verdict.value
                            gains = advice.ring1_recommendation.gains
                            trade_offs = advice.ring1_recommendation.trade_offs + advice.trade_off_notes
                            chosen_delta = dual_res.ring1_delta
                        elif advice.recommended_slot == "Ring 2":
                            ring_verdict = advice.ring2_recommendation.verdict.value
                            gains = advice.ring2_recommendation.gains
                            trade_offs = advice.ring2_recommendation.trade_offs + advice.trade_off_notes
                            chosen_delta = dual_res.ring2_delta
                        else:
                            if (
                                advice.ring1_recommendation.verdict == Verdict.REJECT
                                and advice.ring2_recommendation.verdict == Verdict.REJECT
                            ):
                                ring_verdict = Verdict.REJECT.value
                            else:
                                ring_verdict = Verdict.CONDITIONAL_UPGRADE.value
                            gains = list(dict.fromkeys(advice.ring1_recommendation.gains + advice.ring2_recommendation.gains))
                            trade_offs = advice.trade_off_notes or list(
                                dict.fromkeys(advice.ring1_recommendation.trade_offs + advice.ring2_recommendation.trade_offs)
                            )
                            chosen_delta = dual_res.ring1_delta

                        tactical = generate_tactical_advice(
                            delta=chosen_delta,
                            candidate_raw=raw_text,
                            current_raw=_get_current_raw(advice.recommended_slot or "Ring 1"),
                            zone_id=zone_id,
                            character_level=char_level,
                            stage=stage,
                            character_stats=char_stats_context,
                        )
                        final_verdict = merge_verdicts(ring_verdict, tactical.verdict)

                        target_slot = (
                            advice.recommended_slot.lower().replace(" ", "")
                            if advice.recommended_slot
                            else (requested_slot or "ring1")
                        )
                        cur_name, cur_base = _get_current_info(target_slot)

                        return {
                            "success": True,
                            "item_name": candidate.name or candidate.base_type,
                            "base_type": candidate.base_type,
                            "current_item_name": getattr(chosen_delta, "current_item_name", None) or cur_name,
                            "current_item_base_type": cur_base,
                            "slot": target_slot,
                            "recommended_slot": advice.recommended_slot,
                            "verdict": final_verdict,
                            "reason": tactical.tactical_headline if final_verdict == "REJECT" and ring_verdict != "REJECT" else advice.summary_verdict,
                            "gains": gains,
                            "trade_offs": trade_offs,
                            "formatted_report": advice.formatted_output,
                            "is_weapon": False,
                            "tactical_advice": tactical.model_dump(),
                        }
            else:
                from companion.equipment.pob2_equipment_advisor import normalize_and_validate_pob_slot
                pob_slot = normalize_and_validate_pob_slot(candidate.slot)
                cid = pob_session.submit_candidate(
                    raw_text,
                    candidate_name=candidate.name or candidate.base_type,
                    slot=pob_slot,
                )
                delta = pob_session.simulate_item(
                    slot=pob_slot,
                    raw_candidate=raw_text,
                    candidate_id=cid,
                    candidate_name=candidate.name or candidate.base_type,
                )
                if delta is not None:
                    rec = evaluate_fubgun_equipment_policy(delta, stage=stage, use_color=False)
                    tactical = generate_tactical_advice(
                        delta=delta,
                        candidate_raw=raw_text,
                        current_raw=_get_current_raw(pob_slot),
                        zone_id=zone_id,
                        character_level=char_level,
                        stage=stage,
                        character_stats=char_stats_context,
                    )
                    final_verdict = merge_verdicts(rec.verdict, tactical.verdict)
                    report = rec.formatted_output
                    if final_verdict == "REJECT" and "REJECT" not in str(getattr(rec, "verdict", "")):
                        slot_display_map = {
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
                        disp_slot = slot_display_map.get(pob_slot.lower().replace(" ", ""), pob_slot)
                        report = (
                            f"=== Zone-Aware Equipment Recommendation ===\n"
                            f"Candidate : {candidate.name or candidate.base_type}\n"
                            f"Slot      : {disp_slot}\n"
                            f"Verdict   : REJECT (HOLD CURRENT GEAR)\n"
                            f"Reason    : {tactical.tactical_headline}\n"
                            f"Action    : {tactical.actionable_recommendation}\n"
                        )
                    slot_key = requested_slot or (candidate.slot.value if candidate.slot else pob_slot.lower())
                    cur_name, cur_base = _get_current_info(slot_key)
                    return {
                        "success": True,
                        "item_name": candidate.name or candidate.base_type,
                        "base_type": candidate.base_type,
                        "current_item_name": getattr(delta, "current_item_name", None) or cur_name,
                        "current_item_base_type": cur_base,
                        "slot": slot_key,
                        "verdict": final_verdict,
                        "reason": tactical.tactical_headline if final_verdict == "REJECT" and "REJECT" not in str(getattr(rec, "verdict", "")) else rec.reason,
                        "gains": rec.gains,
                        "trade_offs": rec.trade_offs,
                        "formatted_report": report,
                        "dps_delta": getattr(delta, "dps_delta", 0.0),
                        "life_delta": getattr(delta, "life_delta", 0),
                        "is_weapon": False,
                        "tactical_advice": tactical.model_dump(),
                    }
        except Exception:
            pass

    # 2. Standard Engine live candidate evaluation (always available locally)
    try:
        from companion.equipment.schema import WeaponSetContext
        engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)

        target_wset = None
        target_slot_param = requested_slot
        if requested_slot:
            req_clean = requested_slot.lower().strip()
            if req_clean.startswith("set2_") or req_clean.startswith("swap_"):
                target_wset = WeaponSetContext.WEAPON_SET_2
                target_slot_param = req_clean.replace("set2_", "").replace("swap_", "")
            elif req_clean in ("weapon_1_swap", "weapon 1 swap"):
                target_wset = WeaponSetContext.WEAPON_SET_2
                target_slot_param = "main_hand"
            elif req_clean in ("weapon_2_swap", "weapon 2 swap"):
                target_wset = WeaponSetContext.WEAPON_SET_2
                target_slot_param = "off_hand"
            elif is_weapon:
                target_wset = WeaponSetContext.WEAPON_SET_1

        formatted_report = evaluate_live_candidate(
            candidate_text=raw_text,
            engine=engine,
            runtime_dir=runtime_dir,
            character_id=char_id,
            stage=stage,
            target_weapon_set="set_2" if target_wset == WeaponSetContext.WEAPON_SET_2 else None,
        )

        rec = engine.evaluate_candidate(
            item_text=raw_text,
            character_id=char_id,
            stage=stage,
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

        reason = getattr(rec, "verdict_reason", None) or getattr(rec, "reason", "Evaluated by Equipment Intelligence Engine")
        verdict = rec.verdict.value if hasattr(rec.verdict, "value") else str(rec.verdict)
        slot_value = requested_slot or (candidate.slot.value if candidate.slot else "equipment")
        cur_name, cur_base = _get_current_info(slot_value)

        tactical_dict = None
        try:
            from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
            delta_fb = PobEquipmentDelta(
                slot=candidate.slot.value if candidate.slot else "equipment",
                candidate_id=0,
                candidate_name=candidate.name or candidate.base_type,
                current_item_name=cur_name,
                life_delta=int(proj.life.delta) if getattr(proj.life, "is_delta_known", False) else 0,
                fire_res_delta=int(proj.fire_res.delta) if getattr(proj.fire_res, "is_delta_known", False) else 0,
                cold_res_delta=int(proj.cold_res.delta) if getattr(proj.cold_res, "is_delta_known", False) else 0,
                lightning_res_delta=int(proj.lightning_res.delta) if getattr(proj.lightning_res, "is_delta_known", False) else 0,
                chaos_res_delta=int(proj.chaos_res.delta) if getattr(proj.chaos_res, "is_delta_known", False) else 0,
                armour_delta=int(proj.armour.delta) if getattr(proj.armour, "is_delta_known", False) else 0,
                evasion_delta=int(proj.evasion.delta) if getattr(proj.evasion, "is_delta_known", False) else 0,
                es_delta=int(proj.energy_shield.delta) if getattr(proj.energy_shield, "is_delta_known", False) else 0,
                ehp_delta=float(proj.life.delta) if getattr(proj.life, "is_delta_known", False) else 0.0,
                strength_delta=int(proj.strength.delta) if getattr(proj.strength, "is_delta_known", False) else 0,
                dexterity_delta=int(proj.dexterity.delta) if getattr(proj.dexterity, "is_delta_known", False) else 0,
                intelligence_delta=int(proj.intelligence.delta) if getattr(proj.intelligence, "is_delta_known", False) else 0,
            )
            tactical = generate_tactical_advice(
                delta=delta_fb,
                candidate_raw=raw_text,
                current_raw=_get_current_raw(slot_value),
                zone_id=zone_id,
                character_level=char_level,
                stage=stage,
                character_stats=char_stats_context,
            )
            tactical_dict = tactical.model_dump()
        except Exception:
            pass

        out: dict[str, Any] = {
            "success": True,
            "item_name": candidate.name or candidate.base_type,
            "base_type": candidate.base_type,
            "current_item_name": cur_name,
            "current_item_base_type": cur_base,
            "slot": slot_value,
            "verdict": verdict,
            "reason": reason,
            "gains": gains,
            "trade_offs": trade_offs,
            "formatted_report": formatted_report,
            "is_weapon": is_weapon,
        }
        if tactical_dict:
            out["tactical_advice"] = tactical_dict
            if tactical:
                tac_v = getattr(tactical.verdict, "value", str(tactical.verdict))
                if tac_v == "REJECT":
                    out["verdict"] = "REJECT"
                    if "REJECT" not in str(getattr(rec, "verdict", "")):
                        slot_display_map = {
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
                        disp_slot = slot_display_map.get(slot_value.lower().replace(" ", ""), slot_value.capitalize())
                        out["reason"] = tactical.tactical_headline
                        out["formatted_report"] = (
                            f"=== Zone-Aware Equipment Recommendation ===\n"
                            f"Candidate : {candidate.name or candidate.base_type}\n"
                            f"Slot      : {disp_slot}\n"
                            f"Verdict   : REJECT (HOLD CURRENT GEAR)\n"
                            f"Reason    : {tactical.tactical_headline}\n"
                            f"Action    : {tactical.actionable_recommendation}\n"
                        )
                elif tac_v == "EQUIP_NOW":
                    out["verdict"] = "EQUIP_NOW"
                    out["reason"] = tactical.tactical_headline
                elif tac_v == "CONDITIONAL_UPGRADE" and "INSUFFICIENT_DATA" in str(getattr(rec, "verdict", "")):
                    out["verdict"] = "CONDITIONAL_UPGRADE"
                    out["reason"] = tactical.tactical_headline
        return out
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

    chars_dir = runtime_dir / "characters"
    if chars_dir.is_dir():
        for f in chars_dir.glob("*.json"):
            if f.stem.lower() == str(char_id).lower():
                char_id = f.stem
                break

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
    """Import full character equipment JSON (from GGG get-items or export)."""
    char_id = payload.get("character_id", "BOMSHAK")
    raw_payload = payload.get("character_data") or payload
    if not isinstance(raw_payload, dict):
        return {"error": "Invalid character JSON data."}
    overwrite = payload.get("overwrite", True)

    from companion.equipment.api_adapter import GGGCharacterAPIAdapter
    from companion.equipment.loadout_cli import load_loadout, save_loadout
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
            for attr_name in (
                "life", "armour", "evasion", "energy_shield", "mana", "spirit", "deflection",
                "raw_fire_res", "effective_fire_res", "max_fire_res", "fire_overcap_buffer",
                "raw_cold_res", "effective_cold_res", "max_cold_res", "cold_overcap_buffer",
                "raw_lightning_res", "effective_lightning_res", "max_lightning_res", "lightning_overcap_buffer",
                "raw_chaos_res", "effective_chaos_res", "max_chaos_res", "chaos_overcap_buffer",
                "strength", "dexterity", "intelligence", "movement_speed",
            ):
                curr_fact = getattr(current_baseline, attr_name, None)
                if curr_fact is not None and getattr(curr_fact, "is_known", False):
                    setattr(baseline, attr_name, curr_fact)
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



def fetch_public_profile(account_name: str, character_id: str, runtime_dir: Path, overwrite: bool = True) -> dict[str, Any]:
    """Attempt to fetch public profile items from pathofexile.com."""
    import sys
    import urllib.parse
    import urllib.request

    account_name = account_name.strip()
    character_id = character_id.strip()

    # 1. First check if official PoE2 GGG API is available via pob_mcp
    try:
        from companion.equipment.pob2_equipment_advisor import resolve_pob2_backend_path
        backend_path = resolve_pob2_backend_path()
        if backend_path:
            server_dir = backend_path / "server"
            import_dir = server_dir if server_dir.exists() else backend_path
            if str(import_dir) not in sys.path:
                sys.path.insert(0, str(import_dir))
            from pob_mcp import poe_oauth, poe_api
            token = poe_oauth.get_valid_token()
            if token:
                raw_data = poe_api.fetch_character_raw(character_id)
                parsed_data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
                res = import_character_payload({"character_id": character_id, "character_data": parsed_data, "overwrite": overwrite}, runtime_dir)
                if res.get("success"):
                    res["message"] = f"Berhasil menarik {res.get('imported_slots')} slot perlengkapan resmi untuk {character_id} dari GGG PoE2 API!"
                    return res
    except Exception:
        pass

    # 2. Fallback to web endpoints: if user entered mikaelzo#5674, try exact name first, then clean name
    candidates = [account_name]
    if "#" in account_name:
        clean_name = account_name.split("#")[0].strip()
        if clean_name and clean_name not in candidates:
            candidates = [account_name, clean_name]

    last_error = None
    last_error_candidate = account_name
    last_url = ""

    for candidate in candidates:
        encoded_acc = urllib.parse.quote(candidate)
        encoded_char = urllib.parse.quote(character_id)
        url = f"https://www.pathofexile.com/character-window/get-items?accountName={encoded_acc}&character={encoded_char}"
        last_url = url

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Referer": "https://www.pathofexile.com/",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return import_character_payload({"character_id": character_id, "character_data": data, "overwrite": overwrite}, runtime_dir)
        except urllib.error.HTTPError as e:
            if last_error is None:
                last_error = e
                last_error_candidate = candidate
            continue
        except Exception as e:
            if last_error is None:
                last_error = e
            continue

    if last_error:
        if isinstance(last_error, urllib.error.HTTPError):
            if last_error.code == 403:
                return {
                    "error": "PROFILE_PRIVATE_OR_BLOCKED",
                    "code": 403,
                    "account_name": last_error_candidate,
                    "message": (
                        f"Akun '{last_error_candidate}' terdeteksi PRIVATE atau diblokir oleh GGG (HTTP 403 Forbidden).\n\n"
                        "Penyebab Teknis PoE 2:\n"
                        "GGG telah mengunci endpoint publik lama. Karakter PoE 2 TIDAK BISA ditarik lewat web publik tanpa login OAuth resmi, meskipun akun Anda sudah diset Public.\n\n"
                        "Solusi Praktis PoE 2:\n"
                        "1. Shortcut Ctrl+C: Arahkan kursor ke item di dalam game lalu tekan Ctrl+C (clipboard auto-scanner akan langsung mendeteksi & mengevaluasi item).\n"
                        "2. Opsi B (Paste JSON): Jika Anda memiliki export data karakter / PoB2, tempelkan ke tab 'Paste Character JSON'."
                    ),
                    "url": last_url,
                }
            elif last_error.code == 404:
                return {
                    "error": "ACCOUNT_OR_CHARACTER_NOT_FOUND",
                    "code": 404,
                    "account_name": account_name,
                    "message": (
                        f"Karakter '{character_id}' untuk akun '{account_name}' tidak ditemukan (HTTP 404 Not Found).\n\n"
                        "Penyebab Teknis:\n"
                        "Endpoint web warisan GGG (character-window) hanya melayani karakter Path of Exile 1 dan belum mengekspos karakter PoE 2 ke web publik tanpa OAuth 2.0 resmi.\n\n"
                        "Solusi Praktis PoE 2:\n"
                        "1. Shortcut Ctrl+C: Arahkan kursor ke item di dalam game lalu tekan Ctrl+C (clipboard auto-scanner akan langsung mendeteksi & mengevaluasi item).\n"
                        "2. Opsi B (Paste JSON): Jika Anda memiliki export data karakter / PoB2, tempelkan ke tab 'Paste Character JSON'."
                    ),
                    "url": last_url,
                }
        return {"error": f"HTTP Error: {last_error}", "url": last_url}
    return {"error": "Gagal menghubungi server PoE.", "url": last_url}


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
            from companion.dashboard_server import _GLOBAL_POB_SESSIONS, _GLOBAL_POB_SESSION
            target_pob = _GLOBAL_POB_SESSIONS.get(char_id) or _GLOBAL_POB_SESSION
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
    """Discover available characters for an account from PoB2 OAuth status and local runtime files."""
    if runtime_dir is None:
        runtime_dir = Path(__file__).resolve().parent.parent / "runtime"

    characters: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    # 1. Read from PoB2 backend oauth_status.json
    try:
        from companion.equipment.pob2_equipment_advisor import resolve_pob2_backend_path
        backend_path = resolve_pob2_backend_path()
        if backend_path:
            oauth_file = backend_path / "oauth_status.json"
            if oauth_file.is_file():
                oauth_data = json.loads(oauth_file.read_text(encoding="utf-8"))
                for c in oauth_data.get("characters", []):
                    c_name = c.get("name")
                    if c_name and c_name not in seen_names:
                        seen_names.add(c_name)
                        characters.append({
                            "name": c_name,
                            "level": c.get("level", 1),
                            "class": c.get("class", "Unknown"),
                            "league": c.get("league", "Standard"),
                        })
    except Exception:
        pass

    # 2. Augment / merge with local characters in runtime_dir / "characters"
    char_dir = runtime_dir / "characters"
    if char_dir.is_dir():
        for f in char_dir.glob("*.json"):
            try:
                c_data = json.loads(f.read_text(encoding="utf-8"))
                c_name = c_data.get("character_name") or c_data.get("character_id") or f.stem
                if c_name not in seen_names:
                    seen_names.add(c_name)
                    lvl_obj = c_data.get("level", 1)
                    lvl_val = (
                        lvl_obj.get("value", 1)
                        if isinstance(lvl_obj, dict)
                        else (lvl_obj if isinstance(lvl_obj, int) else 1)
                    )
                    characters.append({
                        "name": c_name,
                        "level": lvl_val,
                        "class": c_data.get("character_class", "Unknown"),
                        "league": "Local",
                    })
                else:
                    for ch in characters:
                        if ch["name"] == c_name:
                            lvl_obj = c_data.get("level")
                            if isinstance(lvl_obj, dict) and "value" in lvl_obj:
                                ch["level"] = lvl_obj["value"]
                            elif isinstance(lvl_obj, int):
                                ch["level"] = lvl_obj
                            if c_data.get("character_class") and ch["class"] in ("Unknown", ""):
                                ch["class"] = c_data["character_class"]
            except Exception:
                pass

    if not characters:
        characters = [{"name": "BOMSHAK", "level": 19, "class": "Mercenary", "league": "Forbidden Rites"}]

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


def get_available_guides() -> dict[str, Any]:
    """Return available build guides and supported progression stages."""
    return {
        "guides": [
            {
                "id": "fubgun_flameblast",
                "name": "Fubgun Flameblast Oil Grenade (Mercenary)",
                "class": "Mercenary",
                "stages": [
                    "auto",
                    "lvl 1-14",
                    "lvl 15-32",
                    "lvl 33-51",
                    "lvl 52 swap",
                    "lvl 53-68",
                    "lvl 85",
                    "endgame",
                    "mageblood",
                    "dot cap",
                ],
            },
            {
                "id": "navira_varashta",
                "name": "Navira's Fracturing Varashta (Sorceress)",
                "class": "Sorceress",
                "stages": [
                    "auto",
                    "Act 1 & 2",
                    "Act 2",
                    "Act 3",
                    "Act 4 to Endgame",
                    "Early Endgame",
                    "Mid-Endgame",
                    "Late Endgame",
                    "Uber Endgame",
                ],
            },
            {
                "id": "generic_pob2",
                "name": "Generic PoB2 Optimizer (Any Class / Witch / Ranger / Sorceress)",
                "class": "Any",
                "stages": ["auto"],
            },
        ]
    }


