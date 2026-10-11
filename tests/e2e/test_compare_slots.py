"""E2E tests for server-owned slot compare and verdict-gated auto-equip."""

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

CROSSBOW_ITEM_TEXT = """Item Class: Crossbows
Rarity: Rare
Gloom Piercer
Bombard Crossbow
--------
Physical Damage: 30-75
--------
Requirements:
Level: 16
--------
+20 to maximum Life
+10% to Fire Resistance
+15% to Attack Speed
"""


def test_manual_compare_sends_no_slot_when_unlocked(dashboard_page: Page, mock_api: Any) -> None:
    requests = mock_api(
        dashboard_page,
        {
            "/api/evaluate-item": {
                "item_name": "Storm Circle",
                "slot": "ring1",
                "verdict": "EQUIP_NOW",
                "gains": ["+40% Lightning Res"],
                "trade_offs": [],
            }
        },
    )

    dashboard_page.locator('.nav-item[data-tab="tab-gear"]').click()
    dashboard_page.locator("#subtab-view-compare").click()
    dashboard_page.fill("#candidate-textarea", RING_ITEM_TEXT)
    dashboard_page.locator("#btn-run-compare").click()

    dashboard_page.wait_for_selector("#compare-verdict-result .verdict-box")

    eval_calls = [body for path, body in requests if path == "/api/evaluate-item"]
    assert len(eval_calls) == 1
    assert "slot" not in eval_calls[0]


def test_manual_compare_sends_selected_slot_when_locked(dashboard_page: Page, mock_api: Any) -> None:
    requests = mock_api(
        dashboard_page,
        {
            "/api/evaluate-item": {
                "item_name": "Storm Circle",
                "slot": "ring2",
                "verdict": "EQUIP_NOW",
                "gains": [],
                "trade_offs": [],
            }
        },
    )

    dashboard_page.locator('.nav-item[data-tab="tab-gear"]').click()
    dashboard_page.locator("#subtab-view-compare").click()
    dashboard_page.evaluate("import('/js/compare.js').then(m => m.selectSlot('ring2'))")
    dashboard_page.check("#compare-lock-slot")
    dashboard_page.fill("#candidate-textarea", RING_ITEM_TEXT)
    dashboard_page.locator("#btn-run-compare").click()

    dashboard_page.wait_for_selector("#compare-verdict-result .verdict-box")

    eval_calls = [body for path, body in requests if path == "/api/evaluate-item"]
    assert len(eval_calls) == 1
    assert eval_calls[0].get("slot") == "ring2"


def test_lock_mismatch_shows_error_and_records_nothing(dashboard_page: Page, mock_api: Any) -> None:
    mock_api(
        dashboard_page,
        {
            "/api/evaluate-item": {
                "error": "Slot terkunci tidak cocok dengan item",
            }
        },
    )

    dashboard_page.locator('.nav-item[data-tab="tab-gear"]').click()
    dashboard_page.locator("#subtab-view-compare").click()
    dashboard_page.evaluate("import('/js/compare.js').then(m => m.selectSlot('ring2'))")
    dashboard_page.check("#compare-lock-slot")
    dashboard_page.fill("#candidate-textarea", CROSSBOW_ITEM_TEXT)
    dashboard_page.locator("#btn-run-compare").click()

    dashboard_page.wait_for_function(
        "() => document.getElementById('compare-verdict-result').textContent.includes('Slot terkunci tidak cocok dengan item')",
        timeout=5000,
    )

    storage = dashboard_page.evaluate("JSON.parse(localStorage.getItem('poe2_slot_compare_v2_BOMSHAK') || '{}')")
    ring2_data = storage.get("ring2", {})
    assert len(ring2_data.get("history", [])) == 0


def test_lock_without_selected_slot_shows_message_and_skips_request(
    dashboard_page: Page, mock_api: Any
) -> None:
    requests = mock_api(dashboard_page, {})

    dashboard_page.locator('.nav-item[data-tab="tab-gear"]').click()
    dashboard_page.locator("#subtab-view-compare").click()

    # Clear selectedSlot so locking has no slot target
    dashboard_page.evaluate(
        "async () => { const { appState } = await import('/js/state.js'); appState.selectedSlot = null; }"
    )
    dashboard_page.check("#compare-lock-slot")
    dashboard_page.fill("#candidate-textarea", RING_ITEM_TEXT)
    dashboard_page.locator("#btn-run-compare").click()

    # Verify short message is displayed in #compare-verdict-result
    dashboard_page.wait_for_selector(
        "#compare-verdict-result:has-text('Pilih slot dulu untuk mengunci.')"
    )
    result_text = dashboard_page.locator("#compare-verdict-result").inner_text()
    assert "Pilih slot dulu untuk mengunci." in result_text

    # Verify no request was sent to /api/evaluate-item
    eval_calls = [body for path, body in requests if path == "/api/evaluate-item"]
    assert len(eval_calls) == 0


def test_autoscan_records_under_server_slot(dashboard_page: Page, mock_api: Any) -> None:
    dashboard_page.evaluate("import('/js/compare.js').then(m => m.selectSlot('ring1'))")

    sent = False

    def poll_handler(_body: dict[str, Any]) -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {
                "has_new_item": True,
                "slot": "ring2",
                "auto_equip_ok": False,
                "raw_text": RING_ITEM_TEXT,
                "item_name": "Storm Circle",
                "verdict": "EQUIP_NOW",
            }
        return {"has_new_item": False}

    mock_api(dashboard_page, {"/api/clipboard-poll": poll_handler})

    wait_js(
        dashboard_page,
        "async () => { const { appState } = await import('/js/state.js'); return appState.selectedSlot === 'ring2'; }",
        timeout_ms=5000,
    )

    storage = dashboard_page.evaluate("JSON.parse(localStorage.getItem('poe2_slot_compare_v2_BOMSHAK') || '{}')")
    ring2_history = storage.get("ring2", {}).get("history", [])
    assert len(ring2_history) > 0
    assert ring2_history[0].get("slot") == "ring2"


def test_autoscan_does_not_equip_unless_auto_equip_ok(dashboard_page: Page, mock_api: Any) -> None:
    dashboard_page.evaluate("() => { document.getElementById('toggle-autoequip-empty').checked = true; }")

    def poll_handler(_body: dict[str, Any]) -> dict[str, Any]:
        return {
            "has_new_item": True,
            "slot": "helmet",
            "verdict": "REJECT",
            "slot_empty": True,
            "auto_equip_ok": False,
            "raw_text": RING_ITEM_TEXT,
            "item_name": "Storm Circle",
        }

    requests = mock_api(dashboard_page, {"/api/clipboard-poll": poll_handler})

    wait_js(
        dashboard_page,
        "async () => { const { appState } = await import('/js/state.js'); return (appState.slotCompareData.helmet?.history?.length || 0) > 0; }",
        timeout_ms=5000,
    )

    equip_calls = [body for path, body in requests if path == "/api/equip-item"]
    assert len(equip_calls) == 0


def test_autoscan_equips_server_slot_when_ok(dashboard_page: Page, mock_api: Any) -> None:
    dashboard_page.evaluate("() => { document.getElementById('toggle-autoequip-empty').checked = true; }")

    sent = False

    def poll_handler(_body: dict[str, Any]) -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {
                "has_new_item": True,
                "slot": "set2_main_hand",
                "auto_equip_ok": True,
                "verdict": "EQUIP_NOW",
                "raw_text": CROSSBOW_ITEM_TEXT,
                "item_name": "Gloom Piercer",
            }
        return {"has_new_item": False}

    requests = mock_api(
        dashboard_page,
        {
            "/api/clipboard-poll": poll_handler,
            "/api/equip-item": {"success": True},
        },
    )

    import time
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if any(p == "/api/equip-item" for p, _ in requests):
            break
        dashboard_page.wait_for_timeout(100)

    equip_calls = [body for path, body in requests if path == "/api/equip-item"]
    assert len(equip_calls) == 1
    assert equip_calls[0].get("slot") == "set2_main_hand"


def test_detect_slot_uses_item_class_table(dashboard_page: Page) -> None:
    r1 = dashboard_page.evaluate(
        "async () => { const { detectSlotFromItemText } = await import('/js/compare.js'); return detectSlotFromItemText('Item Class: Staves\\nRarity: Normal\\n--------'); }"
    )
    assert r1 == "main_hand"

    r2 = dashboard_page.evaluate(
        "async () => { const { detectSlotFromItemText } = await import('/js/compare.js'); return detectSlotFromItemText('Item Class: Quarterstaves'); }"
    )
    assert r2 == "main_hand"

    r3 = dashboard_page.evaluate(
        "async () => { const { detectSlotFromItemText } = await import('/js/compare.js'); return detectSlotFromItemText('Item Class: Rings'); }"
    )
    assert r3 == "ring1"


def test_detect_slot_talisman_without_item_class_is_weapon(dashboard_page: Page) -> None:
    detect = "async (t) => { const { detectSlotFromItemText } = await import('/js/compare.js'); return detectSlotFromItemText(t[0], t[1]); }"
    text = "Rarity: Rare\nGrim Bite\nRoaring Talisman\n--------"
    assert dashboard_page.evaluate(detect, [text, None]) == "main_hand"
    assert dashboard_page.evaluate(detect, [text, "set2_main_hand"]) == "set2_main_hand"
