"""Passive platform clipboard reader and CLI evaluation runners."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Any
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.recommendation import EquipmentRecommendation
from companion.equipment.rules import BuildProgressionStage


def _read_os_clipboard() -> str:
    """Read text from platform clipboard passively without simulating inputs."""
    # Try tkinter if available
    try:
        import tkinter
        r = tkinter.Tk()
        r.withdraw()
        text = r.clipboard_get()
        r.destroy()
        if text:
            return str(text)
    except Exception:
        pass

    # Windows fallback via powershell Get-Clipboard
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if res.returncode == 0 and res.stdout:
                return res.stdout
        except Exception:
            pass

    return ""


def get_clipboard_text() -> str:
    return _read_os_clipboard()


def read_item_input(file_path: str | Path | None = None) -> str:
    if file_path:
        p = Path(file_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Item input file not found: {p}")
        return p.read_text(encoding="utf-8")
    return get_clipboard_text()


def run_inspect_clipboard(
    runtime_dir: str | Path,
    character_id: str,
    slot_name: str | None = None,
    weapon_set_name: str | None = None,
    stage: BuildProgressionStage = BuildProgressionStage.EARLY_ENDGAME,
) -> tuple[str, EquipmentRecommendation]:
    raw_text = get_clipboard_text()
    if not raw_text or not raw_text.strip():
        raise ValueError("Clipboard is empty or contains no valid item text.")

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        item_text=raw_text,
        character_id=character_id,
        target_slot=slot_name,
        target_weapon_set=weapon_set_name,
        stage=stage,
    )
    return rec.formatted_report, rec


def run_evaluate_file(
    runtime_dir: str | Path,
    file_path: str | Path,
    character_id: str,
    slot_name: str | None = None,
    weapon_set_name: str | None = None,
    stage: BuildProgressionStage = BuildProgressionStage.EARLY_ENDGAME,
) -> tuple[str, EquipmentRecommendation]:
    raw_text = read_item_input(file_path=file_path)
    if not raw_text or not raw_text.strip():
        raise ValueError(f"File '{file_path}' is empty or contains no valid item text.")

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        item_text=raw_text,
        character_id=character_id,
        target_slot=slot_name,
        target_weapon_set=weapon_set_name,
        stage=stage,
    )
    return rec.formatted_report, rec
