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


RE_LIFE_REGEN = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s+Life\s+Regeneration\s+per\s+second",
    re.IGNORECASE,
)
RE_ATTR = re.compile(
    r"\+([0-9]+)\s+to\s+(Strength|Dexterity|Intelligence|all\s+Attributes)",
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
    for match in RE_ATTR.finditer(text):
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


def generate_tactical_advice(
    delta: Any,
    candidate_raw: str = "",
    current_raw: str = "",
    zone_id: str | None = None,
    character_level: int | None = None,
    stage: BuildProgressionStage | None = None,
    base_verdict: Verdict | None = None,
) -> TacticalAdvice:
    """Evaluate equipment comparison with zone context, sustain awareness, and bold decision-making."""
    lvl = character_level or 19
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
        is_pre_swap
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
        if is_offensive_slot and (dps_delta <= -2.0 or (dps_delta < -0.5 and life_delta < 0) or flat_damage_lost):
            sustain_desc = " serta menghilangkan sustain Life/Mana" if sustain_lost else ""
            headline = f"{current_name} LEBIH BAGUS! Jangan ganti {slot_label} sekarang! Menukar ke {candidate_name} memotong damage ofensif ({dps_delta:+.2f} DPS){sustain_desc}."
        elif is_weapon_slot and dps_delta < -0.5:
            headline = f"{current_name} LEBIH BAGUS! Jangan ganti senjata sekarang! Menukar ke {candidate_name} menurunkan DPS ({dps_delta:+.2f} DPS)."
        elif is_boots_slot and ms_delta < -0.05:
            headline = f"{current_name} LEBIH BAGUS! Jangan ganti sepatu sekarang! Menukar ke {candidate_name} menurunkan Movement Speed ({ms_delta:g}%)."
        elif total_attr_loss >= 10 and (dps_delta < 0 or life_delta <= 0):
            headline = f"{current_name} LEBIH BAGUS! Jangan ganti {slot_label} sekarang! Menukar ke {candidate_name} menyebabkan defisit atribut besar ({', '.join(attr_penalties)}) serta kehilangan DPS/darah."
        else:
            headline = (
                f"{current_name} LEBIH BAGUS! Jangan ganti {slot_label} sekarang! Menukar ke {candidate_name} "
                f"menurunkan ketahanan elemental atau pertahanan dasar."
            )

        # Actionable tactical recommendation
        if cand_regen > 3.0:
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
        if is_weapon_slot:
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

    return TacticalAdvice(
        verdict=verdict,
        verdict_badge=badge,
        tactical_headline=headline,
        zone_name=zone_profile.friendly_name,
        zone_threat_warning=zone_warning or zone_profile.survival_notes,
        sustain_evaluation=sustain_note,
        attribute_warning=" ".join(attr_warnings),
        actionable_recommendation=action,
        trade_off_bullets=base_rec.trade_offs,
    )
