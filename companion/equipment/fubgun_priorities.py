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


def infer_stage_from_level(level: int) -> BuildProgressionStage:
    """Infer the canonical Fubgun progression stage from character level."""
    if level < 15:
        return BuildProgressionStage.LEVELING_1_14
    elif level < 33:
        return BuildProgressionStage.LEVELING_15_32
    elif level < 52:
        return BuildProgressionStage.LEVELING_33_51
    elif level == 52:
        return BuildProgressionStage.SWAP_52
    elif level <= 68:
        return BuildProgressionStage.LEVELING_53_68
    elif level <= 85:
        return BuildProgressionStage.LEVEL_85
    else:
        return BuildProgressionStage.ENDGAME
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
    r"stun\s+and\s+ailment\s+threshold|"
    r"stun\s+(and\s+)?block\s+recovery|block\s+recovery|stun\s+recovery|"
    r"thorns\s+damage|thorns\b|reflects?\s+.*damage"
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
        # Unless it is simply stun/ailment threshold, stun/block recovery, or throwaway thorns/reflect
        if not (
            "stun threshold" in clean
            or "ailment threshold" in clean
            or "accuracy" in clean
            or "block recovery" in clean
            or "stun recovery" in clean
            or "thorns" in clean
            or "reflect" in clean
        ):
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
    elem_res_gain = (
        max(0, delta.fire_res_delta)
        + max(0, delta.cold_res_delta)
        + max(0, delta.lightning_res_delta)
        + max(0, delta.chaos_res_delta)
    )
    elem_res_loss = (
        min(0, delta.fire_res_delta)
        + min(0, delta.cold_res_delta)
        + min(0, delta.lightning_res_delta)
        + min(0, delta.chaos_res_delta)
    )

    has_primary_gain = delta.life_delta > 0 or elem_res_gain > 0
    has_primary_loss = delta.life_delta < 0 or elem_res_loss < 0

    # Check for net downgrade: dropping EHP, Life, and defenses/DPS for minor resistance (< 15%)
    # or losing primary defense/EHP with no primary gain
    is_net_downgrade = (
        delta.ehp_delta < -1.0
        and (
            (
                delta.life_delta < 0
                and delta.dps_delta <= 0
                and (delta.armour_delta <= 0 and delta.evasion_delta <= 0 and delta.es_delta <= 0)
                and elem_res_gain < 15
            )
            or (
                not has_primary_gain
                and has_primary_loss
                and delta.ehp_delta < -1.0
            )
            or (
                elem_res_loss <= -10
                and delta.life_delta <= 0
                and delta.ehp_delta < -5.0
            )
        )
    )

    if has_primary_gain and not has_primary_loss:
        if delta.ehp_delta >= -10.0:
            verdict = Verdict.EQUIP_NOW
            reason = (
                f"Fubgun {stage_name} — Resistance > Life (defensive upgrade takes precedence over minor accuracy DPS change)."
            )
        else:
            verdict = Verdict.CONDITIONAL_UPGRADE
            reason = (
                f"Fubgun {stage_name} — Trade-off between primary stats and significant local defense loss ({delta.ehp_delta:.2f} Total EHP). "
                f"Equip if elemental resistance is urgently needed."
            )
    elif is_net_downgrade:
        verdict = Verdict.REJECT
        reason = (
            f"Fubgun {stage_name} — Helmet: Net downgrade ({delta.ehp_delta:+.2f} Total EHP, "
            f"{delta.life_delta:+d} Life, {delta.dps_delta:+.2f} DPS) for a minor resistance gain (+{elem_res_gain}%). "
            f"Keep current item."
        )
    elif (
        elem_res_loss <= -6
        and (delta.armour_delta <= -30 or delta.evasion_delta <= -30)
        and delta.life_delta <= 30
    ):
        verdict = Verdict.REJECT
        reason = (
            f"Fubgun {stage_name} — Helmet: Severe defensive compromise ({elem_res_loss:+d}% Resistance, "
            f"{delta.armour_delta:+d} Armour, {delta.evasion_delta:+d} Evasion) for a minor Life gain (+{delta.life_delta}). "
            f"Keep current item."
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
    if delta.slot in ("Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap"):
        return evaluate_fubgun_weapon_policy(delta, stage=stage, use_color=use_color)

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
        delta.fire_res_delta,
        delta.cold_res_delta,
        delta.lightning_res_delta,
        delta.chaos_res_delta,
    ))
    res_loss = sum(min(0, value) for value in (
        delta.fire_res_delta,
        delta.cold_res_delta,
        delta.lightning_res_delta,
        delta.chaos_res_delta,
    ))
    boots_movement_gain = slot == "Boots" and delta.movement_speed_delta > 0.05
    boots_movement_loss = slot == "Boots" and delta.movement_speed_delta < -0.05
    primary_gain = delta.life_delta > 0 or res_gain > 0 or boots_movement_gain
    primary_loss = delta.life_delta < 0 or res_loss < 0 or boots_movement_loss
    secondary_gain = delta.ehp_delta > 5.0 or delta.armour_delta > 20 or delta.evasion_delta > 20 or delta.es_delta > 20

    current = delta.current_item_name or f"Current {slot}"
    is_offensive_slot = slot in ("Gloves", "Ring", "Ring 1", "Ring 2", "Amulet")

    if primary_gain and not primary_loss and not boots_movement_loss:
        material_dps_loss = (delta.dps_delta <= -5.0) or (
            is_offensive_slot and delta.dps_delta <= -2.0
        )
        if material_dps_loss:
            if delta.life_delta >= 40 and delta.ehp_delta >= 40:
                verdict = Verdict.EQUIP_NOW
                reason = f"Fubgun {stage_name} — {slot}: Peningkatan Life/EHP masif (+{delta.life_delta} Life, {delta.ehp_delta:+.1f} EHP); jauh lebih unggul dibandingkan trade-off ofensif ({delta.dps_delta:.2f} DPS)."
            else:
                verdict = Verdict.CONDITIONAL_UPGRADE
                reason = f"Fubgun {stage_name} — {slot}: Trade-off between Life/Resistance upgrade and offensive damage loss ({delta.dps_delta:.2f} DPS). Equip if defensive need matches."
        elif delta.ehp_delta >= -10.0:
            verdict = Verdict.EQUIP_NOW
            reason = f"Fubgun {stage_name} — {slot}: Life and Resistance upgrade; PoB2 confirms the defensive improvement."
        else:
            verdict = Verdict.CONDITIONAL_UPGRADE
            reason = f"Fubgun {stage_name} — {slot}: Trade-off between primary stats and significant local defense loss ({delta.ehp_delta:.2f} Total EHP). Equip if defensive need matches."
    elif (
        delta.ehp_delta < -1.0
        and (
            (
                delta.life_delta < 0
                and delta.dps_delta <= 0
                and (delta.armour_delta <= 0 and delta.evasion_delta <= 0 and delta.es_delta <= 0)
                and res_gain < 15
            )
            or (
                not primary_gain
                and primary_loss
                and delta.ehp_delta < -1.0
            )
            or (
                res_loss <= -10
                and delta.life_delta <= 0
                and delta.ehp_delta < -5.0
            )
        )
    ):
        verdict = Verdict.REJECT
        reason = (
            f"Fubgun {stage_name} — {slot}: Net downgrade ({delta.ehp_delta:+.2f} Total EHP, "
            f"{delta.life_delta:+d} Life, {res_loss:+d}% Resistance). "
            f"Local defense gain does not compensate for lost Life and Resistances. Keep current item."
        )
    elif (
        res_loss <= -6
        and (delta.armour_delta <= -30 or delta.evasion_delta <= -30 or delta.es_delta <= -30)
        and delta.life_delta <= 30
    ):
        verdict = Verdict.REJECT
        reason = (
            f"Fubgun {stage_name} — {slot}: Severe defensive compromise ({res_loss:+d}% Resistance, "
            f"local defense loss) for an inadequate Life gain (+{delta.life_delta}). "
            f"Keep current item."
        )
    elif is_offensive_slot and delta.dps_delta < -0.5 and delta.life_delta < 0:
        verdict = Verdict.REJECT
        reason = (
            f"Fubgun {stage_name} — {slot}: {current} LEBIH BAGUS! Net downgrade "
            f"({delta.dps_delta:+.2f} DPS, {delta.life_delta:+d} Life). Di build Fubgun, "
            f"slot {slot} adalah sumber flat attack damage dan sustain utama selama leveling. "
            f"Keep current item."
        )
    elif is_offensive_slot and delta.dps_delta <= -2.0 and delta.life_delta <= 0 and res_gain < 35:
        verdict = Verdict.REJECT
        reason = (
            f"Fubgun {stage_name} — {slot}: {current} LEBIH BAGUS! Menolak {delta.candidate_name} "
            f"karena kehilangan flat attack damage ({delta.dps_delta:+.2f} DPS). Keep current item."
        )
    elif (
        delta.dps_delta < -0.05
        and delta.life_delta <= 0
        and res_gain <= 0
    ):
        verdict = Verdict.REJECT
        reason = (
            f"Fubgun {stage_name} — {slot}: Net downgrade ({delta.dps_delta:+.2f} DPS, "
            f"{delta.life_delta:+d} Life) with no resistance gain. "
            f"Minor local defense cannot compensate. Keep current item."
        )
    elif not primary_gain and primary_loss:
        verdict = Verdict.REJECT
        loss_details: list[str] = []
        if delta.life_delta < 0:
            loss_details.append(f"{delta.life_delta:+d} Life")
        if res_loss < 0:
            loss_details.append(f"{res_loss:+d}% Resistance")
        if boots_movement_loss:
            loss_details.append(f"{delta.movement_speed_delta:g}% Movement Speed")
        if not loss_details:
            loss_details.append(f"{delta.life_delta:+d} Life, {res_loss:+d}% Resistance")
        reason = (
            f"Fubgun {stage_name} — {slot}: Net loss of primary stats ({', '.join(loss_details)}). Keep current item."
        )
    elif (
        primary_gain
        and primary_loss
        and delta.life_delta >= 0
        and (res_gain + res_loss) >= 0
        and res_loss >= -10
        and (delta.armour_delta + delta.evasion_delta + delta.es_delta) >= 20
        and not boots_movement_loss
    ):
        verdict = Verdict.EQUIP_NOW
        reason = (
            f"Fubgun {stage_name} — {slot}: Clear defensive upgrade (+{delta.life_delta} Life, "
            f"+{delta.armour_delta + delta.evasion_delta + delta.es_delta} local defense, "
            f"net resistance {res_gain + res_loss:+d}%). Minor resistance shift is well compensated."
        )
    elif primary_gain and primary_loss:
        verdict = Verdict.CONDITIONAL_UPGRADE
        if boots_movement_loss and delta.life_delta >= 0 and res_loss == 0:
            reason = f"Fubgun {stage_name} — {slot}: Trade-off between Life/Resistance upgrade and Movement Speed loss ({delta.movement_speed_delta:g}% Movement Speed); equip when it satisfies the current defensive need."
        else:
            reason = f"Fubgun {stage_name} — {slot}: Life/Resistance trade-off; equip when it satisfies the current defensive need."
    elif secondary_gain and not primary_loss:
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


class DualRingRecommendation(BaseModel):
    """Stacked dual-slot recommendation for Ring 1 vs Ring 2."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    ring1_recommendation: FubgunEquipmentRecommendation
    ring2_recommendation: FubgunEquipmentRecommendation
    recommended_slot: str | None = None  # "Ring 1", "Ring 2", or None
    summary_verdict: str = ""
    trade_off_notes: list[str] = Field(default_factory=list)
    formatted_output: str = ""


def evaluate_dual_ring_policy(
    delta1: Any,
    delta2: Any,
    stage: BuildProgressionStage | None = None,
    empty_ring1: bool = False,
    empty_ring2: bool = False,
    use_color: bool | None = None,
    empty_slot1: bool | None = None,
    empty_slot2: bool | None = None,
) -> DualRingRecommendation:
    """Evaluate dual ring placements against canonical Fubgun policy and formatting.

    Adheres strictly to:
    1. Independent policy evaluation for each slot placement.
    2. No arbitrary numeric weighted score.
    3. Recommends slot only when one placement is clearly preferred by policy or dominance.
    4. When both placements are viable but trade different stats, outputs:
       'Both placements viable / No safe automatic slot preference' with trade-off details.
    5. Compact stacked UI format.
    """
    if empty_slot1 is not None:
        empty_ring1 = empty_ring1 or empty_slot1
    if empty_slot2 is not None:
        empty_ring2 = empty_ring2 or empty_slot2

    if use_color is None:
        use_color = _supports_color()

    if delta1 is None or delta2 is None:
        raise ValueError("Both ring deltas are required for dual ring policy evaluation")

    rec1 = evaluate_fubgun_equipment_policy(delta1, stage=stage, use_color=use_color)
    rec2 = evaluate_fubgun_equipment_policy(delta2, stage=stage, use_color=use_color)

    recommended_slot: str | None = None
    summary_verdict: str = ""
    trade_off_notes: list[str] = []

    # Case 1: Empty slot presence. Never replace an equipped ring when the empty
    # placement is at least conditionally viable.
    if empty_ring2 and not empty_ring1:
        if rec2.verdict in (Verdict.EQUIP_NOW, Verdict.CONDITIONAL_UPGRADE):
            recommended_slot = "Ring 2"
            summary_verdict = "Recommended placement: Ring 2 (slot is empty)"
        else:
            recommended_slot = None
            summary_verdict = "Neither placement recommended (keep current rings)"
    elif empty_ring1 and not empty_ring2:
        if rec1.verdict in (Verdict.EQUIP_NOW, Verdict.CONDITIONAL_UPGRADE):
            recommended_slot = "Ring 1"
            summary_verdict = "Recommended placement: Ring 1 (slot is empty)"
        else:
            recommended_slot = None
            summary_verdict = "Neither placement recommended (keep current rings)"

    # Case 2: One placement is EQUIP_NOW and other is REJECT or CONDITIONAL.
    # If the only empty placement was rejected, do not fall through to replacing
    # the equipped ring.
    has_single_empty_ring = empty_ring1 != empty_ring2
    if recommended_slot is None and not has_single_empty_ring:
        if rec1.verdict == Verdict.EQUIP_NOW and rec2.verdict == Verdict.REJECT:
            recommended_slot = "Ring 1"
            summary_verdict = "Recommended placement: Ring 1 (direct upgrade; replacing Ring 2 is a regression)"
        elif rec2.verdict == Verdict.EQUIP_NOW and rec1.verdict == Verdict.REJECT:
            recommended_slot = "Ring 2"
            summary_verdict = "Recommended placement: Ring 2 (direct upgrade; replacing Ring 1 is a regression)"
        elif rec1.verdict == Verdict.EQUIP_NOW and rec2.verdict == Verdict.CONDITIONAL_UPGRADE:
            recommended_slot = "Ring 1"
            summary_verdict = "Recommended placement: Ring 1 (unconditional upgrade; Ring 2 incurs trade-offs)"
        elif rec2.verdict == Verdict.EQUIP_NOW and rec1.verdict == Verdict.CONDITIONAL_UPGRADE:
            recommended_slot = "Ring 2"
            summary_verdict = "Recommended placement: Ring 2 (unconditional upgrade; Ring 1 incurs trade-offs)"
        elif rec1.verdict == Verdict.CONDITIONAL_UPGRADE and rec2.verdict == Verdict.REJECT:
            recommended_slot = "Ring 1"
            summary_verdict = "Recommended placement: Ring 1 (conditional upgrade; replacing Ring 2 is a regression)"
        elif rec2.verdict == Verdict.CONDITIONAL_UPGRADE and rec1.verdict == Verdict.REJECT:
            recommended_slot = "Ring 2"
            summary_verdict = "Recommended placement: Ring 2 (conditional upgrade; replacing Ring 1 is a regression)"

    # Case 3: Both are REJECT
    if recommended_slot is None and rec1.verdict == Verdict.REJECT and rec2.verdict == Verdict.REJECT:
        recommended_slot = None
        summary_verdict = "Neither placement recommended (keep current rings)"

    # Case 4: Both are EQUIP_NOW or both are CONDITIONAL_UPGRADE -> Test Pareto Dominance
    if (
        recommended_slot is None
        and not has_single_empty_ring
        and rec1.verdict in (Verdict.EQUIP_NOW, Verdict.CONDITIONAL_UPGRADE)
        and rec2.verdict in (Verdict.EQUIP_NOW, Verdict.CONDITIONAL_UPGRADE)
    ):
        d1_gains_over_d2 = (
            delta1.life_delta >= delta2.life_delta
            and delta1.fire_res_delta >= delta2.fire_res_delta
            and delta1.cold_res_delta >= delta2.cold_res_delta
            and delta1.lightning_res_delta >= delta2.lightning_res_delta
            and delta1.chaos_res_delta >= delta2.chaos_res_delta
            and delta1.ehp_delta >= delta2.ehp_delta
            and delta1.dps_delta >= delta2.dps_delta
        )
        d1_strictly_greater = (
            delta1.life_delta > delta2.life_delta
            or delta1.fire_res_delta > delta2.fire_res_delta
            or delta1.cold_res_delta > delta2.cold_res_delta
            or delta1.lightning_res_delta > delta2.lightning_res_delta
            or delta1.chaos_res_delta > delta2.chaos_res_delta
            or delta1.ehp_delta > (delta2.ehp_delta + 1.0)
            or delta1.dps_delta > (delta2.dps_delta + 0.5)
        )
        d2_gains_over_d1 = (
            delta2.life_delta >= delta1.life_delta
            and delta2.fire_res_delta >= delta1.fire_res_delta
            and delta2.cold_res_delta >= delta1.cold_res_delta
            and delta2.lightning_res_delta >= delta1.lightning_res_delta
            and delta2.chaos_res_delta >= delta1.chaos_res_delta
            and delta2.ehp_delta >= delta1.ehp_delta
            and delta2.dps_delta >= delta1.dps_delta
        )
        d2_strictly_greater = (
            delta2.life_delta > delta1.life_delta
            or delta2.fire_res_delta > delta1.fire_res_delta
            or delta2.cold_res_delta > delta1.cold_res_delta
            or delta2.lightning_res_delta > delta1.lightning_res_delta
            or delta2.chaos_res_delta > delta1.chaos_res_delta
            or delta2.ehp_delta > (delta1.ehp_delta + 1.0)
            or delta2.dps_delta > (delta1.dps_delta + 0.5)
        )

        if d1_gains_over_d2 and d1_strictly_greater and not (d2_gains_over_d1 and d2_strictly_greater):
            recommended_slot = "Ring 1"
            summary_verdict = "Recommended placement: Ring 1 (higher Life and Resistance gains)"
        elif d2_gains_over_d1 and d2_strictly_greater and not (d1_gains_over_d2 and d1_strictly_greater):
            recommended_slot = "Ring 2"
            summary_verdict = "Recommended placement: Ring 2 (higher Life and Resistance gains)"
        else:
            # Neither dominates: Material trade-offs!
            recommended_slot = None
            summary_verdict = "Both placements viable / No safe automatic slot preference"
            trade_off_notes.append(
                f"Replacing Ring 1: {delta1.life_delta:+d} Life, "
                f"Res (F:{delta1.fire_res_delta:+d}% C:{delta1.cold_res_delta:+d}% L:{delta1.lightning_res_delta:+d}%)."
            )
            trade_off_notes.append(
                f"Replacing Ring 2: {delta2.life_delta:+d} Life, "
                f"Res (F:{delta2.fire_res_delta:+d}% C:{delta2.cold_res_delta:+d}% L:{delta2.lightning_res_delta:+d}%)."
            )

    # Format the UI sections
    current_1 = "EMPTY" if empty_ring1 else (delta1.current_item_name or "Current Ring 1")
    current_2 = "EMPTY" if empty_ring2 else (delta2.current_item_name or "Current Ring 2")

    header_1 = {
        Verdict.EQUIP_NOW: "🟢 EQUIP NOW",
        Verdict.REJECT: "🔴 REJECT / KEEP CURRENT",
        Verdict.CONDITIONAL_UPGRADE: "🟡 CONDITIONAL UPGRADE",
    }.get(rec1.verdict, f"⚪ {rec1.verdict.value}")
    if use_color and rec1.verdict in (Verdict.EQUIP_NOW, Verdict.REJECT, Verdict.CONDITIONAL_UPGRADE):
        c1 = {Verdict.EQUIP_NOW: 32, Verdict.REJECT: 31, Verdict.CONDITIONAL_UPGRADE: 33}[rec1.verdict]
        header_1 = f"\033[{c1}m{header_1}\033[0m"

    header_2 = {
        Verdict.EQUIP_NOW: "🟢 EQUIP NOW",
        Verdict.REJECT: "🔴 REJECT / KEEP CURRENT",
        Verdict.CONDITIONAL_UPGRADE: "🟡 CONDITIONAL UPGRADE",
    }.get(rec2.verdict, f"⚪ {rec2.verdict.value}")
    if use_color and rec2.verdict in (Verdict.EQUIP_NOW, Verdict.REJECT, Verdict.CONDITIONAL_UPGRADE):
        c2 = {Verdict.EQUIP_NOW: 32, Verdict.REJECT: 31, Verdict.CONDITIONAL_UPGRADE: 33}[rec2.verdict]
        header_2 = f"\033[{c2}m{header_2}\033[0m"

    lines: list[str] = [
        "────────────────────────",
        f"Vs Ring 1: {current_1}",
        header_1,
    ]
    if rec1.gains:
        lines.extend(rec1.gains)
    if rec1.trade_offs:
        lines.extend(["", "Trade-offs:", *rec1.trade_offs])

    lines.extend([
        "",
        f"Vs Ring 2: {current_2}",
        header_2,
    ])
    if rec2.gains:
        lines.extend(rec2.gains)
    if rec2.trade_offs:
        lines.extend(["", "Trade-offs:", *rec2.trade_offs])

    lines.extend([
        "",
        "────────────────────────",
        "Summary:",
        summary_verdict,
    ])
    if trade_off_notes:
        lines.extend(trade_off_notes)
    lines.append("────────────────────────")

    formatted_output = "\n".join(lines)
    return DualRingRecommendation(
        ring1_recommendation=rec1,
        ring2_recommendation=rec2,
        recommended_slot=recommended_slot,
        summary_verdict=summary_verdict,
        trade_off_notes=trade_off_notes,
        formatted_output=formatted_output,
    )


def evaluate_fubgun_weapon_policy(
    delta: Any,
    skill_context: str | None = None,
    stage: BuildProgressionStage | None = None,
    use_color: bool | None = None,
) -> FubgunEquipmentRecommendation:
    """Apply the Fubgun weapon policy (offensive scaling & defensive baseline)."""
    if use_color is None:
        use_color = _supports_color()

    slot = delta.slot
    stage_name = stage.value if stage else "campaign"
    skill_str = f" [{skill_context}]" if skill_context else ""

    gains: list[str] = []
    trade_offs: list[str] = []

    if delta.dps_delta > 0.05:
        gains.append(f"+{delta.dps_delta:.2f} DPS")
    elif delta.dps_delta < -0.05:
        trade_offs.append(f"{delta.dps_delta:.2f} DPS")

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

    res_loss = sum(min(0, value) for value in (
        delta.fire_res_delta,
        delta.cold_res_delta,
        delta.lightning_res_delta,
        delta.chaos_res_delta,
    ))
    local_defense_loss = (
        delta.ehp_delta < -5.0
        or delta.armour_delta < -20
        or delta.evasion_delta < -20
        or delta.es_delta < -20
    )
    defensive_loss = delta.life_delta < 0 or res_loss < 0 or local_defense_loss
    dps_gain = delta.dps_delta > 0.05
    dps_loss = delta.dps_delta < -0.05

    # Campaign / Leveling weapon rule:
    # In Fubgun campaign leveling, weapons are the primary damage engine.
    # An outstanding DPS boost (dps_delta >= 5.0) with zero resistance loss (res_loss == 0)
    # and only minor incidental attribute-driven life loss (life_delta >= -25) without
    # shield/defense collapse is an undeniable EQUIP_NOW.
    is_pre_swap = stage.is_pre_swap if stage else True
    is_shield_collapse = (
        delta.ehp_delta < -50.0
        or delta.armour_delta < -100
        or delta.evasion_delta < -100
        or delta.es_delta < -100
    )
    is_decisive_weapon_upgrade = (
        is_pre_swap
        and delta.dps_delta >= 5.0
        and res_loss == 0
        and delta.life_delta >= -25
        and not is_shield_collapse
    )

    if is_decisive_weapon_upgrade:
        verdict = Verdict.EQUIP_NOW
        reason = (
            f"Fubgun {stage_name} — {slot}{skill_str}: {delta.candidate_name} LEBIH BAGUS! "
            f"DPS upgrade lonjakan damage besar ({delta.dps_delta:+.2f} DPS). Di build Fubgun, senjata adalah motor utama "
            f"damage ledakan granat dan kehilangan minor darah ({delta.life_delta:+d} Life) dari atribut lama "
            f"tidak sebanding dengan lonjakan ofensif ini. Pasang sekarang!"
        )
    elif dps_gain and not defensive_loss:
        verdict = Verdict.EQUIP_NOW
        reason = f"Fubgun {stage_name} — {slot}{skill_str}: {delta.candidate_name} LEBIH BAGUS! DPS upgrade without defensive trade-offs; PoB2 confirms the improvement."
    elif dps_gain and defensive_loss:
        verdict = Verdict.CONDITIONAL_UPGRADE
        reason = f"Fubgun {stage_name} — {slot}{skill_str}: DPS upgrade with defensive loss ({trade_offs[0] if trade_offs else 'defenses'}); equip if offense outweighs defense."
    elif not dps_loss and (delta.life_delta > 0 or delta.ehp_delta > 5.0):
        verdict = Verdict.CONDITIONAL_UPGRADE
        reason = f"Fubgun {stage_name} — {slot}{skill_str}: defensive utility gain without DPS loss."
    else:
        verdict = Verdict.REJECT
        reason = f"Fubgun {stage_name} — {slot}{skill_str}: no DPS upgrade. Keep current weapon."

    header = {
        Verdict.EQUIP_NOW: "🟢 EQUIP NOW",
        Verdict.REJECT: "🔴 REJECT / KEEP CURRENT",
        Verdict.CONDITIONAL_UPGRADE: "🟡 CONDITIONAL UPGRADE",
    }.get(verdict, f"⚪ {verdict.value}")
    if use_color and verdict in (Verdict.EQUIP_NOW, Verdict.REJECT, Verdict.CONDITIONAL_UPGRADE):
        color = {Verdict.EQUIP_NOW: 32, Verdict.REJECT: 31, Verdict.CONDITIONAL_UPGRADE: 33}[verdict]
        header = f"\033[{color}m{header}\033[0m"

    current = delta.current_item_name or f"Current {slot}"
    lines = [
        "────────────────────────",
        header,
        "",
        f"{delta.candidate_name} ({slot}{skill_str})",
        f"vs {current}",
        "",
    ]
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


class DualWeaponRecommendation(BaseModel):
    """Stacked dual-slot recommendation for ambiguous 1H weapon placement."""

    model_config = ConfigDict(frozen=True)

    slot1_recommendation: FubgunEquipmentRecommendation
    slot2_recommendation: FubgunEquipmentRecommendation
    recommended_slot: str | None = None
    summary_verdict: str
    trade_off_notes: list[str] = Field(default_factory=list)
    formatted_output: str


def evaluate_dual_weapon_policy(
    delta1: Any,
    delta2: Any,
    stage: BuildProgressionStage | None = None,
    use_color: bool | None = None,
    empty_slot1: bool = False,
    empty_slot2: bool = False,
) -> DualWeaponRecommendation:
    """Evaluate dual weapon placements against canonical Fubgun policy and formatting."""
    if delta1 is None or delta2 is None:
        raise ValueError("Both weapon deltas are required for dual weapon policy evaluation")

    rec1 = evaluate_fubgun_weapon_policy(delta1, stage=stage, use_color=use_color)
    rec2 = evaluate_fubgun_weapon_policy(delta2, stage=stage, use_color=use_color)

    slot1_name = delta1.slot
    slot2_name = delta2.slot

    trade_off_notes: list[str] = []
    if empty_slot2 and not empty_slot1:
        if rec2.verdict in (Verdict.EQUIP_NOW, Verdict.CONDITIONAL_UPGRADE):
            recommended_slot = slot2_name
            summary_verdict = f"Recommended placement: {slot2_name} (slot is empty)"
        else:
            recommended_slot = None
            summary_verdict = "Neither placement recommended (keep current weapons)"
    elif empty_slot1 and not empty_slot2:
        if rec1.verdict in (Verdict.EQUIP_NOW, Verdict.CONDITIONAL_UPGRADE):
            recommended_slot = slot1_name
            summary_verdict = f"Recommended placement: {slot1_name} (slot is empty)"
        else:
            recommended_slot = None
            summary_verdict = "Neither placement recommended (keep current weapons)"
    elif rec1.verdict == Verdict.EQUIP_NOW and rec2.verdict != Verdict.EQUIP_NOW:
        recommended_slot = slot1_name
        summary_verdict = f"Recommended placement: {slot1_name} (direct upgrade; replacing {slot2_name} is a regression)"
    elif rec2.verdict == Verdict.EQUIP_NOW and rec1.verdict != Verdict.EQUIP_NOW:
        recommended_slot = slot2_name
        summary_verdict = f"Recommended placement: {slot2_name} (direct upgrade; replacing {slot1_name} is a regression)"
    elif rec1.verdict == Verdict.EQUIP_NOW and rec2.verdict == Verdict.EQUIP_NOW:
        if delta1.dps_delta > delta2.dps_delta:
            recommended_slot = slot1_name
            summary_verdict = f"Recommended placement: {slot1_name} (higher DPS gain)"
        elif delta2.dps_delta > delta1.dps_delta:
            recommended_slot = slot2_name
            summary_verdict = f"Recommended placement: {slot2_name} (higher DPS gain)"
        else:
            recommended_slot = slot1_name
            summary_verdict = f"Both placements are valid upgrades ({slot1_name} or {slot2_name})"
    else:
        recommended_slot = None
        summary_verdict = "Neither placement recommended (keep current weapons)"

    header_1 = {
        Verdict.EQUIP_NOW: "🟢 EQUIP NOW",
        Verdict.REJECT: "🔴 REJECT / KEEP CURRENT",
        Verdict.CONDITIONAL_UPGRADE: "🟡 CONDITIONAL UPGRADE",
    }.get(rec1.verdict, f"⚪ {rec1.verdict.value}")

    header_2 = {
        Verdict.EQUIP_NOW: "🟢 EQUIP NOW",
        Verdict.REJECT: "🔴 REJECT / KEEP CURRENT",
        Verdict.CONDITIONAL_UPGRADE: "🟡 CONDITIONAL UPGRADE",
    }.get(rec2.verdict, f"⚪ {rec2.verdict.value}")

    current_1 = "EMPTY" if empty_slot1 else (delta1.current_item_name or f"Current {slot1_name}")
    current_2 = "EMPTY" if empty_slot2 else (delta2.current_item_name or f"Current {slot2_name}")

    lines = [
        "────────────────────────",
        f"Ambiguous 1H Weapon Evaluation: {delta1.candidate_name}",
        "",
        f"Vs {slot1_name}: {current_1}",
        header_1,
    ]
    if rec1.gains:
        lines.extend(rec1.gains)
    if rec1.trade_offs:
        lines.extend(["", "Trade-offs:", *rec1.trade_offs])

    lines.extend([
        "",
        f"Vs {slot2_name}: {current_2}",
        header_2,
    ])
    if rec2.gains:
        lines.extend(rec2.gains)
    if rec2.trade_offs:
        lines.extend(["", "Trade-offs:", *rec2.trade_offs])

    lines.extend([
        "",
        "────────────────────────",
        "Summary:",
        summary_verdict,
    ])
    lines.append("────────────────────────")

    formatted_output = "\n".join(lines)
    return DualWeaponRecommendation(
        slot1_recommendation=rec1,
        slot2_recommendation=rec2,
        recommended_slot=recommended_slot,
        summary_verdict=summary_verdict,
        trade_off_notes=trade_off_notes,
        formatted_output=formatted_output,
    )
