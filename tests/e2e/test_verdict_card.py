"""E2E tests for verdict card contents and engine header."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Page

from tests.e2e.conftest import wait_js

RING_ITEM_TEXT = """Item Class: Rings
Rarity: Rare
Storm Circle
Topaz Ring
--------
Requirements:
Level: 30
--------
Item Level: 35
--------
+40% to Lightning Resistance
+20 to Strength
"""


def _open_compare_subtab(page: Page) -> None:
    page.locator('.nav-item[data-tab="tab-gear"]').click()
    page.locator("#subtab-view-compare").click()


def test_card_shows_slot_reason_and_pcts(dashboard_page: Page, mock_api: Any) -> None:
    slot_reason = "Ring 1 memiliki resistensi lebih rendah sehingga prioritas diganti"
    mock_api(
        dashboard_page,
        {
            "/api/evaluate-item": {
                "item_name": "Storm Circle",
                "slot": "ring1",
                "slot_reason": slot_reason,
                "dps_pct": 0.0123,
                "ehp_pct": -0.004,
                "engine": "pob2",
                "verdict": "EQUIP_NOW",
                "gains": ["+40% Lightning Res"],
                "trade_offs": [],
            }
        },
    )

    _open_compare_subtab(dashboard_page)
    dashboard_page.fill("#candidate-textarea", RING_ITEM_TEXT)
    dashboard_page.locator("#btn-run-compare").click()

    dashboard_page.wait_for_selector("#compare-verdict-result .verdict-box")
    card_text = dashboard_page.locator("#compare-verdict-result").inner_text()

    assert "DPS +1.2%" in card_text
    assert "EHP −0.4%" in card_text
    assert slot_reason in card_text
    assert f"🎯 Slot: Ring 1 — {slot_reason}" in card_text


def test_card_priority_line(dashboard_page: Page, mock_api: Any) -> None:
    mock_api(
        dashboard_page,
        {
            "/api/evaluate-item": {
                "item_name": "Storm Circle",
                "slot": "ring1",
                "slot_reason": "Slot kosong",
                "engine": "pob2",
                "verdict": "EQUIP_NOW",
                "guide": {
                    "name": "Fubgun Deadeye",
                    "stage_title": "Early Maps",
                    "priority_matched": 3,
                    "priority_total": 4,
                    "must_have_missing": ["Movement Speed"],
                },
                "gains": [],
                "trade_offs": [],
            }
        },
    )

    _open_compare_subtab(dashboard_page)
    dashboard_page.fill("#candidate-textarea", RING_ITEM_TEXT)
    dashboard_page.locator("#btn-run-compare").click()

    dashboard_page.wait_for_selector("#compare-verdict-result .verdict-box")
    card_text = dashboard_page.locator("#compare-verdict-result").inner_text()

    assert "Prioritas guide 3/4 (kurang: Movement Speed)" in card_text


def test_card_safety_badge(dashboard_page: Page, mock_api: Any) -> None:
    safety_reason = (
        "Fire damage ke Attack menyalakan Oil Grenade terlalu cepat (Fubgun, lvl 52+)"
    )
    mock_api(
        dashboard_page,
        {
            "/api/evaluate-item": {
                "item_name": "Storm Circle",
                "slot": "ring1",
                "slot_reason": "Evaluasi cincin",
                "engine": "pob2",
                "verdict": "REJECT",
                "safety": [safety_reason],
                "gains": [],
                "trade_offs": [],
            }
        },
    )

    _open_compare_subtab(dashboard_page)
    dashboard_page.fill("#candidate-textarea", RING_ITEM_TEXT)
    dashboard_page.locator("#btn-run-compare").click()

    dashboard_page.wait_for_selector("#compare-verdict-result .verdict-box")
    card_text = dashboard_page.locator("#compare-verdict-result").inner_text()

    expected_badge = f"⛔ {safety_reason}"
    assert expected_badge in card_text


def test_card_sparse_response_has_no_placeholder_garbage(
    dashboard_page: Page,
) -> None:
    _open_compare_subtab(dashboard_page)

    responses: list[dict[str, Any]] = [
        {
            "verdict": "ALREADY_EQUIPPED",
            "engine": "pob2",
            "engine_reason": None,
            "slot": "boots",
            "slot_reason": "Slot boots",
            "dps_pct": 0.0,
            "ehp_pct": 0.0,
            "dps_delta": 0,
            "life_delta": 0,
            "slot_empty": False,
            "auto_equip_ok": False,
            "dims": {},
            "guide": None,
            "safety": [],
        },
        {
            "verdict": "INSUFFICIENT_DATA",
            "engine": "heuristic",
            "engine_reason": "Stat perbandingan senjata tidak lengkap",
            "is_weapon": True,
            "slot": "main_hand",
            "slot_reason": "Senjata utama (Set 1)",
            "dims": {},
            "guide": None,
            "safety": [],
        },
    ]

    for resp in responses:
        dashboard_page.evaluate(
            """(data) => {
                const container = document.getElementById('compare-verdict-result');
                return import('/js/compare.js').then(m => m.renderEvaluationVerdict(data, container));
            }""",
            resp,
        )
        card_text = dashboard_page.locator("#compare-verdict-result").inner_text()
        assert "DPS +0.0%" not in card_text
        assert "DPS " not in card_text
        for placeholder in ("NaN", "undefined", "null"):
            assert placeholder not in card_text, (
                f"Found '{placeholder}' in verdict card text for verdict {resp.get('verdict')}: {card_text}"
            )


def test_header_shows_unavailable_reason(
    dashboard_page: Page, mock_api: Any
) -> None:
    reason = "Docker daemon is not running (zero-backend fallback active)"
    mock_api(
        dashboard_page,
        {
            "/api/status": {
                "status": "ok",
                "character": {"name": "BOMSHAK", "level": 1, "resistances": {}},
                "objective": {},
                "loadout": {
                    "shared_slots": {},
                    "weapon_set_1": {},
                    "weapon_set_2": {},
                },
                "engine_status": {
                    "available": False,
                    "unavailable_reason": reason,
                },
            }
        },
    )

    dashboard_page.evaluate("import('/js/runtime.js').then(m => m.fetchHttpRuntime())")

    dashboard_page.wait_for_function(
        "expected => document.getElementById('status-label')?.textContent?.includes(expected)",
        arg=reason,
        timeout=5000,
    )

    status_text = dashboard_page.locator("#status-label").inner_text()
    assert reason in status_text
    assert f"PoB2 OFF: {reason}" == status_text


def test_card_target_fit_and_heuristic_engine_reason(
    dashboard_page: Page,
) -> None:
    _open_compare_subtab(dashboard_page)

    data = {
        "verdict": "EQUIP_NOW",
        "engine": "heuristic",
        "engine_reason": "PoB2 timeout (fallback ke heuristik)",
        "slot": "gloves",
        "slot_reason": "Sarung tangan upgrade",
        "dps_pct": 0.05,
        "ehp_pct": 0.02,
        "guide": {
            "name": "Fubgun Deadeye",
            "stage_title": "Campaign",
            "priority_matched": 2,
            "priority_total": 3,
            "must_have_missing": [],
            "target_fit": {
                "dps_pct": 0.08,
                "ehp_pct": 0.03,
            },
        },
        "safety": [],
    }

    dashboard_page.evaluate(
        """(data) => {
            const container = document.getElementById('compare-verdict-result');
            return import('/js/compare.js').then(m => m.renderEvaluationVerdict(data, container));
        }""",
        data,
    )
    card_text = dashboard_page.locator("#compare-verdict-result").inner_text()

    assert "Prioritas guide 2/3" in card_text
    assert "(kurang:" not in card_text
    assert "Di build target: DPS +8.0% · EHP +3.0%" in card_text
    assert "⚠ Estimasi heuristik (tanpa PoB2) — PoB2 timeout (fallback ke heuristik)" in card_text


def test_card_target_fit_ignores_speculative_alias_keys(
    dashboard_page: Page,
) -> None:
    _open_compare_subtab(dashboard_page)

    data = {
        "verdict": "EQUIP_NOW",
        "engine": "pob2",
        "slot": "gloves",
        "slot_reason": "Sarung tangan upgrade",
        "dps_pct": 0.05,
        "ehp_pct": 0.02,
        "target_fit": {
            "dps_pct": 0.08,
            "ehp_pct": 0.03,
        },
        "guide": {
            "name": "Fubgun Deadeye",
            "stage_title": "Campaign",
            "target_fit": {
                "dps": 0.08,
                "ehp": 0.03,
            },
        },
        "safety": [],
    }

    dashboard_page.evaluate(
        """(data) => {
            const container = document.getElementById('compare-verdict-result');
            return import('/js/compare.js').then(m => m.renderEvaluationVerdict(data, container));
        }""",
        data,
    )
    card_text = dashboard_page.locator("#compare-verdict-result").inner_text()
    assert "Di build target" not in card_text

