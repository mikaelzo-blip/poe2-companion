"""Generic relative-threshold verdict policy over a PoB2 equipment delta."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from companion.builds.priorities import PrioritySignal
from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta

DPS_UP = 0.01
EHP_FLOOR = -0.01
EHP_UP = 0.02
DPS_FLOOR = -0.005
DPS_DOWN = -0.01
# a DPS drop beyond DPS_CRASH is only worth it for at least EHP_COMPENSATE more EHP
DPS_CRASH = -0.20
EHP_COMPENSATE = 0.05
RES_CAP = 75

VERDICT_RANK = {"EQUIP_NOW": 3, "CONDITIONAL_UPGRADE": 2, "INSUFFICIENT_DATA": 1, "REJECT": 0}

# (field, PoE2 stat name, unit suffix)
_FLAT_STATS = (
    ("life_delta", "maximum Life", ""),
    ("mana_delta", "maximum Mana", ""),
    ("es_delta", "maximum Energy Shield", ""),
    ("armour_delta", "Armour", ""),
    ("evasion_delta", "Evasion Rating", ""),
    ("fire_res_delta", "Fire Resistance", "%"),
    ("cold_res_delta", "Cold Resistance", "%"),
    ("lightning_res_delta", "Lightning Resistance", "%"),
    ("chaos_res_delta", "Chaos Resistance", "%"),
    ("crit_chance_delta", "Critical Hit Chance", "%"),
    ("crit_bonus_delta", "Critical Damage Bonus", "%"),
    ("average_hit_pct", "Average Hit", "%"),
    ("speed_pct", "Skill Speed (uses per second)", "%"),
    ("movement_speed_delta", "Movement Speed", "%"),
    ("strength_delta", "Strength", ""),
    ("dexterity_delta", "Dexterity", ""),
    ("intelligence_delta", "Intelligence", ""),
)


class SlotResult(BaseModel):
    slot: str
    verdict: str  # EQUIP_NOW | CONDITIONAL_UPGRADE | REJECT | INSUFFICIENT_DATA
    dps_pct: float = 0.0
    ehp_pct: float = 0.0
    gains: list[str] = []
    trade_offs: list[str] = []
    reasons: list[str] = []
    is_empty: bool = False
    delta: PobEquipmentDelta | None = None


def _pct(after: float, before: float) -> float:
    return (after - before) / max(before, 1)


def decide(
    delta: PobEquipmentDelta,
    *,
    unmet_requirements: Sequence[str] = (),
    priority: PrioritySignal | None = None,
    is_empty: bool = False,
) -> SlotResult:
    dps_pct = _pct(delta.dps_after, delta.dps_before)
    ehp_pct = _pct(delta.ehp_after, delta.ehp_before)
    breached = [
        (key, before, delta.res_after[key])
        for key, before in delta.res_before.items()
        if key in delta.res_after and before >= RES_CAP > delta.res_after[key]
    ]

    signed: list[tuple[float, str]] = []
    for pct, name in ((dps_pct, "DPS"), (ehp_pct, "EHP")):
        if round(pct, 3) != 0:  # a "+0.0%" line is noise
            signed.append((pct, f"{pct:+.1%} {name}"))
    for field, label, unit in _FLAT_STATS:
        value = getattr(delta, field)
        if round(value, 1):
            signed.append((value, f"{round(value, 1):+g}{unit} {label}"))
    gains = [text for value, text in signed if value > 0]
    trade_offs = [text for value, text in signed if value < 0]
    trade_offs += [
        f"{key.capitalize()} Resistance turun di bawah cap ({before:g}% → {after:g}%)" for key, before, after in breached
    ]
    trade_offs += [f"Kebutuhan belum terpenuhi: {req}" for req in unmet_requirements]

    missing = list(priority.must_have_missing) if priority else []
    trade_offs += [f"Prioritas guide kurang: {line}" for line in missing]

    no_gain = dps_pct <= 0 and ehp_pct <= 0
    if unmet_requirements:
        verdict, reason = "REJECT", "Kebutuhan item belum terpenuhi."
    elif dps_pct <= DPS_DOWN and ehp_pct <= 0:
        verdict, reason = "REJECT", "DPS turun tanpa kompensasi EHP."
    elif dps_pct < DPS_CRASH and ehp_pct < EHP_COMPENSATE:
        verdict, reason = "REJECT", "DPS turun lebih dari 20% dan kenaikan EHP di bawah 5%."
    elif breached and no_gain:
        verdict, reason = "REJECT", "Resist turun di bawah cap tanpa keuntungan."
    elif not breached and (
        (dps_pct >= DPS_UP and ehp_pct >= EHP_FLOOR) or (ehp_pct >= EHP_UP and dps_pct >= DPS_FLOOR)
    ):
        verdict, reason = "EQUIP_NOW", "Peningkatan melewati ambang tanpa trade-off besar."
    else:
        verdict, reason = "CONDITIONAL_UPGRADE", "Peningkatan di bawah ambang atau ada trade-off."
    reasons = [reason]
    if missing and verdict == "EQUIP_NOW":
        verdict = "CONDITIONAL_UPGRADE"
        reasons.insert(0, "Mod wajib dari guide belum ada.")

    return SlotResult(
        slot=delta.slot, verdict=verdict, dps_pct=dps_pct, ehp_pct=ehp_pct, gains=gains,
        trade_offs=trade_offs, reasons=reasons, is_empty=is_empty, delta=delta,
    )


def insufficient(slot: str, reason: str) -> SlotResult:
    return SlotResult(slot=slot, verdict="INSUFFICIENT_DATA", reasons=[reason])


def rejected(slot: str, reasons: list[str]) -> SlotResult:
    return SlotResult(slot=slot, verdict="REJECT", reasons=list(reasons))
