"""PoE2 Companion MVP Live Clipboard Mode watcher and short human output."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable

from companion.equipment.baseline_cli import load_baseline
from companion.equipment.baseline_gate import check_baseline_consistency
from companion.equipment.clipboard import get_clipboard_text
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.loadout import is_item_decision_equal
from companion.equipment.loadout_cli import load_loadout, run_loadout_clear, run_loadout_set_item
from companion.equipment.parser import (
    InvalidItemClipboardError,
    parse_item_text,
    validate_poe2_item_envelope,
)
from companion.equipment.precedence import Verdict
from companion.equipment.recommendation import EquipmentRecommendation
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotOccupancy, SlotType, WeaponSetContext
from companion.state.store import CharacterStateStore


def resolve_live_stage(
    stage_arg: str | None,
    runtime_dir: str | Path,
    char_id: str,
) -> BuildProgressionStage:
    """Resolve build progression stage from explicit argument or persisted character state."""
    if stage_arg:
        stage = BuildProgressionStage(stage_arg)
        if stage is not None:
            return stage
        raise ValueError(f"Invalid progression stage '{stage_arg}'.")

    # Fallback to persisted character state
    try:
        store = CharacterStateStore(runtime_dir)
        char_state = None
        try:
            char_state = store.load_character(char_id)
        except Exception:
            char_state = store.get_active_character()

        if char_state and char_state.build_progression:
            active_stage_str = char_state.build_progression.get("active_stage")
            if active_stage_str:
                stage = BuildProgressionStage(active_stage_str)
                if stage is not None:
                    return stage
    except Exception:
        pass

    raise ValueError(
        "No progression stage specified and no persisted build stage found in runtime state. "
        "Please provide --stage (e.g. --stage 'lvl 15-32')."
    )


def supports_color() -> bool:
    """Return True if the current terminal environment supports ANSI colors."""
    if "NO_COLOR" in os.environ:
        return False
    if os.environ.get("FORCE_COLOR") in ("1", "true", "TRUE"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def format_short_human_recommendation(
    rec: EquipmentRecommendation,
    vs_item_name: str | None = None,
    slot_label: str | None = None,
    use_color: bool | None = None,
) -> str:
    """Format short, human-readable terminal recommendation output."""
    if use_color is None:
        use_color = supports_color()

    lines: list[str] = ["────────────────────────"]

    # Header / Verdict with semantic ANSI color
    if rec.verdict == Verdict.EQUIP_NOW:
        hdr = "🟢 EQUIP NOW"
        lines.append(f"\033[32m{hdr}\033[0m" if use_color else hdr)
    elif rec.verdict == Verdict.REJECT:
        hdr = "🔴 REJECT / KEEP CURRENT"
        lines.append(f"\033[31m{hdr}\033[0m" if use_color else hdr)
    elif rec.verdict == Verdict.CONDITIONAL_UPGRADE:
        hdr = "🟡 CONDITIONAL UPGRADE"
        lines.append(f"\033[33m{hdr}\033[0m" if use_color else hdr)
    elif rec.verdict == Verdict.INSUFFICIENT_DATA:
        lines.append("⚪ INSUFFICIENT DATA")
    else:
        lines.append(f"⚪ {rec.verdict.value.replace('_', ' ')}")

    lines.append("")

    # Items comparison header
    disp_name = vs_item_name
    if not disp_name and rec.displaced_items:
        disp_name = rec.displaced_items[0].name
    if not disp_name:
        disp_name = "Empty / Unobserved Slot"

    item_header = rec.candidate.name
    if slot_label:
        item_header += f" ({slot_label})"
    lines.append(item_header)
    lines.append(f"vs {disp_name}")
    lines.append("")

    # If insufficient data due to unsupported displaced effects
    if (
        rec.verdict == Verdict.INSUFFICIENT_DATA
        and rec.sufficiency is not None
        and rec.sufficiency.unsupported_displaced_effects
    ):
        lines.append("Current item contains unsupported or unmodeled effects:")
        for effect in rec.sufficiency.unsupported_displaced_effects:
            lines.append(f"- {effect}")
        lines.append("")
        lines.append("Cannot safely say the candidate is better yet.")
        lines.append("────────────────────────")
        return "\n".join(lines)

    # If insufficient data due to unobserved slot
    if (
        rec.verdict == Verdict.INSUFFICIENT_DATA
        and rec.sufficiency is not None
        and not rec.sufficiency.is_slot_known
    ):
        lines.append(f"Current equipped slot '{rec.slot.value}' is unobserved.")
        lines.append("")
        lines.append("Cannot safely say the candidate is better yet.")
        lines.append("────────────────────────")
        return "\n".join(lines)

    # Gains
    proj = rec.projection
    gains: list[str] = []
    if proj.life.delta > 0:
        gains.append(f"+{int(proj.life.delta)} Life")
    if proj.fire_res.delta > 0:
        gains.append(f"+{int(proj.fire_res.delta)}% Fire Res")
    if proj.cold_res.delta > 0:
        gains.append(f"+{int(proj.cold_res.delta)}% Cold Res")
    if proj.lightning_res.delta > 0:
        gains.append(f"+{int(proj.lightning_res.delta)}% Lightning Res")
    if proj.chaos_res.delta > 0:
        gains.append(f"+{int(proj.chaos_res.delta)}% Chaos Res")
    if proj.movement_speed.delta > 0:
        gains.append(f"+{int(proj.movement_speed.delta)}% Movement Speed")
    if proj.strength.delta > 0:
        gains.append(f"+{int(proj.strength.delta)} Strength")
    if proj.dexterity.delta > 0:
        gains.append(f"+{int(proj.dexterity.delta)} Dexterity")
    if proj.intelligence.delta > 0:
        gains.append(f"+{int(proj.intelligence.delta)} Intelligence")
    if proj.armour.delta > 0:
        gains.append(f"+{int(proj.armour.delta)} Armour")
    if proj.evasion.delta > 0:
        gains.append(f"+{int(proj.evasion.delta)} Evasion")
    if proj.energy_shield.delta > 0:
        gains.append(f"+{int(proj.energy_shield.delta)} Energy Shield")

    # Losses / Trade-offs
    losses: list[str] = []
    if proj.movement_speed.delta < 0:
        losses.append(f"{int(proj.movement_speed.delta)}% Movement Speed")
    if proj.life.delta < 0:
        losses.append(f"{int(proj.life.delta)} Life")
    if proj.fire_res.delta < 0:
        losses.append(f"{int(proj.fire_res.delta)}% Fire Res")
    if proj.cold_res.delta < 0:
        losses.append(f"{int(proj.cold_res.delta)}% Cold Res")
    if proj.lightning_res.delta < 0:
        losses.append(f"{int(proj.lightning_res.delta)}% Lightning Res")
    if proj.chaos_res.delta < 0:
        losses.append(f"{int(proj.chaos_res.delta)}% Chaos Res")
    if proj.strength.delta < 0:
        losses.append(f"{int(proj.strength.delta)} Strength")
    if proj.dexterity.delta < 0:
        losses.append(f"{int(proj.dexterity.delta)} Dexterity")
    if proj.intelligence.delta < 0:
        losses.append(f"{int(proj.intelligence.delta)} Intelligence")
    if proj.armour.delta < 0:
        losses.append(f"{int(proj.armour.delta)} Armour")
    if proj.evasion.delta < 0:
        losses.append(f"{int(proj.evasion.delta)} Evasion")
    if proj.energy_shield.delta < 0:
        losses.append(f"{int(proj.energy_shield.delta)} Energy Shield")

    if rec.verdict == Verdict.REJECT:
        if losses:
            lines.append("Main losses:")
            for l_item in losses:
                lines.append(l_item)
            lines.append("")
        has_meaningful_gain = any(
            g > 0
            for g in (
                proj.life.delta,
                proj.fire_res.delta,
                proj.cold_res.delta,
                proj.lightning_res.delta,
                proj.chaos_res.delta,
                proj.movement_speed.delta,
                proj.armour.delta,
                proj.evasion.delta,
                proj.energy_shield.delta,
            )
        )
        if not gains:
            lines.append("No useful stat gain.")
            lines.append("")
        elif not has_meaningful_gain:
            lines.append("No meaningful compensating gains.")
            lines.append("")
        lines.append(rec.verdict_reason or "Keep current item.")
        if rec.projection.removed_build_mechanics:
            mechs = [m.raw_text.split(" — ")[0] for m in rec.projection.removed_build_mechanics]
            if mechs:
                lines.append("")
                lines.append(f"Additional material uncertainty: removes {', '.join(mechs)} (unmodeled build mechanic).")
    else:
        for g_item in gains:
            lines.append(g_item)

        if losses:
            lines.append("")
            lines.append("Trade-offs:")
            for l_item in losses:
                lines.append(l_item)

        # Resistance progression highlights
        res_transitions: list[str] = []
        if rec.contextual_analysis is not None:
            for r_type, r_ana in rec.contextual_analysis.resistances.items():
                if r_ana.delta != 0 and r_ana.current_effective is not None and r_ana.projected_effective is not None:
                    res_transitions.append(f"{r_type.value.capitalize()}:\n{r_ana.current_effective}% → {r_ana.projected_effective}%")

        if res_transitions:
            lines.append("")
            for trans in res_transitions:
                lines.append(trans)

        lines.append("")
        lines.append("Recommendation:")
        if rec.verdict == Verdict.EQUIP_NOW:
            lines.append("Strong direct upgrade.")
        elif rec.verdict == Verdict.CONDITIONAL_UPGRADE:
            if "MIXED_TRADEOFF" in rec.flags:
                lines.append("Good survivability/stat gain but meaningful defense or mobility trade-off.")
            else:
                lines.append(rec.verdict_reason or "Conditional upgrade: evaluate trade-offs before equipping.")
        elif rec.verdict == Verdict.INSUFFICIENT_DATA:
            if rec.sufficiency and not rec.sufficiency.is_baseline_anchored:
                lines.append("Character baseline is missing or stale.")
            else:
                lines.append(rec.verdict_reason or "Insufficient data for confident recommendation.")
            lines.append("Cannot safely say the candidate is better yet.")
        else:
            lines.append(rec.verdict_reason)

    lines.append("────────────────────────")
    return "\n".join(lines)


def evaluate_live_candidate(
    candidate_text: str,
    engine: EquipmentIntelligenceEngine,
    runtime_dir: str | Path,
    character_id: str,
    stage: BuildProgressionStage,
    target_weapon_set: str | None = None,
) -> str:
    """Evaluate candidate text against loadout and return formatted recommendation."""
    loadout = load_loadout(runtime_dir, character_id)
    candidate = parse_item_text(candidate_text, target_weapon_set=target_weapon_set)

    # Check for ring ambiguity
    cls_lower = candidate.base_type.lower()
    is_ring = candidate.slot in (SlotType.RING_1, SlotType.RING_2) or "ring" in cls_lower

    if is_ring:
        ring1_entry = loadout.get_slot(SlotType.RING_1) if loadout else None
        ring2_entry = loadout.get_slot(SlotType.RING_2) if loadout else None

        has_ring1 = ring1_entry is not None and ring1_entry.item is not None
        has_ring2 = ring2_entry is not None and ring2_entry.item is not None

        # Case 1: Both rings known -> compare against both
        if has_ring1 and has_ring2:
            rec1 = engine.evaluate_candidate(
                item_text=candidate_text,
                character_id=character_id,
                target_slot=SlotType.RING_1,
                stage=stage,
            )
            rec2 = engine.evaluate_candidate(
                item_text=candidate_text,
                character_id=character_id,
                target_slot=SlotType.RING_2,
                stage=stage,
            )
            rep1 = format_short_human_recommendation(rec1, vs_item_name=ring1_entry.item.name, slot_label="Ring 1")
            rep2 = format_short_human_recommendation(rec2, vs_item_name=ring2_entry.item.name, slot_label="Ring 2")
            return f"{rep1}\n\n{rep2}"

        # Case 2: Only Ring 1 known
        if has_ring1 and not has_ring2:
            rec = engine.evaluate_candidate(
                item_text=candidate_text,
                character_id=character_id,
                target_slot=SlotType.RING_1,
                stage=stage,
            )
            return format_short_human_recommendation(rec, vs_item_name=ring1_entry.item.name, slot_label="Ring 1")

        # Case 3: Only Ring 2 known
        if has_ring2 and not has_ring1:
            rec = engine.evaluate_candidate(
                item_text=candidate_text,
                character_id=character_id,
                target_slot=SlotType.RING_2,
                stage=stage,
            )
            return format_short_human_recommendation(rec, vs_item_name=ring2_entry.item.name, slot_label="Ring 2")

        # Case 4: Neither ring is known -> do NOT choose arbitrary default!
        lines = [
            "────────────────────────",
            "⚪ SLOT CONTEXT UNKNOWN",
            "",
            "Both Ring 1 and Ring 2 are unobserved in current loadout.",
            "Cannot safely determine which ring to compare against.",
            "",
            "Please capture equipped rings first:",
            "  companion gear loadout set-clipboard --slot ring1",
            "  companion gear loadout set-clipboard --slot ring2",
            "────────────────────────",
        ]
        return "\n".join(lines)

    # Check for weapon ambiguity
    is_weapon = candidate.slot in (SlotType.MAIN_HAND, SlotType.OFF_HAND) or candidate.slot_occupancy in (
        SlotOccupancy.MAIN_HAND,
        SlotOccupancy.OFF_HAND,
        SlotOccupancy.TWO_HAND,
    )
    if is_weapon and target_weapon_set is None:
        lines = [
            "────────────────────────",
            "⚪ WEAPON SET CONTEXT AMBIGUOUS",
            "",
            "Cannot determine whether weapon belongs to Weapon Set 1 or Weapon Set 2.",
            "Please specify weapon set context when running live mode:",
            "  companion gear live --weapon-set set_1",
            "  or",
            "  companion gear live --weapon-set set_2",
            "────────────────────────",
        ]
        return "\n".join(lines)

    wset_ctx = WeaponSetContext.from_val(target_weapon_set) if target_weapon_set else candidate.weapon_set
    rec = engine.evaluate_candidate(
        item_text=candidate_text,
        character_id=character_id,
        target_slot=candidate.slot,
        target_weapon_set=wset_ctx,
        stage=stage,
    )
    vs_name = None
    if rec.displaced_items:
        vs_name = rec.displaced_items[0].name
    elif loadout:
        entry = loadout.get_slot(rec.slot, wset_ctx)
        if entry and entry.item:
            vs_name = entry.item.name

    return format_short_human_recommendation(rec, vs_item_name=vs_name)


def run_live_watcher(
    runtime_dir: str | Path,
    character_id: str,
    stage: BuildProgressionStage,
    poll_interval: float = 0.25,
    clipboard_reader: Callable[[], str] | None = None,
    output_writer: Callable[[str], None] = print,
    as_json: bool = False,
    weapon_set: str | None = None,
    bootstrap: bool = False,
) -> int:
    """Run passive clipboard monitoring loop for PoE2 equipment."""
    r_path = Path(runtime_dir)
    engine = EquipmentIntelligenceEngine(runtime_dir=r_path)
    reader = clipboard_reader if clipboard_reader is not None else get_clipboard_text

    # 1. Startup check
    loadout = load_loadout(r_path, character_id)
    raw_baseline = load_baseline(r_path, character_id)

    loadout_rev = str(loadout.revision) if loadout else "UNINITIALIZED"

    baseline_status = "MISSING"
    baseline_note: str | None = None
    if raw_baseline is None:
        baseline_status = "MISSING"
        baseline_note = "Note: Character baseline is MISSING. Run 'companion gear baseline set' to establish baseline stats."
    elif loadout is None:
        baseline_status = "UNINITIALIZED"
        baseline_note = "Note: Loadout is UNINITIALIZED. Run 'companion gear loadout finalize' to establish revision."
    else:
        consistency = check_baseline_consistency(
            raw_baseline,
            current_loadout_revision=loadout.revision,
            current_loadout_fingerprint=loadout.compute_fingerprint(),
        )
        if consistency.is_consistent:
            baseline_status = "READY"
        else:
            baseline_status = "STALE"
            baseline_note = "Note: Baseline is STALE (revision mismatch). Run 'companion gear baseline refresh'."

    output_writer("PoE2 Companion LIVE")
    output_writer(f"Runtime: {r_path}")
    output_writer(f"Stage: {stage.value}")
    output_writer(f"Loadout revision: {loadout_rev}")
    output_writer(f"Baseline: {baseline_status}")
    if baseline_status == "MISSING":
        output_writer("Item-to-item comparison: AVAILABLE")
        output_writer("Character-context projection: LIMITED")
    if bootstrap:
        output_writer("Bootstrap mode: ACTIVE")
        output_writer("Warning: first item copied for an unknown slot is assumed to be CURRENT EQUIPPED.")
        output_writer("Copy CURRENT Weapon Set 1 first, then CURRENT Weapon Set 2.")
    if baseline_note and baseline_status != "MISSING":
        output_writer("")
        output_writer(baseline_note)
    output_writer("")
    output_writer("Waiting for PoE2 item clipboard...")
    output_writer("Hover item and press Ctrl+C.")
    output_writer("")

    last_raw_clipboard: str = ""
    last_item_hash: str = ""

    try:
        while True:
            try:
                raw_text = reader()
            except KeyboardInterrupt:
                raise
            except Exception:
                raw_text = ""

            if raw_text and raw_text != last_raw_clipboard:
                last_raw_clipboard = raw_text

                # Validate PoE2 envelope
                is_valid = True
                try:
                    validate_poe2_item_envelope(raw_text)
                except InvalidItemClipboardError:
                    is_valid = False
                except Exception:
                    is_valid = False

                if is_valid:
                    # Item deduplication check
                    item_hash = hashlib.sha256(raw_text.strip().encode("utf-8")).hexdigest()
                    if item_hash != last_item_hash:
                        last_item_hash = item_hash
                        wset_ctx = WeaponSetContext.from_val(weapon_set) if weapon_set else None
                        try:
                            candidate = parse_item_text(raw_text, target_weapon_set=wset_ctx)
                        except Exception as exc:
                            output_writer(f"Error parsing item: {exc}")
                            continue

                        cls_lower = candidate.base_type.lower()
                        is_ring = candidate.slot in (SlotType.RING_1, SlotType.RING_2) or "ring" in cls_lower
                        is_weapon = candidate.slot in (SlotType.MAIN_HAND, SlotType.OFF_HAND) or candidate.slot_occupancy in (
                            SlotOccupancy.MAIN_HAND,
                            SlotOccupancy.OFF_HAND,
                            SlotOccupancy.TWO_HAND,
                        )

                        bootstrapped = False

                        if bootstrap:
                            loadout = load_loadout(r_path, character_id)

                            if is_ring:
                                r1_entry = loadout.get_slot(SlotType.RING_1) if loadout else None
                                r2_entry = loadout.get_slot(SlotType.RING_2) if loadout else None
                                has_r1 = r1_entry is not None and r1_entry.item is not None
                                has_r2 = r2_entry is not None and r2_entry.item is not None

                                if not has_r1:
                                    run_loadout_set_item(r_path, character_id, "ring1", raw_text)
                                    output_writer("✓ CURRENT RING 1 LEARNED")
                                    output_writer(candidate.name or candidate.base_type)
                                    output_writer("")
                                    bootstrapped = True
                                elif not has_r2:
                                    if not is_item_decision_equal(r1_entry.item, candidate):
                                        run_loadout_set_item(r_path, character_id, "ring2", raw_text)
                                        output_writer("✓ CURRENT RING 2 LEARNED")
                                        output_writer(candidate.name or candidate.base_type)
                                        output_writer("")
                                        bootstrapped = True
                                    else:
                                        output_writer("Ring is already recorded as Ring 1. To record Ring 2, capture a distinct ring.")
                                        output_writer("")
                                        continue

                            elif is_weapon:
                                if weapon_set is None:
                                    w1_entry = loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_1) if loadout else None
                                    w2_entry = loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_2) if loadout else None
                                    has_w1 = w1_entry is not None and w1_entry.item is not None
                                    has_w2 = w2_entry is not None and w2_entry.item is not None

                                    if not has_w1:
                                        run_loadout_set_item(
                                            r_path,
                                            character_id,
                                            candidate.slot.value,
                                            raw_text,
                                            weapon_set_name="set_1",
                                        )
                                        if candidate.slot_occupancy == SlotOccupancy.TWO_HAND:
                                            run_loadout_clear(r_path, character_id, SlotType.OFF_HAND.value, weapon_set_name="set_1")
                                        output_writer("✓ CURRENT WEAPON SET 1 LEARNED")
                                        output_writer(candidate.name or candidate.base_type)
                                        output_writer("")
                                        bootstrapped = True
                                    elif not has_w2:
                                        if not is_item_decision_equal(w1_entry.item, candidate):
                                            run_loadout_set_item(
                                                r_path,
                                                character_id,
                                                candidate.slot.value,
                                                raw_text,
                                                weapon_set_name="set_2",
                                            )
                                            if candidate.slot_occupancy == SlotOccupancy.TWO_HAND:
                                                run_loadout_clear(r_path, character_id, SlotType.OFF_HAND.value, weapon_set_name="set_2")
                                            output_writer("✓ CURRENT WEAPON SET 2 LEARNED")
                                            output_writer(candidate.name or candidate.base_type)
                                            output_writer("")
                                            bootstrapped = True
                                        else:
                                            output_writer("Weapon is already recorded as Weapon Set 1. To record Weapon Set 2, capture a distinct weapon.")
                                            output_writer("")
                                            continue
                                else:
                                    target_slot = candidate.slot
                                    slot_entry = loadout.get_slot(target_slot, weapon_set=wset_ctx) if loadout else None
                                    has_slot = slot_entry is not None and slot_entry.item is not None
                                    if not has_slot:
                                        run_loadout_set_item(
                                            r_path,
                                            character_id,
                                            target_slot.value,
                                            raw_text,
                                            weapon_set_name=wset_ctx.value,
                                        )
                                        slot_disp = "MAIN HAND" if target_slot == SlotType.MAIN_HAND else ("OFF HAND" if target_slot == SlotType.OFF_HAND else target_slot.value.upper())
                                        output_writer(f"✓ CURRENT {slot_disp} LEARNED")
                                        output_writer(candidate.name or candidate.base_type)
                                        output_writer("")
                                        bootstrapped = True

                            else:
                                slot_entry = loadout.get_slot(candidate.slot) if loadout else None
                                has_slot = slot_entry is not None and slot_entry.item is not None
                                if not has_slot:
                                    run_loadout_set_item(r_path, character_id, candidate.slot.value, raw_text)
                                    slot_disp = candidate.slot.value.replace("_", " ").upper()
                                    output_writer(f"✓ CURRENT {slot_disp} LEARNED")
                                    output_writer(candidate.name or candidate.base_type)
                                    output_writer("")
                                    bootstrapped = True

                        if not bootstrapped:
                            try:
                                report = evaluate_live_candidate(
                                    candidate_text=raw_text,
                                    engine=engine,
                                    runtime_dir=r_path,
                                    character_id=character_id,
                                    stage=stage,
                                    target_weapon_set=weapon_set,
                                )
                                output_writer(report)
                            except Exception as exc:
                                output_writer(f"Error evaluating item: {exc}")

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        output_writer("\nExiting live clipboard mode.")
        return 0
