"""Unit tests for the CLI evaluation runner and formatter module (companion/equipment/cli_eval.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from companion.equipment.cli_eval import (
    evaluate_once,
    format_result,
    open_pob_session,
    run_live,
)
from tests.unit.eval_helpers import FUB, Stub, _install, _item


def test_format_result_lines() -> None:
    flat_equip = {
        "verdict": "EQUIP_NOW",
        "item_name": "Loath Trail",
        "pob_slot": "Boots",
        "slot": "boots",
        "slot_reason": "Slot: Boots",
        "dps_pct": 0.0123,
        "ehp_pct": -0.004,
        "engine": "pob2",
        "engine_reason": None,
        "safety": ["Material mechanic warning"],
        "gains": ["+66 to maximum Life"],
        "trade_offs": [],
        "guide": None,
    }
    out = format_result(flat_equip)
    assert "DPS +1.2% · EHP −0.4%" in out
    assert "⛔ " in out
    assert "+ " in out
    assert "Slot: Boots" in out

    flat_insufficient = {
        "verdict": "INSUFFICIENT_DATA",
        "item_name": "Iron Greaves",
        "pob_slot": "Boots",
        "slot": "boots",
        "slot_reason": "Slot: Boots",
        "dps_pct": 0.0123,
        "ehp_pct": -0.004,
        "engine": "pob2",
        "engine_reason": None,
        "safety": [],
        "gains": [],
        "trade_offs": [],
        "guide": None,
    }
    out_insufficient = format_result(flat_insufficient)
    assert "DPS " not in out_insufficient

    flat_with_guide_and_tradeoff = {
        "verdict": "SIDEGRADE",
        "item_name": "Iron Greaves",
        "pob_slot": "Boots",
        "slot": "boots",
        "slot_reason": "Slot: Boots",
        "dps_pct": 0.0,
        "ehp_pct": 0.0,
        "engine": "heuristic",
        "engine_reason": "PoB2 tidak tersedia",
        "safety": [],
        "gains": [],
        "trade_offs": ["-15% to Cold Resistance"],
        "guide": {
            "name": "Fubgun Deadeye",
            "stage_title": "Early Maps",
            "priority_matched": 3,
            "priority_total": 4,
        },
    }
    out_extra = format_result(flat_with_guide_and_tradeoff)
    assert "Guide: Fubgun Deadeye · Early Maps · Prioritas 3/4" in out_extra
    assert "- 15% to Cold Resistance" in out_extra
    assert "Engine: heuristik — PoB2 tidak tersedia" in out_extra


def test_cli_evaluate_heuristic_prints_engine_reason(tmp_path: Path) -> None:
    _install(tmp_path, FUB, "BOMSHAK", 60)
    boots = _item("Boots", "Iron Greaves", ["+20 to maximum Life"])
    code, text = evaluate_once(boots, tmp_path, "BOMSHAK", pob_session=None)
    assert code == 0
    assert "Engine: heuristik" in text


def test_evaluate_once_value_error_exit_1(tmp_path: Path) -> None:
    _install(tmp_path, FUB, "BOMSHAK", 60)
    currency = _item("Stackable Currency", "Chaos Orb", ["Reforges a rare item"])
    code, text = evaluate_once(currency, tmp_path, "BOMSHAK", pob_session=None)
    assert code == 1
    assert "Item ini tidak bisa dipasang di slot equipment" in text


def test_live_dedupes_and_skips_noise(tmp_path: Path) -> None:
    _install(tmp_path, FUB, "BOMSHAK", 60)
    boots = _item("Boots", "Iron Greaves", ["+20 to maximum Life"], name="Iron Greaves")
    currency = _item("Stackable Currency", "Chaos Orb", ["Reforges a rare item"])
    ring = _item("Rings", "Iron Ring", ["+10 to maximum Life"], name="Iron Ring")

    items = [boots, boots, "hello", currency, ring, ring]
    written: list[str] = []

    def fake_reader() -> str:
        if items:
            return items.pop(0)
        return ring

    code = run_live(
        tmp_path,
        "BOMSHAK",
        pob_session=Stub(),
        poll_interval=0.0,
        clipboard_reader=fake_reader,
        output_writer=written.append,
        max_polls=6,
    )

    assert code == 0
    # Exactly 2 result blocks (boots, ring) and one "Item dilewati:" line
    assert len(written) == 3
    assert any("Iron Greaves" in w for w in written)
    assert any("Iron Ring" in w for w in written)
    item_dilewati = [w for w in written if w.startswith("Item dilewati:")]
    assert len(item_dilewati) == 1
    assert "Item ini tidak bisa dipasang di slot equipment" in item_dilewati[0]


def test_live_json_one_line_per_item(tmp_path: Path) -> None:
    _install(tmp_path, FUB, "BOMSHAK", 60)
    boots = _item("Boots", "Iron Greaves", ["+20 to maximum Life"])
    ring = _item("Rings", "Iron Ring", ["+10 to maximum Life"])

    items = [boots, ring]
    written: list[str] = []

    def fake_reader() -> str:
        if items:
            return items.pop(0)
        return ""

    code = run_live(
        tmp_path,
        "BOMSHAK",
        pob_session=Stub(),
        poll_interval=0.0,
        as_json=True,
        clipboard_reader=fake_reader,
        output_writer=written.append,
        max_polls=2,
    )

    assert code == 0
    assert len(written) == 2
    for line in written:
        parsed = json.loads(line)
        assert "verdict" in parsed


def test_open_pob_session_disabled_and_failed(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    assert open_pob_session("BOMSHAK", enabled=False) is None
    captured = capsys.readouterr()
    assert captured.out == ""

    class FailingPobSession:
        def __init__(self, character_name: str) -> None:
            self.character_name = character_name
            self.unavailable_reason = "Docker daemon is not running"

        def initialize(self) -> bool:
            return False

    monkeypatch.setattr("companion.equipment.cli_eval.Pob2EquipmentSession", FailingPobSession)
    sess = open_pob_session("BOMSHAK", enabled=True)
    assert sess is None
    captured = capsys.readouterr()
    assert "PoB2 tidak tersedia: Docker daemon is not running" in captured.out


def test_evaluate_once_json(tmp_path: Path) -> None:
    _install(tmp_path, FUB, "BOMSHAK", 60)
    boots = _item("Boots", "Iron Greaves", ["+20 to maximum Life"])
    code, text = evaluate_once(boots, tmp_path, "BOMSHAK", pob_session=None, as_json=True)
    assert code == 0
    parsed = json.loads(text)
    assert "verdict" in parsed


def test_evaluate_once_locked_slot_mismatch(tmp_path: Path) -> None:
    _install(tmp_path, FUB, "BOMSHAK", 60)
    boots = _item("Boots", "Iron Greaves", ["+20 to maximum Life"])
    code, text = evaluate_once(boots, tmp_path, "BOMSHAK", pob_session=None, locked_slot="Ring 1")
    assert code == 1
    assert "Slot terkunci tidak cocok dengan item" in text



def test_live_survives_unexpected_error(tmp_path, monkeypatch):
    import companion.equipment.cli_eval as ce

    def boom(*_a, **_k):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(ce, "evaluate", boom)
    out: list[str] = []
    item = _item("Boots", "Wool Shoes", ["+10 to maximum Life"])
    texts = iter([item, item + "x"])
    code = ce.run_live(tmp_path, "BOMSHAK", pob_session=None, poll_interval=0,
                       clipboard_reader=lambda: next(texts), output_writer=out.append, max_polls=2)
    assert code == 0
    assert out == ["Evaluasi gagal: engine exploded"] * 2


def test_cli_parser_gear_live_options() -> None:
    from companion.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["gear", "live", "--no-pob", "--stage", "3"])
    assert args.no_pob is True
    assert args.stage == "3"

    with pytest.raises(SystemExit):
        parser.parse_args(["gear", "live", "--bootstrap"])

