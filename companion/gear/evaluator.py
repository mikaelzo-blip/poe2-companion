"""Gear evaluation, staleness tracking, and target requirement comparison."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from pydantic import BaseModel, ConfigDict, Field

from companion.gear.schema import EquippedItem, ItemSlot
from companion.state.provenance import VerificationState


class ComparisonResult(BaseModel):
    """Result of comparing an equipped item against target build requirements."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: ItemSlot
    is_compliant: bool
    missing_requirements: list[str] = Field(default_factory=list)
    notes: str = ""


def evaluate_gear_staleness(
    item: EquippedItem,
    now: datetime | None = None,
    ttl_minutes: int = 60,
) -> VerificationState:
    """Evaluate whether an equipped item's observation has expired."""
    current_time = now or datetime.now(timezone.utc)
    try:
        obs_dt = datetime.fromisoformat(item.observed_at)
    except Exception:
        return VerificationState.UNKNOWN

    elapsed_seconds = (current_time - obs_dt).total_seconds()
    if elapsed_seconds > (ttl_minutes * 60):
        return VerificationState.STALE

    return item.verification


def _extract_mod_values(item: EquippedItem) -> dict[str, float]:
    """Map canonical keys to total numeric values from item mods."""
    values: dict[str, float] = {}

    for mod in item.implicit_mods + item.explicit_mods:
        raw = mod.raw_text.lower()
        if mod.key and mod.value is not None:
            values[mod.key] = values.get(mod.key, 0.0) + float(mod.value)
            continue

        # Pattern match common stat categories
        if "maximum life" in raw or "to life" in raw:
            m = re.search(r"\+?([0-9]+)", raw)
            if m:
                values["life"] = values.get("life", 0.0) + float(m.group(1))

        if "fire resistance" in raw or "fire res" in raw:
            m = re.search(r"([+-]?[0-9]+)%", raw)
            if m:
                values["fire_res"] = values.get("fire_res", 0.0) + float(m.group(1))

        if "cold resistance" in raw or "cold res" in raw:
            m = re.search(r"([+-]?[0-9]+)%", raw)
            if m:
                values["cold_res"] = values.get("cold_res", 0.0) + float(m.group(1))

        if "lightning resistance" in raw or "lightning res" in raw:
            m = re.search(r"([+-]?[0-9]+)%", raw)
            if m:
                values["lightning_res"] = values.get("lightning_res", 0.0) + float(m.group(1))

        if "chaos resistance" in raw or "chaos res" in raw:
            m = re.search(r"([+-]?[0-9]+)%", raw)
            if m:
                values["chaos_res"] = values.get("chaos_res", 0.0) + float(m.group(1))

    return values


def compare_equipped_against_target(
    item: EquippedItem,
    target_requirements: dict[str, float | int | str],
) -> ComparisonResult:
    """Compare equipped item attributes against target build criteria."""
    mod_values = _extract_mod_values(item)
    missing: list[str] = []

    for req_key, req_val in target_requirements.items():
        if isinstance(req_val, (int, float)):
            actual_val = mod_values.get(req_key, 0.0)
            if actual_val < req_val:
                missing.append(req_key)
        elif isinstance(req_val, str):
            if req_val.lower() not in item.base_type.lower():
                missing.append(req_key)

    is_compliant = len(missing) == 0
    notes = "Meets all target requirements." if is_compliant else f"Missing: {', '.join(missing)}"

    return ComparisonResult(
        slot=item.slot,
        is_compliant=is_compliant,
        missing_requirements=missing,
        notes=notes,
    )
