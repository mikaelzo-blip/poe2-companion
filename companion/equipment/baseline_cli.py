"""CLI handlers and storage operations for CharacterStatBaseline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from companion.state.provenance import VerificationState
from companion.state.store import atomic_write_file
from companion.equipment.baseline import (
    BaselineSource,
    CharacterFact,
    CharacterStatBaseline,
)
from companion.equipment.loadout_cli import load_loadout


def get_baseline_file(runtime_dir: str | Path, character_id: str) -> Path:
    p = Path(runtime_dir).resolve() / "baselines" / f"{character_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_baseline(runtime_dir: str | Path, character_id: str) -> CharacterStatBaseline | None:
    target = get_baseline_file(runtime_dir, character_id)
    if target.exists():
        try:
            return CharacterStatBaseline.model_validate_json(target.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_baseline(runtime_dir: str | Path, baseline: CharacterStatBaseline) -> Path:
    target = get_baseline_file(runtime_dir, baseline.character_id)
    raw_bytes = (baseline.model_dump_json(indent=2) + "\n").encode("utf-8")
    atomic_write_file(target, raw_bytes)
    return target


def run_baseline_set(
    runtime_dir: str | Path,
    character_id: str,
    life: int | None = None,
    armour: int | None = None,
    evasion: int | None = None,
    energy_shield: int | None = None,
    fire_res: int | None = None,
    fire_raw: int | None = None,
    max_fire_res: int | None = None,
    cold_res: int | None = None,
    cold_raw: int | None = None,
    max_cold_res: int | None = None,
    lightning_res: int | None = None,
    lightning_raw: int | None = None,
    max_lightning_res: int | None = None,
    chaos_res: int | None = None,
    chaos_raw: int | None = None,
    max_chaos_res: int | None = None,
    strength: int | None = None,
    dexterity: int | None = None,
    intelligence: int | None = None,
    movement_speed: int | None = None,
    **kwargs: Any,
) -> CharacterStatBaseline:
    strength = strength if strength is not None else kwargs.get("str")
    dexterity = dexterity if dexterity is not None else kwargs.get("dex")
    intelligence = intelligence if intelligence is not None else kwargs.get("int")
    movement_speed = movement_speed if movement_speed is not None else kwargs.get("ms")

    loadout = load_loadout(runtime_dir, character_id)
    anchored_rev = loadout.revision if loadout.is_finalized else 1
    anchored_fp = loadout.compute_fingerprint() if loadout.is_finalized else None

    baseline = CharacterStatBaseline.create_partial(
        baseline_id=f"base_{character_id}",
        character_id=character_id,
        anchored_loadout_revision=anchored_rev,
        anchored_loadout_fingerprint=anchored_fp,
        source=BaselineSource.MANUAL_USER_INPUT,
        verification=VerificationState.VERIFIED,
        life=life,
        armour=armour,
        evasion=evasion,
        energy_shield=energy_shield,
        fire_res=fire_res,
        fire_raw=fire_raw,
        max_fire_res=max_fire_res,
        cold_res=cold_res,
        cold_raw=cold_raw,
        max_cold_res=max_cold_res,
        lightning_res=lightning_res,
        lightning_raw=lightning_raw,
        max_lightning_res=max_lightning_res,
        chaos_res=chaos_res,
        chaos_raw=chaos_raw,
        max_chaos_res=max_chaos_res,
        strength=strength,
        dexterity=dexterity,
        intelligence=intelligence,
        movement_speed=movement_speed,
    )
    save_baseline(runtime_dir, baseline)
    return baseline


def run_baseline_refresh(
    runtime_dir: str | Path,
    character_id: str,
    life: int | None = None,
    armour: int | None = None,
    evasion: int | None = None,
    energy_shield: int | None = None,
    fire_res: int | None = None,
    fire_raw: int | None = None,
    max_fire_res: int | None = None,
    cold_res: int | None = None,
    cold_raw: int | None = None,
    max_cold_res: int | None = None,
    lightning_res: int | None = None,
    lightning_raw: int | None = None,
    max_lightning_res: int | None = None,
    chaos_res: int | None = None,
    chaos_raw: int | None = None,
    max_chaos_res: int | None = None,
    strength: int | None = None,
    dexterity: int | None = None,
    intelligence: int | None = None,
    movement_speed: int | None = None,
    **kwargs: Any,
) -> CharacterStatBaseline:
    """Refresh baseline anchoring directly to current loadout revision."""
    strength = strength if strength is not None else kwargs.get("str")
    dexterity = dexterity if dexterity is not None else kwargs.get("dex")
    intelligence = intelligence if intelligence is not None else kwargs.get("int")
    movement_speed = movement_speed if movement_speed is not None else kwargs.get("ms")

    existing = load_baseline(runtime_dir, character_id)

    # Use existing values if not overridden
    def pick_stat(new_v: int | None, fact: CharacterFact[int] | None) -> int | None:
        if new_v is not None:
            return new_v
        if fact and fact.is_known:
            return fact.value
        return None

    return run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=character_id,
        life=pick_stat(life, existing.life if existing else None),
        armour=pick_stat(armour, existing.armour if existing else None),
        evasion=pick_stat(evasion, existing.evasion if existing else None),
        energy_shield=pick_stat(energy_shield, existing.energy_shield if existing else None),
        fire_res=pick_stat(fire_res, existing.effective_fire_res if existing else None),
        fire_raw=pick_stat(fire_raw, existing.raw_fire_res if existing else None),
        max_fire_res=pick_stat(max_fire_res, existing.max_fire_res if existing else None),
        cold_res=pick_stat(cold_res, existing.effective_cold_res if existing else None),
        cold_raw=pick_stat(cold_raw, existing.raw_cold_res if existing else None),
        max_cold_res=pick_stat(max_cold_res, existing.max_cold_res if existing else None),
        lightning_res=pick_stat(lightning_res, existing.effective_lightning_res if existing else None),
        lightning_raw=pick_stat(lightning_raw, existing.raw_lightning_res if existing else None),
        max_lightning_res=pick_stat(max_lightning_res, existing.max_lightning_res if existing else None),
        chaos_res=pick_stat(chaos_res, existing.effective_chaos_res if existing else None),
        chaos_raw=pick_stat(chaos_raw, existing.raw_chaos_res if existing else None),
        max_chaos_res=pick_stat(max_chaos_res, existing.max_chaos_res if existing else None),
        strength=pick_stat(strength, existing.strength if existing else None),
        dexterity=pick_stat(dexterity, existing.dexterity if existing else None),
        intelligence=pick_stat(intelligence, existing.intelligence if existing else None),
        movement_speed=pick_stat(movement_speed, existing.movement_speed if existing else None),
    )


def run_baseline_show(
    runtime_dir: str | Path,
    character_id: str,
) -> str:
    baseline = load_baseline(runtime_dir, character_id)
    if not baseline:
        return f"No baseline recorded for character '{character_id}'."

    def fmt_fact(fact: CharacterFact[int]) -> str:
        if not fact.is_known or fact.value is None:
            return "UNKNOWN"
        return f"{fact.value}"

    def fmt_res(eff: CharacterFact[int], raw: CharacterFact[int], max_res: CharacterFact[int]) -> str:
        if not eff.is_known or eff.value is None:
            return "UNKNOWN"
        res_str = f"{eff.value}%"
        if raw.is_known and raw.value is not None:
            res_str += f" (Raw: {raw.value}%)"
        if max_res.is_known and max_res.value is not None:
            res_str += f" [Max: {max_res.value}%]"
        return res_str

    lines = [
        f"=== Character Stat Baseline: {baseline.baseline_id} ===",
        f"Character ID: {baseline.character_id}",
        f"Anchored Loadout Revision: {baseline.anchored_loadout_revision}",
        f"Anchored Loadout Fingerprint: {baseline.anchored_loadout_fingerprint or 'NONE (LEGACY)'}",
        f"Observed At: {baseline.observed_at}",
        f"Life: {fmt_fact(baseline.life)}",
        f"Armour: {fmt_fact(baseline.armour)}",
        f"Evasion: {fmt_fact(baseline.evasion)}",
        f"Energy Shield: {fmt_fact(baseline.energy_shield)}",
        f"Fire Res: {fmt_res(baseline.effective_fire_res, baseline.raw_fire_res, baseline.max_fire_res)}",
        f"Cold Res: {fmt_res(baseline.effective_cold_res, baseline.raw_cold_res, baseline.max_cold_res)}",
        f"Lightning Res: {fmt_res(baseline.effective_lightning_res, baseline.raw_lightning_res, baseline.max_lightning_res)}",
        f"Chaos Res: {fmt_res(baseline.effective_chaos_res, baseline.raw_chaos_res, baseline.max_chaos_res)}",
        f"Strength: {fmt_fact(baseline.strength)}",
        f"Dexterity: {fmt_fact(baseline.dexterity)}",
        f"Intelligence: {fmt_fact(baseline.intelligence)}",
        f"Movement Speed: {fmt_fact(baseline.movement_speed)}%",
    ]
    return "\n".join(lines)
