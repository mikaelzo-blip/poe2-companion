"""E2E tests: overview shows zero-valued facts, and the stats modal never invents numbers."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Page


def _fact(value: Any) -> dict[str, Any]:
    return {"value": value, "source": "DEFAULT_INIT"}


def _status(character: dict[str, Any], baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": {},
        "character": character,
        "objective": {},
        "loadout": {"shared_slots": {}, "weapon_set_1": {}, "weapon_set_2": {}},
        "baseline": baseline or {},
        "active_character_id": character["character_id"],
    }


def test_zero_death_count_is_shown_as_zero(dashboard_page: Page, mock_api: Any) -> None:
    mock_api(dashboard_page, {"/api/status": _status({
        "character_id": "NEWCHAR", "character_name": "NEWCHAR",
        "level": _fact(3), "death_count": _fact(0), "current_zone": _fact("G1_2"),
    })})
    dashboard_page.reload()
    dashboard_page.wait_for_function("() => document.getElementById('stat-level').textContent === '3'")
    assert dashboard_page.locator("#stat-deaths").inner_text() == "0"
    assert dashboard_page.locator("#stat-zone").inner_text() == "G1_2"


def test_stats_modal_prefills_real_values_and_sends_null_for_unknown(dashboard_page: Page, mock_api: Any) -> None:
    requests = mock_api(dashboard_page, {
        "/api/status": _status(
            {"character_id": "NEWCHAR", "character_name": "NEWCHAR", "level": _fact(12),
             "attributes": {"strength": _fact(0)}},
            {"life": {"value": 410}},
        ),
        "/api/update-stats": {"success": True, "message": "ok"},
    })
    dashboard_page.reload()
    dashboard_page.wait_for_function("() => document.getElementById('stat-level').textContent === '12'")
    dashboard_page.click("#btn-open-stats-modal")

    assert dashboard_page.input_value("#stat-edit-char-name") == "NEWCHAR"
    assert dashboard_page.input_value("#stat-edit-level") == "12"
    assert dashboard_page.input_value("#stat-edit-str") == "0"
    assert dashboard_page.input_value("#stat-edit-life") == "410"
    assert dashboard_page.input_value("#stat-edit-armour") == ""  # unknown: no sample number

    dashboard_page.click("#btn-save-character-stats")
    dashboard_page.wait_for_function("() => document.getElementById('stat-save-msg').textContent.includes('ok')")
    body = next(b for p, b in requests if p == "/api/update-stats")
    assert body["character_id"] == "NEWCHAR"
    assert (body["level"], body["strength"], body["life"]) == (12, 0, 410)
    assert body["armour"] is None and body["fire_res"] is None
