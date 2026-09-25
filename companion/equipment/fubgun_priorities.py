"""Verified campaign gear priorities and materiality from Fubgun 0.5.5 guide.

PROVENANCE:
Primary Source: Fubgun 0.5.5 Flameblast / Oil Grenade Mobalytics guide.
Target build progression: Campaign leveling (lvl 1-14, lvl 15-32, lvl 33-51, lvl 52 Swap, lvl 53-68)
"""

from __future__ import annotations

import math
import os
import re
import sys
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, ConfigDict, Field

from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotType

if TYPE_CHECKING:
    from companion.equipment.pob2_helmet_advisor import PobHelmetDelta

FUBGUN_GUIDE_PROVENANCE = "Fubgun 0.5.5 Flameblast / Oil Grenade Mobalytics guide"

# Non-material modifiers on campaign gear that must NOT block recommendations
RE_CAMPAIGN_NON_MATERIAL = re.compile(
    r"\b("
    r"maximum\s+mana|mana\b|"
    r"regenerat[a-z]*(\s+per\s+second|\s+rate)?|"
    r"item\s+rarity|"
    r"light\s+radius|"
    r"accuracy\s+rating|accuracy\b|"
    r"stun\s+threshold|ailment\s+threshold|"
    r"stun\s+and\s+ailment\s+threshold"
    r")\b",
    re.IGNORECASE,
)

# Genuinely material effects that must be preserved conservatively even if they mention words above
RE_GENUINELY_MATERIAL = re.compile(
    r"\b("
    r"damage|adds?\b.*\bto\b|critical|strike[a-z]*|penetrat[a-z]*|multiplier[a-z]*|"
    r"applies?\s+to|taken\s+as|damage\s+taken|suppress[a-z]*|block[a-z]*|deflect[a-z]*|ward|"
    r"maximum\s+.*resistan[a-z]*|intimidate|onslaught|unholy\s+might|consecrat[a-z]*|"
    r"curse[a-z]*|blind[a-z]*|taunt[a-z]*|exposure|wither|gem[a-z]*|socketed|reserv[a-z]*|"
    r"cooldown[a-z]*|aura[a-z]*|iron\s+reflexes"
    r")\b",
    re.IGNORECASE,
)


def is_fubgun_non_material_modifier(
    mod_text: str,
    slot: SlotType | None = None,
    stage: BuildProgressionStage | None = None,
) -> bool:
    """Return True if an unsupported modifier is non-material under Fubgun campaign priorities."""
    if stage is not None and not stage.is_campaign:
        return False

    clean = mod_text.strip().lower()

    # If it contains genuinely material combat/keystone/defense mechanics, it is material!
    if RE_GENUINELY_MATERIAL.search(clean):
        # Unless it is simply stun/ailment threshold
        if not ("stun threshold" in clean or "ailment threshold" in clean or "accuracy" in clean):
            return False

    # Check non-material patterns
    if RE_CAMPAIGN_NON_MATERIAL.search(clean):
        return True

    return False


def get_fubgun_slot_priority_note(
    slot: SlotType,
    stage: BuildProgressionStage | None = None,
) -> str:
    """Return short guide priority note for the specified gear slot and progression stage."""
    stage_name = stage.value if stage else "campaign"

    if slot == SlotType.BOOTS:
        return "Fubgun — Movement Speed is critical on Boots (mandatory priority, then Resistance/Life)."

    if slot == SlotType.HELMET:
        return f"Fubgun {stage_name} — Resistance > Life (local defenses are secondary tie-breakers)."

    if slot == SlotType.BODY_ARMOUR:
        return "Fubgun — High Armour or Armour/Evasion hybrid is primary defense priority; Life + Resistance remain valuable."

    if slot in (SlotType.RING_1, SlotType.RING_2, SlotType.GLOVES):
        return "Fubgun campaign — Resistance/Life; flat damage to attacks is a meaningful offensive priority during leveling."

    if slot in (SlotType.AMULET, SlotType.BELT):
        return "Fubgun campaign — Generic Resistance/Life; attributes only according to actual requirements."

    if slot in (SlotType.MAIN_HAND, SlotType.OFF_HAND):
        if stage == BuildProgressionStage.LEVELING_15_32:
            return "Fubgun lvl15-32 — Highest damage Crossbow (Varnished Crossbow benchmark); % Physical desirable, Attack Speed is not a major value."
        if stage and stage.is_pre_swap:
            return "Fubgun pre-swap — Highest damage Crossbow; % Physical desirable."
        return "Fubgun post-swap — Set 1 Flameblast staff, Set 2 Oil Grenade crossbow."

    return f"Build priority: Fubgun {stage_name} — Resistance > Life"


def get_fubgun_build_priority_short(stage: BuildProgressionStage | None = None) -> str:
    """Return concise one-line build priority header."""
    if stage == BuildProgressionStage.LEVELING_15_32:
        return "Fubgun lvl15-32 — Resistance > Life"
    if stage and stage.is_pre_swap:
        return f"Fubgun {stage.value} — Resistance > Life"
    return "Fubgun campaign — Resistance > Life"


class FubgunEquipmentRecommendation(BaseModel):
    """Structured recommendation from applying Fubgun policy to PoB equipment deltas."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    verdict: Verdict
    reason: str
    delta: Any
    gains: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)
    stage: BuildProgressionStage | None = None
    formatted_output: str = ""


class FubgunHelmetRecommendation(FubgunEquipmentRecommendation):
    """Backward-compatible recommendation type for helmet callers."""


def _supports_color() -> bool:
    if "NO_COLOR" in os.environ:
        return False
    if os.environ.get("FORCE_COLOR") in ("1", "true", "TRUE"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def evaluate_fubgun_helmet_policy(
    delta: PobHelmetDelta,
    stage: BuildProgressionStage | None = None,
    use_color: bool | None = None,
) -> FubgunHelmetRecommendation:
    """Evaluate PoB helmet mathematical deltas against canonical Fubgun campaign policy.

    Core Fubgun Campaign Rules for Helmet:
    1. Primary leveling priorities: Resistance > Life.
    2. Local defense trades (Armour vs Evasion vs Energy Shield) are secondary tie-breakers
       provided Total EHP is not catastrophically reduced.
    3. Small negative DPS deltas resulting from an Accuracy affix drop are non-material for
       campaign helmet evaluation and MUST NOT block defensive upgrades.
    4. No arbitrary numeric weighted scoring.
    """
    if use_color is None:
        use_color = _supports_color()

    stage_name = stage.value if stage else "campaign"

    gains: list[str] = []
    trade_offs: list[str] = []

    # Compile Gains
    if delta.life_delta > 0:
        gains.append(f"+{delta.life_delta} Life")
    if delta.fire_res_delta > 0:
        gains.append(f"+{delta.fire_res_delta}% Fire Res")
    if delta.cold_res_delta > 0:
        gains.append(f"+{delta.cold_res_delta}% Cold Res")
    if delta.lightning_res_delta > 0:
        gains.append(f"+{delta.lightning_res_delta}% Lightning Res")
    if delta.chaos_res_delta > 0:
        gains.append(f"+{delta.chaos_res_delta}% Chaos Res")
    if delta.armour_delta > 0:
        gains.append(f"+{delta.armour_delta} Armour")
    if delta.evasion_delta > 0:
        gains.append(f"+{delta.evasion_delta} Evasion")
    if delta.es_delta > 0:
        gains.append(f"+{delta.es_delta} Energy Shield")
    if delta.ehp_delta > 0.05:
        gains.append(f"+{delta.ehp_delta:.2f} Total EHP")
    if delta.dps_delta > 0.05:
        gains.append(f"+{delta.dps_delta:.2f} DPS")

    # Compile Trade-offs / Losses
    if delta.life_delta < 0:
        trade_offs.append(f"{delta.life_delta} Life")
    if delta.fire_res_delta < 0:
        trade_offs.append(f"{delta.fire_res_delta}% Fire Res")
    if delta.cold_res_delta < 0:
        trade_offs.append(f"{delta.cold_res_delta}% Cold Res")
    if delta.lightning_res_delta < 0:
        trade_offs.append(f"{delta.lightning_res_delta}% Lightning Res")
    if delta.chaos_res_delta < 0:
        trade_offs.append(f"{delta.chaos_res_delta}% Chaos Res")
    if delta.armour_delta < 0:
        trade_offs.append(f"{delta.armour_delta} Armour")
    if delta.evasion_delta < 0:
        trade_offs.append(f"{delta.evasion_delta} Evasion")
    if delta.es_delta < 0:
        trade_offs.append(f"{delta.es_delta} Energy Shield")
    if delta.ehp_delta < -0.05:
        trade_offs.append(f"{delta.ehp_delta:.2f} Total EHP")

    # Evaluate DPS delta materiality
    # Minor negative DPS on campaign helmet typically stems from accuracy on replaced gear
    if delta.dps_delta < -0.05:
        trade_offs.append(
            f"{delta.dps_delta:.2f} DPS (Accuracy loss is non-material for campaign helmet)"
        )

    # Core Decision Logic
    elem_res_gain = max(0, delta.fire_res_delta) + max(0, delta.cold_res_delta) + max(0, delta.lightning_res_delta)
    elem_res_loss = min(0, delta.fire_res_delta) + min(0, delta.cold_res_delta) + min(0, delta.lightning_res_delta)

    has_primary_gain = delta.life_delta > 0 or elem_res_gain > 0
    has_primary_loss = delta.life_delta < 0 or elem_res_loss < 0

    if has_primary_gain and not has_primary_loss and (delta.ehp_delta >= -1.0):
        verdict = Verdict.EQUIP_NOW
        reason = (
            f"Fubgun {stage_name} — Resistance > Life (defensive upgrade takes precedence over minor accuracy DPS change)."
        )
    elif has_primary_gain and has_primary_loss:
        verdict = Verdict.CONDITIONAL_UPGRADE
        reason = (
            f"Fubgun {stage_name} — Trade-off between Life ({delta.life_delta:+d}) and Elemental Resistance ({elem_res_loss:+d}%). "
            f"Equip if needed to satisfy elemental resistance thresholds."
        )
    elif not has_primary_gain and (delta.ehp_delta > 5.0 or delta.armour_delta > 20):
        verdict = Verdict.CONDITIONAL_UPGRADE
        reason = f"Fubgun {stage_name} — Secondary local defense improvement; no primary Life or Resistance gains."
    else:
        verdict = Verdict.REJECT
        reason = f"Fubgun {stage_name} — No gain in primary helmet priorities (Resistance > Life). Keep current item."

    # Render formatted output in companion terminal style
    lines: list[str] = ["────────────────────────"]
    if verdict == Verdict.EQUIP_NOW:
        hdr = "🟢 EQUIP NOW"
        lines.append(f"\033[32m{hdr}\033[0m" if use_color else hdr)
    elif verdict == Verdict.REJECT:
        hdr = "🔴 REJECT / KEEP CURRENT"
        lines.append(f"\033[31m{hdr}\033[0m" if use_color else hdr)
    elif verdict == Verdict.CONDITIONAL_UPGRADE:
        hdr = "🟡 CONDITIONAL UPGRADE"
        lines.append(f"\033[33m{hdr}\033[0m" if use_color else hdr)
    else:
        lines.append(f"⚪ {verdict.value}")

    lines.append("")
    vs_name = delta.current_helmet_name or "Current Helmet"
    lines.append(f"{delta.candidate_name} (Helmet)")
    lines.append(f"vs {vs_name}")
    lines.append("")

    if verdict == Verdict.REJECT:
        if trade_offs:
            lines.append("Main losses:")
            for item in trade_offs:
                lines.append(item)
            lines.append("")
        lines.append("No useful stat gain.")
        lines.append("")
        lines.append(reason)
    else:
        for g in gains:
            lines.append(g)

        if trade_offs:
            lines.append("")
            lines.append("Trade-offs:")
            for t in trade_offs:
                lines.append(t)

        lines.append("")
        lines.append("Recommendation:")
        if verdict == Verdict.EQUIP_NOW:
            lines.append("Strong direct upgrade.")
        lines.append(reason)

    lines.append("────────────────────────")
    formatted_output = "\n".join(lines)

    return FubgunHelmetRecommendation(
        verdict=verdict,
        reason=reason,
        delta=delta,
        gains=gains,
        trade_offs=trade_offs,
        stage=stage,
        formatted_output=formatted_output,
    )


def evaluate_fubgun_equipment_policy(
    delta: Any,
    stage: BuildProgressionStage | None = None,
    use_color: bool | None = None,
) -> FubgunEquipmentRecommendation:
    """Apply the shared Fubgun defensive policy to a production-enabled core slot."""
    if delta.slot == "Helmet":
        return evaluate_fubgun_helmet_policy(delta, stage=stage, use_color=use_color)

    if use_color is None:
        use_color = _supports_color()

    slot = delta.slot
    stage_name = stage.value if stage else "campaign"
    gains: list[str] = []
    trade_offs: list[str] = []
    for value, label in (
        (delta.life_delta, " Life"),
        (delta.fire_res_delta, "% Fire Res"),
        (delta.cold_res_delta, "% Cold Res"),
        (delta.lightning_res_delta, "% Lightning Res"),
        (delta.chaos_res_delta, "% Chaos Res"),
        (delta.armour_delta, " Armour"),
        (delta.evasion_delta, " Evasion"),
        (delta.es_delta, " Energy Shield"),
    ):
        if value > 0:
            gains.append(f"+{value}{label}")
        elif value < 0:
            trade_offs.append(f"{value}{label}")
    if delta.movement_speed_delta > 0.05:
        gains.append(f"+{delta.movement_speed_delta:g}% Movement Speed")
    elif delta.movement_speed_delta < -0.05:
        trade_offs.append(f"{delta.movement_speed_delta:g}% Movement Speed")
    if delta.ehp_delta > 0.05:
        gains.append(f"+{delta.ehp_delta:.2f} Total EHP")
    elif delta.ehp_delta < -0.05:
        trade_offs.append(f"{delta.ehp_delta:.2f} Total EHP")
    if delta.dps_delta > 0.05:
        gains.append(f"+{delta.dps_delta:.2f} DPS")
    elif delta.dps_delta < -0.05:
        trade_offs.append(f"{delta.dps_delta:.2f} DPS")

    res_gain = sum(max(0, value) for value in (
        delta.fire_res_delta, delta.cold_res_delta, delta.lightning_res_delta
    ))
    res_loss = sum(min(0, value) for value in (
        delta.fire_res_delta, delta.cold_res_delta, delta.lightning_res_delta
    ))
    boots_movement_gain = slot == "Boots" and delta.movement_speed_delta > 0.05
    boots_movement_loss = slot == "Boots" and delta.movement_speed_delta < -0.05
    primary_gain = delta.life_delta > 0 or res_gain > 0 or boots_movement_gain
    primary_loss = delta.life_delta < 0 or res_loss < 0 or boots_movement_loss
    secondary_gain = delta.ehp_delta > 5.0 or delta.armour_delta > 20 or delta.evasion_delta > 20 or delta.es_delta > 20

    if primary_gain and not primary_loss and not boots_movement_loss and delta.ehp_delta >= -1.0:
        verdict = Verdict.EQUIP_NOW
        reason = f"Fubgun {stage_name} — {slot}: Life and Resistance upgrade; PoB2 confirms the defensive improvement."
    elif primary_gain and primary_loss:
        verdict = Verdict.CONDITIONAL_UPGRADE
        reason = f"Fubgun {stage_name} — {slot}: Life/Resistance trade-off; equip when it satisfies the current defensive need."
    elif secondary_gain:
        verdict = Verdict.CONDITIONAL_UPGRADE
        reason = f"Fubgun {stage_name} — {slot}: secondary local-defense improvement without a primary Life/Resistance gain."
    else:
        verdict = Verdict.REJECT
        reason = f"Fubgun {stage_name} — {slot}: no useful Life or Resistance gain. Keep current item."

    header = {
        Verdict.EQUIP_NOW: "🟢 EQUIP NOW",
        Verdict.REJECT: "🔴 REJECT / KEEP CURRENT",
        Verdict.CONDITIONAL_UPGRADE: "🟡 CONDITIONAL UPGRADE",
    }.get(verdict, f"⚪ {verdict.value}")
    if use_color and verdict in (Verdict.EQUIP_NOW, Verdict.REJECT, Verdict.CONDITIONAL_UPGRADE):
        color = {Verdict.EQUIP_NOW: 32, Verdict.REJECT: 31, Verdict.CONDITIONAL_UPGRADE: 33}[verdict]
        header = f"\033[{color}m{header}\033[0m"

    current = delta.current_item_name or f"Current {slot}"
    lines = ["────────────────────────", header, "", f"{delta.candidate_name} ({slot})", f"vs {current}", ""]
    if gains:
        lines.extend(gains)
    if trade_offs:
        lines.extend(["", "Trade-offs:", *trade_offs])
    lines.extend(["", "Recommendation:", reason, "────────────────────────"])
    return FubgunEquipmentRecommendation(
        verdict=verdict,
        reason=reason,
        delta=delta,
        gains=gains,
        trade_offs=trade_offs,
        stage=stage,
        formatted_output="\n".join(lines),
    )
