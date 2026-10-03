"""Tactical & Decisive Equipment Advisor for Path of Exile 2.

Synthesizes PoB2 simulation deltas, zone & boss threat intelligence, sustain (Life Regen),
and attribute requirement checks to provide bold, actionable tactical advice.
"""

from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, Field

from companion.equipment.fubgun_priorities import (
    evaluate_fubgun_equipment_policy,
    evaluate_fubgun_helmet_policy,
    infer_stage_from_level,
)
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.zone_threats import ZoneThreatProfile, get_zone_threat_profile


class TacticalAdvice(BaseModel):
    """Structured, decisive tactical briefing for equipment swaps."""

    verdict: Verdict
    verdict_badge: str
    tactical_headline: str
    zone_name: str
    zone_threat_warning: str = ""
    sustain_evaluation: str = ""
    attribute_warning: str = ""
    actionable_recommendation: str = ""
    trade_off_bullets: list[str] = Field(default_factory=list)
    character_stat_context: dict[str, Any] | None = None
    stat_analysis_notes: list[str] = Field(default_factory=list)



def merge_verdicts(
    policy_verdict: Any,
    tactical_verdict: Any,
) -> str:
    """Canonical verdict merging rule across all equipment slots.

    Veto-Only Policy:
    - Tactical advice acts strictly as a safety veto (can downgrade to REJECT).
    - Tactical advice CANNOT promote a policy REJECT or CONDITIONAL_UPGRADE to EQUIP_NOW.
    - If policy is REJECT, result is REJECT regardless of tactical.
    - If tactical is REJECT, result is REJECT (tactical veto).
    - If policy is CONDITIONAL_UPGRADE, result remains CONDITIONAL_UPGRADE unless vetoed by tactical.
    - If policy is EQUIP_NOW and tactical is not REJECT, result is EQUIP_NOW.
    - Handles string, Verdict enum, or None inputs safely.
    """
    p_str = getattr(policy_verdict, "value", str(policy_verdict or "")).strip().upper()
    t_str = getattr(tactical_verdict, "value", str(tactical_verdict or "")).strip().upper()

    if p_str == "NONE":
        p_str = ""
    if t_str == "NONE":
        t_str = ""

    if t_str == "REJECT" or p_str == "REJECT":
        return "REJECT"
    if p_str == "CONDITIONAL_UPGRADE":
        return "CONDITIONAL_UPGRADE"
    if p_str == "EQUIP_NOW":
        return "EQUIP_NOW"
    return p_str or t_str or "REJECT"


RE_LIFE_REGEN = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s+Life\s+Regeneration\s+per\s+second",
    re.IGNORECASE,
)
RE_ATTR = re.compile(
    r"\+?\s*([0-9]+)\s+(?:to\s+)?(Strength|Dexterity|Intelligence|all\s+Attributes)",
    re.IGNORECASE,
)
RE_FLAT_ATTACK = re.compile(
    r"Adds\s+([0-9]+)\s+to\s+([0-9]+)\s+(?:Physical|Fire|Cold|Lightning|Chaos)?\s*Damage\s+to\s+Attacks",
    re.IGNORECASE,
)
RE_LIFE_ON_HIT = re.compile(
    r"Gain\s+([0-9]+)\s+Life\s+per\s+Enemy\s+Hit",
    re.IGNORECASE,
)
RE_MANA_ON_KILL = re.compile(
    r"([0-9]+)\s+Mana\s+per\s+(?:enemy\s+killed|Enemy\s+Killed)",
    re.IGNORECASE,
)


def _extract_life_regen(text: str) -> float:
    match = RE_LIFE_REGEN.search(text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0
    return 0.0


def _extract_flat_attack_damage(text: str) -> float:
    total = 0.0
    for match in RE_FLAT_ATTACK.finditer(text):
        low, high = float(match.group(1)), float(match.group(2))
        total += (low + high) / 2.0
    return total


def _extract_sustain(text: str) -> dict[str, int]:
    res = {"life_on_hit": 0, "mana_on_kill": 0}
    loh_m = RE_LIFE_ON_HIT.search(text)
    if loh_m:
        res["life_on_hit"] = int(loh_m.group(1))
    mok_m = RE_MANA_ON_KILL.search(text)
    if mok_m:
        res["mana_on_kill"] = int(mok_m.group(1))
    return res


def _extract_attributes(text: str) -> dict[str, int]:
    attrs: dict[str, int] = {"Strength": 0, "Dexterity": 0, "Intelligence": 0}
    for line in text.splitlines():
        clean = line.strip().lower()
        if clean.startswith("requires") or clean.startswith("requirements") or clean.startswith("level"):
            continue
        for match in RE_ATTR.finditer(line):
            val = int(match.group(1))
            attr_name = match.group(2).lower()
            if "strength" in attr_name:
                attrs["Strength"] += val
            elif "dexterity" in attr_name:
                attrs["Dexterity"] += val
            elif "intelligence" in attr_name:
                attrs["Intelligence"] += val
            elif "all" in attr_name:
                attrs["Strength"] += val
                attrs["Dexterity"] += val
                attrs["Intelligence"] += val
    return attrs


def _extract_requirements(text: str) -> dict[str, int]:
    """Extract item requirements (Level, Strength, Dexterity, Intelligence)."""
    reqs = {"level": 1, "strength": 0, "dexterity": 0, "intelligence": 0}
    in_req_section = False
    for line in text.splitlines():
        clean = line.strip()
        if clean.lower().startswith("requirements"):
            in_req_section = True
            continue
        if in_req_section and (clean.startswith("---") or clean.startswith("===")):
            in_req_section = False
            continue

        # Check level
        m_lvl = re.search(r"\bLevel\s*[:\s]\s*([0-9]+)", clean, re.IGNORECASE)
        if m_lvl:
            reqs["level"] = max(reqs["level"], int(m_lvl.group(1)))

        # Check Str
        m_str = re.search(r"\b(?:Str|Strength)\s*[:\s]\s*([0-9]+)", clean, re.IGNORECASE)
        if m_str:
            reqs["strength"] = max(reqs["strength"], int(m_str.group(1)))

        # Check Dex
        m_dex = re.search(r"\b(?:Dex|Dexterity)\s*[:\s]\s*([0-9]+)", clean, re.IGNORECASE)
        if m_dex:
            reqs["dexterity"] = max(reqs["dexterity"], int(m_dex.group(1)))

        # Check Int
        m_int = re.search(r"\b(?:Int|Intelligence)\s*[:\s]\s*([0-9]+)", clean, re.IGNORECASE)
        if m_int:
            reqs["intelligence"] = max(reqs["intelligence"], int(m_int.group(1)))

    return reqs


def _normalize_character_stats(stats: Any) -> dict[str, Any]:
    """Normalize CharacterStatBaseline, CharacterState, or dict into a flat numeric dict."""
    if not stats:
        return {}
    if hasattr(stats, "model_dump"):
        stats = stats.model_dump()
    elif not isinstance(stats, dict):
        return {}

    out: dict[str, Any] = {}
    for k in ("strength", "dexterity", "intelligence", "level", "life", "mana", "spirit", "armour", "evasion", "energy_shield"):
        val = stats.get(k)
        if isinstance(val, dict):
            val = val.get("value")
        if val is not None:
            try:
                out[k] = int(val)
            except (ValueError, TypeError):
                pass

    if "attributes" in stats and isinstance(stats["attributes"], dict):
        for attr_k in ("strength", "dexterity", "intelligence"):
            if attr_k not in out:
                v = stats["attributes"].get(attr_k)
                if isinstance(v, dict):
                    v = v.get("value")
                if v is not None:
                    try:
                        out[attr_k] = int(v)
                    except (ValueError, TypeError):
                        pass

    for res_name, key in [("fire_res", "fire"), ("cold_res", "cold"), ("lightning_res", "lightning"), ("chaos_res", "chaos")]:
        val = stats.get(res_name)
        if val is None:
            val = stats.get(f"effective_{res_name}")
        if val is None and "resistances" in stats and isinstance(stats["resistances"], dict):
            val = stats["resistances"].get(key)
        if isinstance(val, dict):
            val = val.get("value")
        if val is not None:
            try:
                out[res_name] = int(val)
            except (ValueError, TypeError):
                pass

    return out


from companion.equipment.rules import BuildProgressionStage

def evaluate_tactical_map_hazards(
    map_modifiers: list[str],
    stage: BuildProgressionStage,
    has_ignite_immunity: bool = False,
) -> list[str]:
    """Evaluate map modifiers for tactical hazards specific to the build stage."""
    warnings = []
    
    if not stage.is_pre_swap:
        # Post-swap (Lvl 52+): Oil Grenade ignite mechanics are active
        has_ignited_ground = any("ignited ground" in mod.lower() for mod in map_modifiers)
        has_ignite_risk = any("ignite" in mod.lower() for mod in map_modifiers) and not has_ignited_ground
        
        if has_ignited_ground:
            warnings.append(
                "⚠️ TACTICAL HAZARD: Ignited Ground map modifier detected. "
                "This will prematurely ignite your Oil Grenade puddles before Flameblast hits. "
                "Disable Tornado Cast on Dodge and avoid throwing oil directly onto burning ground."
            )
            
        if has_ignite_risk and not has_ignite_immunity:
            warnings.append(
                "⚠️ TACTICAL HAZARD: High Ignite risk detected without Ignite Immune/Block Charm (e.g., Thawing Charm). "
                "If you are ignited, your dodge-rolls or attacks may contaminate the oil puddle, destroying the Flameblast damage window."
            )
            
    return warnings

def generate_tactical_advice(
    delta: Any,
    candidate_raw: str = "",
    current_raw: str = "",
    zone_id: str | None = None,
    character_level: int | None = None,
    stage: BuildProgressionStage | None = None,
    base_verdict: Verdict | None = None,
    character_stats: Any = None,
) -> TacticalAdvice:
    """Evaluate equipment comparison with zone context, sustain awareness, and bold decision-making."""
    norm_stats = _normalize_character_stats(character_stats)
    lvl = character_level or norm_stats.get("level") or 19
    if stage is None:
        stage = infer_stage_from_level(lvl)

    zone_profile: ZoneThreatProfile = get_zone_threat_profile(zone_id, character_level=lvl)


    # 1. Base policy evaluation (Fubgun verified baseline)
    slot_name = getattr(delta, "slot", "Equipment")
    if slot_name == "Helmet":
        base_rec = evaluate_fubgun_helmet_policy(delta, stage=stage, use_color=False)
    else:
        base_rec = evaluate_fubgun_equipment_policy(delta, stage=stage, use_color=False)

    verdict = base_verdict if base_verdict is not None else base_rec.verdict
    candidate_name = getattr(delta, "candidate_name", None) or "Candidate Item"
    current_name = getattr(delta, "current_item_name", None) or f"Current {slot_name}"

    # 2. Extract sustain & attribute differences
    cand_regen = _extract_life_regen(candidate_raw)
    curr_regen = _extract_life_regen(current_raw)
    regen_delta = cand_regen - curr_regen

    cand_flat = _extract_flat_attack_damage(candidate_raw)
    curr_flat = _extract_flat_attack_damage(current_raw)
    cand_sustain = _extract_sustain(candidate_raw)
    curr_sustain = _extract_sustain(current_raw)

    flat_damage_lost = (curr_flat > 0 and cand_flat == 0)
    sustain_lost = (
        (curr_sustain["life_on_hit"] > 0 and cand_sustain["life_on_hit"] == 0)
        or (curr_sustain["mana_on_kill"] > 0 and cand_sustain["mana_on_kill"] == 0)
    )

    cand_attrs = _extract_attributes(candidate_raw)
    curr_attrs = _extract_attributes(current_raw)

    attr_warnings: list[str] = []
    attr_penalties: list[str] = []
    total_attr_loss = 0
    for attr in ("Strength", "Dexterity", "Intelligence"):
        delta_attr = getattr(delta, f"{attr.lower()}_delta", None)
        if delta_attr is not None and delta_attr != 0:
            loss = -delta_attr if delta_attr < 0 else 0
        else:
            loss = curr_attrs[attr] - cand_attrs[attr]
        if loss > 0:
            attr_penalties.append(f"-{loss} {attr}")
            total_attr_loss += loss
            attr_warnings.append(
                f"-{loss} {attr}: Pastikan gem atau gear lain tidak mati (berwarna merah) "
                f"akibat kehilangan {attr} dari {current_name}."
            )

    # 3. Zone threat audit
    fire_delta = getattr(delta, "fire_res_delta", 0)
    cold_delta = getattr(delta, "cold_res_delta", 0)
    lightning_delta = getattr(delta, "lightning_res_delta", 0)
    chaos_delta = getattr(delta, "chaos_res_delta", 0)
    ehp_delta = getattr(delta, "ehp_delta", 0.0)
    life_delta = getattr(delta, "life_delta", 0)

    is_lethal_drop, zone_warning = zone_profile.is_resistance_drop_dangerous(
        fire_delta=fire_delta,
        cold_delta=cold_delta,
        lightning_delta=lightning_delta,
        chaos_delta=chaos_delta,
    )

    # Decisive hardening: If the swap drops lethal zone resistance and either loses EHP/Life,
    # or drops local defenses with only minor life gain (<= 35):
    # it is NEVER a conditional upgrade — it is firmly REJECTED for the active zone!
    arm_delta = getattr(delta, "armour_delta", 0)
    eva_delta = getattr(delta, "evasion_delta", 0)
    dps_delta = getattr(delta, "dps_delta", 0.0)
    ms_delta = getattr(delta, "movement_speed_delta", 0.0)
    is_weapon_slot = (
        "weapon" in slot_name.lower()
        or getattr(delta, "is_weapon", False)
        or "hand" in slot_name.lower()
        or "bow" in slot_name.lower()
        or "crossbow" in slot_name.lower()
        or "wand" in slot_name.lower()
    )
    is_boots_slot = "boot" in slot_name.lower()

    local_defense_collapse = (arm_delta <= -30 or eva_delta <= -30 or (arm_delta + eva_delta) <= -40)

    # Universal Decisive Rules:
    # A. Lethal zone drop without overwhelming compensation
    if is_lethal_drop and (
        ehp_delta < -1.0
        or life_delta < 0
        or (life_delta <= 35 and local_defense_collapse)
        or (fire_delta <= -5 or cold_delta <= -5 or lightning_delta <= -5)
    ):
        verdict = Verdict.REJECT

    # B. Weapon DPS downgrade
    if is_weapon_slot and dps_delta < -0.5:
        verdict = Verdict.REJECT

    # C. Boots movement speed downgrade without massive defense gain
    if is_boots_slot and ms_delta <= -10.0 and life_delta <= 25 and (fire_delta + cold_delta + lightning_delta) <= 20:
        verdict = Verdict.REJECT

    # D. Attribute Deficit & Stat Drain:
    # Dropping >= 10 attributes without massive primary gain is a build hazard.
    # If it also loses DPS or loses Life, it MUST be firmly REJECTED.
    total_res_gain = max(0, fire_delta) + max(0, cold_delta) + max(0, lightning_delta) + max(0, chaos_delta)
    if total_attr_loss >= 10 and (dps_delta < 0 or life_delta <= 0 or (total_res_gain < 25 and life_delta < 40)):
        verdict = Verdict.REJECT

    # E. Core DPS and Life downgrade (Triple Negative):
    if dps_delta < -0.05 and life_delta <= 0 and total_res_gain <= 0:
        verdict = Verdict.REJECT

    # F. Offensive leveling slot DPS & Life drop (Gloves, Rings, Amulet):
    is_offensive_slot = any(k in slot_name.lower() for k in ("glove", "ring", "amulet"))
    if is_offensive_slot and (
        (dps_delta < -0.5 and life_delta < 0)
        or (dps_delta <= -2.0 and total_res_gain < 35 and life_delta <= 25)
        or (flat_damage_lost and dps_delta < 0 and total_res_gain < 35)
        or (sustain_lost and flat_damage_lost and total_res_gain < 30)
    ):
        verdict = Verdict.REJECT

    # G. Decisive Weapon DPS Upgrade (Campaign Leveling):
    # In Fubgun campaign leveling, weapons are the primary damage engine.
    # An outstanding DPS boost (dps_delta >= 5.0) with zero resistance loss
    # and only minor incidental attribute-driven life loss (life_delta >= -25) is decisively EQUIP_NOW.
    is_pre_swap = stage.is_pre_swap if stage else True
    if (
        base_verdict != Verdict.INSUFFICIENT_DATA
        and is_pre_swap
        and is_weapon_slot
        and dps_delta >= 5.0
        and fire_delta >= -5
        and cold_delta >= -5
        and lightning_delta >= -5
        and life_delta >= -25
        and ehp_delta >= -50.0
        and arm_delta >= -100
    ):
        verdict = Verdict.EQUIP_NOW

    # H. Decisive Defensive Slot Upgrade (Body Armour, Helmet, Boots, Gloves, Shields):
    # When life increases or is preserved, local defenses (Armour/Evasion/ES) increase substantially,
    # and net resistance is non-negative without a lethal zone drop:
    es_delta = getattr(delta, "es_delta", 0)
    net_res_delta = fire_delta + cold_delta + lightning_delta + chaos_delta
    total_local_defense_gain = arm_delta + eva_delta + es_delta
    is_defensive_slot = any(k in slot_name.lower() for k in ("body", "chest", "armour", "cuirass", "mail", "helmet", "boot", "shield"))

    if (
        base_verdict != Verdict.INSUFFICIENT_DATA
        and is_defensive_slot
        and life_delta >= 0
        and total_local_defense_gain >= 20
        and net_res_delta >= 0
        and not is_lethal_drop
        and total_attr_loss < 10
        and not (is_boots_slot and ms_delta < 0)
    ):
        verdict = Verdict.EQUIP_NOW

    # 4. Formulate Sustain Notes
    sustain_note = ""
    if cand_regen > 0:
        if regen_delta > 0:
            sustain_note = (
                f"+{regen_delta:.1f} Life Regen per detik pada {candidate_name} adalah sustain pasif "
                f"yang sangat besar untuk Level {lvl}. Sangat nyaman untuk eksplorasi dan farming."
            )
        else:
            sustain_note = f"{cand_regen:.1f} Life Regen per detik (sebanding dengan gear lama)."

    # 4b. Audit Character Stats Baseline & Requirements
    trade_off_bullets = list(base_rec.trade_offs)
    stat_analysis_notes: list[str] = []
    unmet_requirements: list[str] = []

    char_cold = None
    char_light = None
    char_fire = None

    if norm_stats:
        cand_reqs = _extract_requirements(candidate_raw)
        for attr_key, attr_label in (("strength", "Strength"), ("dexterity", "Dexterity"), ("intelligence", "Intelligence")):
            req_val = cand_reqs.get(attr_key, 0)
            char_val = norm_stats.get(attr_key)
            if req_val > 0 and char_val is not None and char_val < req_val:
                deficit = req_val - char_val
                msg = f"Kebutuhan Stat Tidak Terpenuhi: Membutuhkan {req_val} {attr_label} (Karakter Anda: {char_val}, kurang {deficit} {attr_label})."
                attr_warnings.append(msg)
                trade_off_bullets.append(f"Kurang {deficit} {attr_label} ({char_val}/{req_val})")
                unmet_requirements.append(f"{attr_label} {char_val}/{req_val}")

        req_lvl = cand_reqs.get("level", 1)
        char_lvl = character_level or norm_stats.get("level")
        if req_lvl > 1 and char_lvl is not None and char_lvl < req_lvl:
            lvl_def = req_lvl - char_lvl
            lvl_msg = f"Kebutuhan Level Tidak Terpenuhi: Membutuhkan Level {req_lvl} (Karakter Anda: Level {char_lvl}, kurang {lvl_def} level)."
            attr_warnings.append(lvl_msg)
            trade_off_bullets.append(f"Belum cukup level ({char_lvl}/{req_lvl})")
            unmet_requirements.append(f"Level {char_lvl}/{req_lvl}")

        # Check negative resistances
        char_cold = norm_stats.get("cold_res")
        if char_cold is not None and char_cold < 0:
            if cold_delta < 0:
                verdict = Verdict.REJECT
                neg_cold_msg = (
                    f"Resistansi Cold karakter Anda saat ini sudah di angka negatif ({char_cold}%). "
                    f"Menukar item ini akan menurunkan Cold Res menjadi {char_cold + cold_delta}%, "
                    f"sangat berbahaya dan fatal terhadap musuh tipe cold!"
                )
                attr_warnings.append(neg_cold_msg)
                trade_off_bullets.append(f"Cold Res makin jatuh: {char_cold}% -> {char_cold + cold_delta}%")
            elif cold_delta > 0:
                stat_analysis_notes.append(
                    f"⭐ Menambal Cold Res Kritis: +{cold_delta}% Cold Res (mengangkat resistansi dari {char_cold}% ke {char_cold + cold_delta}%)."
                )

        char_light = norm_stats.get("lightning_res")
        if char_light is not None and char_light < 0:
            if lightning_delta < 0:
                verdict = Verdict.REJECT
                neg_light_msg = (
                    f"Resistansi Lightning karakter Anda saat ini sudah di angka negatif ({char_light}%). "
                    f"Menukar item ini akan menurunkan Lightning Res menjadi {char_light + lightning_delta}%, "
                    f"sangat berbahaya terkena burst petir!"
                )
                attr_warnings.append(neg_light_msg)
                trade_off_bullets.append(f"Lightning Res makin jatuh: {char_light}% -> {char_light + lightning_delta}%")
            elif lightning_delta > 0:
                stat_analysis_notes.append(
                    f"⭐ Menambal Lightning Res Kritis: +{lightning_delta}% Lightning Res (mengangkat resistansi dari {char_light}% ke {char_light + lightning_delta}%)."
                )

        char_fire = norm_stats.get("fire_res")
        if char_fire is not None and char_fire < 0:
            if fire_delta < 0:
                verdict = Verdict.REJECT
                neg_fire_msg = (
                    f"Resistansi Fire karakter Anda saat ini sudah di angka negatif ({char_fire}%). "
                    f"Menukar item ini akan menurunkan Fire Res menjadi {char_fire + fire_delta}%!"
                )
                attr_warnings.append(neg_fire_msg)
                trade_off_bullets.append(f"Fire Res makin jatuh: {char_fire}% -> {char_fire + fire_delta}%")
            elif fire_delta > 0:
                stat_analysis_notes.append(
                    f"⭐ Menambal Fire Res Kritis: +{fire_delta}% Fire Res (mengangkat resistansi dari {char_fire}% ke {char_fire + fire_delta}%)."
                )

        char_life = norm_stats.get("life")
        if char_life and char_life > 0 and life_delta != 0:
            pct = (life_delta / char_life) * 100
            sign = "+" if life_delta > 0 else ""
            stat_analysis_notes.append(
                f"Dampak Life: {sign}{life_delta} ({sign}{pct:.1f}% dari {char_life} Base Life -> {char_life + life_delta})"
            )

    if unmet_requirements and verdict == Verdict.EQUIP_NOW:
        verdict = Verdict.CONDITIONAL_UPGRADE


    # 5. Formulate Badges & Actionable Recommendations
    slot_label = (
        "helm" if "helmet" in slot_name.lower()
        else ("zirah" if "armour" in slot_name.lower() or "chest" in slot_name.lower()
        else ("sarung tangan" if "glove" in slot_name.lower()
        else ("sepatu" if "boot" in slot_name.lower()
        else ("sabuk" if "belt" in slot_name.lower()
        else ("amulet" if "amulet" in slot_name.lower() or "kalung" in slot_name.lower()
        else ("cincin" if "ring" in slot_name.lower()
        else ("senjata" if is_weapon_slot
        else slot_name.lower())))))))
    )

    if verdict == Verdict.EQUIP_NOW:
        badge = "🟢 GANTI SEKARANG"
        if is_weapon_slot and dps_delta >= 0.5:
            headline = f"{candidate_name} LEBIH BAGUS! Pasang sekarang untuk lonjakan damage besar ({dps_delta:+.2f} DPS)."
            action = (
                f"Aman dan sangat direkomendasikan dipasang. Di build Fubgun, DPS senjata adalah motor utama "
                f"damage ledakan granat di {zone_profile.friendly_name}. Kehilangan minor darah "
                f"({life_delta:+d} Life) tidak sebanding dengan lonjakan DPS ini."
                if life_delta < 0 else
                f"Aman dan sangat direkomendasikan dipasang. Di build Fubgun, DPS senjata adalah motor utama "
                f"damage ledakan granat di {zone_profile.friendly_name}."
            )
        elif is_defensive_slot and (total_local_defense_gain >= 20 or life_delta >= 20):
            defense_parts = []
            if life_delta > 0:
                defense_parts.append(f"+{life_delta} Life")
            if total_local_defense_gain > 0:
                defense_parts.append(f"+{total_local_defense_gain} Total Pertahanan")
            summary_str = ", ".join(defense_parts) if defense_parts else "+Pertahanan"
            headline = f"{candidate_name} LEBIH BAGUS! Pasang sekarang untuk peningkatan pertahanan drastis ({summary_str})."
            action = (
                f"Sangat direkomendasikan dipasang. Menghadapi ancaman di {zone_profile.friendly_name}, "
                f"pertahanan dasar dan ketahanan yang lebih baik memberikan survivability jauh lebih unggul dibandingkan {current_name}."
            )
        else:
            headline = f"{candidate_name} LEBIH BAGUS! Pasang sekarang untuk peningkatan pertahanan dan survivability."
            action = (
                f"Aman dipasang. Peningkatan stat ini menguntungkan untuk bertahan di {zone_profile.friendly_name} "
                f"tanpa membahayakan batas pertahanan vital."
            )
    elif verdict == Verdict.INSUFFICIENT_DATA:
        badge = "⚪ BUTUH DATA BASELINE"
        headline = (
            f"Data baseline karakter belum lengkap atau belum sinkron ({current_name}). "
            f"Perlu data karakter untuk kepastian rekomendasi."
        )
        action = (
            f"Buka panel karakter in-game atau perbarui baseline agar stat dapat diproyeksikan "
            f"secara akurat sebelum memutuskan memasang {candidate_name}."
        )
    elif verdict == Verdict.REJECT:
        badge = "🛑 TAHAN GEAR LAMA"
        if norm_stats and (
            (char_cold is not None and char_cold < 0 and cold_delta < 0)
            or (char_light is not None and char_light < 0 and lightning_delta < 0)
            or (char_fire is not None and char_fire < 0 and fire_delta < 0)
        ):
            badge = "🛑 REJECT (BAHAYA RESISTANSI)"
            active_neg = []
            if char_cold is not None and char_cold < 0 and cold_delta < 0:
                active_neg.append(f"Cold ({char_cold}%)")
            if char_light is not None and char_light < 0 and lightning_delta < 0:
                active_neg.append(f"Lightning ({char_light}%)")
            if char_fire is not None and char_fire < 0 and fire_delta < 0:
                active_neg.append(f"Fire ({char_fire}%)")
            headline = f"{current_name} LEBIH BAGUS! Tolak {candidate_name} karena resistansi {', '.join(active_neg)} Anda saat ini negatif!"
            action = f"Tolak swap ini! Resistansi karakter Anda saat ini berada di angka negatif ({', '.join(active_neg)}). Kehilangan resistansi ini akan membuat Anda sering mati instan."
        elif is_offensive_slot and (dps_delta <= -2.0 or (dps_delta < -0.5 and life_delta < 0) or flat_damage_lost):
            sustain_desc = " serta menghilangkan sustain Life/Mana" if sustain_lost else ""
            headline = f"{current_name} LEBIH BAGUS! Jangan ganti {slot_label} sekarang! Menukar ke {candidate_name} memotong damage ofensif ({dps_delta:+.2f} DPS){sustain_desc}."
        elif is_weapon_slot and dps_delta < -0.5:
            headline = f"{current_name} LEBIH BAGUS! Jangan ganti senjata sekarang! Menukar ke {candidate_name} menurunkan DPS ({dps_delta:+.2f} DPS)."
        elif is_boots_slot and ms_delta < -0.05:
            headline = f"{current_name} LEBIH BAGUS! Jangan ganti sepatu sekarang! Menukar ke {candidate_name} menurunkan Movement Speed ({ms_delta:g}%)."
        elif total_attr_loss >= 10 and (dps_delta < 0 or life_delta <= 0):
            headline = f"{current_name} LEBIH BAGUS! Jangan ganti {slot_label} sekarang! Menukar ke {candidate_name} menyebabkan defisit atribut besar ({', '.join(attr_penalties)}) serta kehilangan DPS/darah."
        else:
            reasons = []
            if is_lethal_drop:
                reasons.append("menurunkan resistensi terhadap bahaya mematikan wilayah")
            if net_res_delta < 0:
                reasons.append("menurunkan total ketahanan elemental")
            if total_local_defense_gain < 0:
                reasons.append("menurunkan pertahanan dasar")
            if life_delta < 0:
                reasons.append("menurunkan Life")
            if not reasons:
                reasons.append("tidak memberikan peningkatan defensif yang signifikan")
            headline = (
                f"{current_name} LEBIH BAGUS! Jangan ganti {slot_label} sekarang! Menukar ke {candidate_name} "
                f"{' dan '.join(reasons)}."
            )

        # Actionable tactical recommendation
        if norm_stats and (
            (char_cold is not None and char_cold < 0 and cold_delta < 0)
            or (char_light is not None and char_light < 0 and lightning_delta < 0)
            or (char_fire is not None and char_fire < 0 and fire_delta < 0)
        ):
            pass  # already populated in action above
        elif cand_regen > 3.0:
            action = (
                f"Rekomendasi: Tetap gunakan {current_name} untuk menghadapi {zone_profile.upcoming_boss}. "
                f"Simpan {candidate_name} di Stash/Tas Anda — pasang nanti saat Fire Resistance Anda sudah "
                f"tertutup dari slot Ring/Amulet untuk memanfaatkan sustain {cand_regen:.1f} regen/s."
            )
        elif is_offensive_slot and (dps_delta <= -2.0 or (dps_delta < -0.5 and life_delta < 0) or flat_damage_lost):
            action = (
                f"Rekomendasi: Tetap gunakan {current_name}. {current_name} memberikan output damage ofensif "
                f"dan sustain yang jauh lebih superior untuk build granat di {zone_profile.friendly_name}."
            )
        elif is_weapon_slot and dps_delta < -0.5:
            action = (
                f"Rekomendasi: Tetap gunakan {current_name}. Senjata dengan base DPS lebih tinggi "
                f"harus selalu dipertahankan untuk leveling."
            )
        elif is_boots_slot and ms_delta < -0.05:
            action = (
                f"Rekomendasi: Tetap gunakan {current_name}. Movement Speed pada sepatu adalah prioritas "
                f"mutlak di build Fubgun."
            )
        elif total_attr_loss >= 10 and (dps_delta < 0 or life_delta <= 0):
            action = (
                f"Rekomendasi: Tetap gunakan {current_name}. {candidate_name} memotong atribut "
                f"({', '.join(attr_penalties)}) dan menurunkan DPS/Life yang berisiko melumpuhkan gem/gear Anda."
            )
        else:
            action = (
                f"Rekomendasi: Tetap gunakan {current_name}. {candidate_name} adalah net downgrade "
                f"untuk keselamatan karakter Anda di {zone_profile.friendly_name}."
            )
    else:  # CONDITIONAL_UPGRADE
        badge = "⚠️ KONDISIONAL"
        if unmet_requirements:
            badge = "⚠️ KONDISIONAL (STAT KURANG)"
            headline = f"Tahan di Stash: {candidate_name} bagus tetapi Anda kekurangan stat ({', '.join(unmet_requirements)})."
            action = f"Simpan item ini di stash. Cari tambahan {', '.join(unmet_requirements)} dari cincin/amulet atau alokasikan point di passive tree sebelum memasangnya."
        elif is_weapon_slot:
            headline = f"Pertukaran Ofensif vs Defensif: {candidate_name} vs {current_name} meningkatkan DPS ({dps_delta:+.2f}) tetapi kehilangan pertahanan ({life_delta:+d} Life)."
            action = (
                f"Pasang {candidate_name} jika Anda ingin membersihkan monster dan boss lebih cepat ({dps_delta:+.2f} DPS), "
                f"atau pertahankan {current_name} jika merasa survivability saat ini masih rapuh."
            )
        else:
            headline = f"Pertukaran Bersyarat: {candidate_name} vs {current_name} menukar tipe pertahanan."
            action = (
                f"Pertahankan {current_name}, pasang {candidate_name} HANYA jika Anda sedang mengalami defisit resistensi parah "
                f"di {zone_profile.friendly_name} (target Fire {zone_profile.recommended_res.get('fire', 30)}%)."
            )

    effective_zone_threat = ""
    if is_lethal_drop:
        effective_zone_threat = zone_warning
    else:
        lethal_positive = []
        for l_type in zone_profile.lethal_damage_types:
            l_delta = getattr(delta, f"{l_type.lower()}_res_delta", 0)
            if l_delta > 0:
                lethal_positive.append(f"+{l_delta}% {l_type.capitalize()} Res")
        if lethal_positive:
            effective_zone_threat = (
                f"Resistansi aman untuk {zone_profile.friendly_name}: "
                f"Ketahanan terhadap ancaman wilayah ({', '.join(lethal_positive)}) terjaga & meningkat."
            )

    return TacticalAdvice(
        verdict=verdict,
        verdict_badge=badge,
        tactical_headline=headline,
        zone_name=zone_profile.friendly_name,
        zone_threat_warning=effective_zone_threat,
        sustain_evaluation=sustain_note,
        attribute_warning=" ".join(attr_warnings),
        actionable_recommendation=action,
        trade_off_bullets=trade_off_bullets,
        character_stat_context=norm_stats if norm_stats else None,
        stat_analysis_notes=stat_analysis_notes,
    )

