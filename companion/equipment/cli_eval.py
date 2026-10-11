"""CLI evaluation runner and formatter on the guide-aware evaluation pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import time
from typing import Any, Callable

from companion.dashboard_api import flatten_result
from companion.equipment.clipboard import get_clipboard_text
from companion.equipment.evaluation import evaluate
from companion.equipment.pob2_equipment_advisor import Pob2EquipmentSession

logger = logging.getLogger(__name__)


def _format_pct(val: float | None) -> str:
    if val is None:
        return "+0.0%"
    pct = val * 100.0
    fixed = f"{abs(pct):.1f}"
    if fixed == "0.0":
        return "+0.0%"
    return f"−{fixed}%" if pct < 0 else f"+{fixed}%"


def format_result(res: dict[str, Any]) -> str:
    verdict = res.get("verdict", "")
    item_name = res.get("item_name") or res.get("base_type") or ""
    pob_slot = res.get("pob_slot") or res.get("slot") or ""
    slot_reason = res.get("slot_reason") or ""

    if slot_reason:
        slot_part = f"{pob_slot} ({slot_reason})" if pob_slot else f"({slot_reason})"
    else:
        slot_part = pob_slot

    header = f"{verdict} — {item_name} → {slot_part}" if slot_part else f"{verdict} — {item_name}"
    lines = [header]

    engine = res.get("engine", "")
    if verdict not in ("INSUFFICIENT_DATA", "ALREADY_EQUIPPED") and engine != "none":
        dps_str = _format_pct(res.get("dps_pct"))
        ehp_str = _format_pct(res.get("ehp_pct"))
        lines.append(f"  DPS {dps_str} · EHP {ehp_str}")

    for reason in res.get("safety") or []:
        lines.append(f"  ⛔ {reason}")

    for gain in res.get("gains") or []:
        if gain.startswith("+ "):
            lines.append(f"  {gain}")
        elif gain.startswith("+"):
            lines.append(f"  + {gain[1:].strip()}")
        else:
            lines.append(f"  + {gain}")

    for trade_off in res.get("trade_offs") or []:
        if trade_off.startswith("- "):
            lines.append(f"  {trade_off}")
        elif trade_off.startswith("-"):
            lines.append(f"  - {trade_off[1:].strip()}")
        else:
            lines.append(f"  - {trade_off}")

    guide = res.get("guide")
    if guide and isinstance(guide, dict):
        name = guide.get("name") or ""
        stage_title = guide.get("stage_title") or ""
        matched = guide.get("priority_matched")
        total = guide.get("priority_total")
        if matched is not None and total is not None:
            lines.append(f"  Guide: {name} · {stage_title} · Prioritas {matched}/{total}")
        elif name or stage_title:
            lines.append(f"  Guide: {name} · {stage_title}")

    if engine != "pob2":
        engine_reason = res.get("engine_reason")
        if engine_reason:
            lines.append(f"  Engine: heuristik — {engine_reason}")
        else:
            lines.append("  Engine: heuristik")

    return "\n".join(lines)


def evaluate_once(
    raw: str,
    runtime_dir: Path,
    character_id: str,
    *,
    pob_session: Any | None,
    locked_slot: str | None = None,
    stage_override: str | None = None,
    as_json: bool = False,
) -> tuple[int, str]:
    try:
        res = evaluate(
            raw_text=raw,
            character_id=character_id,
            runtime_dir=runtime_dir,
            pob_session=pob_session,
            source="cli",
            locked_slot=locked_slot,
            stage_override=stage_override,
        )
    except ValueError as exc:
        return 1, str(exc)

    flat = flatten_result(res)
    if as_json:
        return 0, json.dumps(flat)
    return 0, format_result(flat)


def open_pob_session(character_id: str, enabled: bool) -> Pob2EquipmentSession | None:
    if not enabled:
        return None
    session = Pob2EquipmentSession(character_name=character_id)
    try:
        ok = session.initialize()
    except Exception as exc:
        print(f"PoB2 tidak tersedia: {exc}")
        return None
    if not ok:
        print(f"PoB2 tidak tersedia: {session.unavailable_reason}")
        return None
    return session


def run_live(
    runtime_dir: Path,
    character_id: str,
    *,
    pob_session: Any | None,
    poll_interval: float = 0.25,
    as_json: bool = False,
    stage_override: str | None = None,
    clipboard_reader: Callable[[], str] = get_clipboard_text,
    output_writer: Callable[[str], None] = print,
    max_polls: int | None = None,
) -> int:
    polls = 0
    last_text: str | None = None

    try:
        while max_polls is None or polls < max_polls:
            polls += 1
            try:
                raw = clipboard_reader()
            except KeyboardInterrupt:
                return 0
            except Exception:
                raw = ""

            if raw and raw != last_text:
                last_text = raw
                if "Rarity:" in raw and "Item Class:" in raw:
                    try:
                        code, out = evaluate_once(
                            raw, runtime_dir, character_id, pob_session=pob_session,
                            stage_override=stage_override, as_json=as_json,
                        )
                    except Exception as exc:  # keep the watcher alive on engine/parser bugs
                        logger.warning("CLI live evaluation failed", exc_info=True)
                        code, out = 2, f"Evaluasi gagal: {exc}"
                    output_writer(f"Item dilewati: {out}" if code == 1 else out)

            if max_polls is not None and polls >= max_polls:
                break

            if poll_interval > 0:
                try:
                    time.sleep(poll_interval)
                except KeyboardInterrupt:
                    return 0
    except KeyboardInterrupt:
        return 0

    return 0
