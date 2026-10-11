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
RES_CAP = 75

VERDICT_RANK = {"EQUIP_NOW": 3, "CONDITIONAL_UPGRADE": 2, "INSUFFICIENT_DATA": 1, "REJECT": 0}

# (field, label, unit suffix)
_FLAT_STATS = (
    ("life_delta", "Life", ""),
    ("armour_delta", "Armour", ""),
    ("evasion_delta", "Evasion", ""),
    ("es_delta", "Energy Shield", ""),
    ("fire_res_delta", "Fire Res", "%"),
    ("cold_res_delta", "Cold Res", "%"),
    ("lightning_res_delta", "Lightning Res", "%"),
    ("chaos_res_delta", "Chaos Res", "%"),
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
        if value:
            signed.append((value, f"{value:+g}{unit} {label}"))
    gains = [text for value, text in signed if value > 0]
    trade_offs = [text for value, text in signed if value < 0]
    trade_offs += [
        f"{key.capitalize()} Res turun di bawah cap ({before:g}% → {after:g}%)" for key, before, after in breached
    ]
    trade_offs += [f"Kebutuhan belum terpenuhi: {req}" for req in unmet_requirements]

    missing = list(priority.must_have_missing) if priority else []
    trade_offs += [f"Prioritas guide kurang: {line}" for line in missing]

    no_gain = dps_pct <= 0 and ehp_pct <= 0
    if unmet_requirements:
        verdict, reason = "REJECT", "Kebutuhan item belum terpenuhi."
    elif dps_pct <= DPS_DOWN and ehp_pct <= 0:
        verdict, reason = "REJECT", "DPS turun tanpa kompensasi EHP."
    elif breached and no_gain:
        verdict, reason = "REJECT", "Resist turun di bawah cap tanpa keuntungan."
    elif not breached and (
        (dps_pct >= DPS_UP and ehp_pct >= EHP_FLOOR) or (ehp_pct >= EHP_UP and dps_pct >= DPS_FLOOR)
    ):
        verdict, reason = "EQUIP_NOW", "Peningkatan melewati ambang tanpa trade-off besar."
    else:
        verdict, reason = "CONDITIONAL_UPGRADE", "Peningkatan di bawah ambang atau ada trade-off."
    if missing and verdict == "EQUIP_NOW":
        verdict, reason = "CONDITIONAL_UPGRADE", "Mod wajib dari guide belum ada."

    return SlotResult(
        slot=delta.slot, verdict=verdict, dps_pct=dps_pct, ehp_pct=ehp_pct, gains=gains,
        trade_offs=trade_offs, reasons=[reason], is_empty=is_empty, delta=delta,
    )


def insufficient(slot: str, reason: str) -> SlotResult:
    return SlotResult(slot=slot, verdict="INSUFFICIENT_DATA", reasons=[reason])


def rejected(slot: str, reasons: list[str]) -> SlotResult:
    return SlotResult(slot=slot, verdict="REJECT", reasons=list(reasons))
