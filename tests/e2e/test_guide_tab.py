"""E2E tests for the guide tab breaker-rule editor and re-import link."""

from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import Page

SAMPLE_FUBGUN_GUIDE = {
    "slug": "fubgun-flameblast-oil-grenade",
    "name": "0.5.5 Fubgun Flameblast Oil Grenade",
    "source_url": "https://mobalytics.gg/poe-2/builds/fubgun-flameblast-oil-grenade",
    "has_pob": True,
    "stages": [{"id": "s1", "title": "lvl 1-14"}],
    "breaker_rules": [
        {
            "pattern": r"adds .*fire damage to attacks",
            "from_level": 52,
            "exclude_slots": ["Weapon 1", "Weapon 2"],
            "reason": "Fire damage ke Attack menyalakan Oil Grenade terlalu cepat",
        }
    ],
}


def _open_guide_tab(page: Page) -> None:
    page.locator("#btn-open-sync-modal").click()
    page.locator("#mtab-guides").click()
    page.wait_for_selector("#guide-list")


def test_rule_editor_add_and_save_posts_full_list(dashboard_page: Page, mock_api: Any) -> None:
    requests = mock_api(
        dashboard_page,
        {
            "/api/guides": {
                "guides": [SAMPLE_FUBGUN_GUIDE],
                "active": {"guide": SAMPLE_FUBGUN_GUIDE["slug"], "stage_override": None},
            },
            "/api/guides/rules": {"success": True},
        },
    )

    _open_guide_tab(dashboard_page)

    # Click Aturan toggle button to expand editor
    toggle_btn = dashboard_page.locator("button:has-text('Aturan (1)')")
    toggle_btn.click()

    # Fill add rule form
    dashboard_page.locator(".rule-input-pattern").fill(r"gain .*as extra fire damage")
    dashboard_page.locator(".rule-input-from-level").fill("60")
    dashboard_page.locator(".rule-input-exclude-slots").fill("Gloves, Boots")
    dashboard_page.locator(".rule-input-reason").fill("Extra fire reason")

    # Click Simpan aturan
    dashboard_page.locator("button:has-text('Simpan aturan')").click()

    # Poll requests until /api/guides/rules is recorded
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if any(p == "/api/guides/rules" for p, _ in requests):
            break
        dashboard_page.wait_for_timeout(100)

    # Assert recorded /api/guides/rules body
    rule_posts = [body for path, body in requests if path == "/api/guides/rules"]
    assert len(rule_posts) == 1
    post_body = rule_posts[0]
    assert post_body["slug"] == "fubgun-flameblast-oil-grenade"
    assert len(post_body["rules"]) == 2

    # Existing rule preserved
    r1 = post_body["rules"][0]
    assert r1["pattern"] == r"adds .*fire damage to attacks"
    assert r1["from_level"] == 52
    assert r1["exclude_slots"] == ["Weapon 1", "Weapon 2"]
    assert "Oil Grenade" in r1["reason"]

    # Newly added rule
    r2 = post_body["rules"][1]
    assert r2["pattern"] == r"gain .*as extra fire damage"
    assert r2["from_level"] == 60
    assert isinstance(r2["from_level"], int)
    assert r2["exclude_slots"] == ["Gloves", "Boots"]
    assert isinstance(r2["exclude_slots"], list)
    assert r2["reason"] == "Extra fire reason"


def test_rule_editor_invalid_regex_keeps_rules(dashboard_page: Page, mock_api: Any) -> None:
    error_msg = "Pola regex tidak valid: missing ), unterminated subpattern at position 9"
    mock_api(
        dashboard_page,
        {
            "/api/guides": {
                "guides": [SAMPLE_FUBGUN_GUIDE],
                "active": {"guide": SAMPLE_FUBGUN_GUIDE["slug"], "stage_override": None},
            },
            "/api/guides/rules": {"error": error_msg},
        },
    )

    _open_guide_tab(dashboard_page)

    # Click Aturan toggle button
    dashboard_page.locator("button:has-text('Aturan (1)')").click()

    # Fill invalid regex
    dashboard_page.locator(".rule-input-pattern").fill("[invalid(")
    dashboard_page.locator(".rule-input-from-level").fill("50")
    dashboard_page.locator(".rule-input-reason").fill("Bad pattern rule")

    # Save
    dashboard_page.locator("button:has-text('Simpan aturan')").click()

    # Error is shown verbatim
    dashboard_page.wait_for_selector(f"text={error_msg}")
    container_text = dashboard_page.locator("#guide-list").inner_text()
    assert error_msg in container_text

    # The rendered list still has the original rule
    assert "adds .*fire damage to attacks" in container_text
    assert "Fire damage ke Attack menyalakan Oil Grenade terlalu cepat" in container_text

    # Unsaved input is preserved so user can fix the typo
    assert dashboard_page.locator(".rule-input-pattern").input_value() == "[invalid("
    assert dashboard_page.locator(".rule-input-from-level").input_value() == "50"
    assert dashboard_page.locator(".rule-input-reason").input_value() == "Bad pattern rule"


def test_reimport_link_points_to_source_url(dashboard_page: Page, mock_api: Any) -> None:
    guide_without_url = {
        "slug": "custom-local-guide",
        "name": "Custom Local Guide",
        "source_url": None,
        "has_pob": False,
        "stages": [{"id": "s1", "title": "lvl 1-10"}],
        "breaker_rules": [],
    }

    mock_api(
        dashboard_page,
        {
            "/api/guides": {
                "guides": [SAMPLE_FUBGUN_GUIDE, guide_without_url],
                "active": {},
            },
        },
    )

    _open_guide_tab(dashboard_page)

    # Link for guide with source_url exists and has correct attributes
    reimport_link = dashboard_page.locator("a:has-text('Buka halaman guide')")
    assert reimport_link.count() == 1
    assert reimport_link.get_attribute("href") == SAMPLE_FUBGUN_GUIDE["source_url"]
    assert reimport_link.get_attribute("target") == "_blank"
    assert reimport_link.get_attribute("rel") == "noopener"


def test_rule_editor_delete_rule_updates_list_and_count(dashboard_page: Page, mock_api: Any) -> None:
    mock_api(
        dashboard_page,
        {
            "/api/guides": {
                "guides": [SAMPLE_FUBGUN_GUIDE],
                "active": {},
            },
            "/api/guides/rules": {"success": True},
        },
    )

    _open_guide_tab(dashboard_page)
    dashboard_page.locator("button:has-text('Aturan (1)')").click()
    dashboard_page.locator(".btn-del-rule").click()
    assert dashboard_page.locator("button:has-text('Aturan (0)')").is_visible()


def test_rule_editor_failed_save_keeps_local_deletion(dashboard_page: Page, mock_api: Any) -> None:
    guide_with_two_rules = {
        **SAMPLE_FUBGUN_GUIDE,
        "breaker_rules": [
            SAMPLE_FUBGUN_GUIDE["breaker_rules"][0],
            {
                "pattern": r"dummy pattern to delete",
                "from_level": 1,
                "exclude_slots": [],
                "reason": "Dummy reason",
            },
        ],
    }
    error_msg = "Pola regex tidak valid"
    mock_api(
        dashboard_page,
        {
            "/api/guides": {
                "guides": [guide_with_two_rules],
                "active": {"guide": guide_with_two_rules["slug"], "stage_override": None},
            },
            "/api/guides/rules": {"error": error_msg},
        },
    )

    _open_guide_tab(dashboard_page)
    dashboard_page.locator("button:has-text('Aturan (2)')").click()

    # Delete the second rule locally
    dashboard_page.locator(".btn-del-rule").nth(1).click()
    assert dashboard_page.locator("button:has-text('Aturan (1)')").is_visible()

    # Attempt to save with invalid regex
    dashboard_page.locator(".rule-input-pattern").fill("[broken(")
    dashboard_page.locator("button:has-text('Simpan aturan')").click()

    # Error is shown
    dashboard_page.wait_for_selector(f"text={error_msg}")

    # Local deletion is kept: count is still 1 and deleted rule is NOT resurrected
    assert dashboard_page.locator("button:has-text('Aturan (1)')").is_visible()
    container_text = dashboard_page.locator("#guide-list").inner_text()
    assert "dummy pattern to delete" not in container_text


def test_select_character_error_is_shown(dashboard_page: Page, mock_api: Any) -> None:
    mock_api(
        dashboard_page,
        {
            "/api/account-characters": {
                "characters": [
                    {"name": "BOMSHAK", "level": 37, "class": "Mercenary"},
                    {"name": "ALTCHAR", "level": 12, "class": "Ranger"},
                ],
                "active_character_id": "BOMSHAK",
            },
            "/api/select-character": {
                "_status": 500,
                "error": "Gagal mengganti ke ALTCHAR",
            },
        },
    )

    dashboard_page.reload()
    dashboard_page.wait_for_selector("#header-char-select")
    dashboard_page.wait_for_function("() => Array.from(document.querySelectorAll('#header-char-select option')).some(o => o.value === 'ALTCHAR')")
    dashboard_page.select_option("#header-char-select", "ALTCHAR")

    dashboard_page.wait_for_selector("#guide-error:has-text('Gagal mengganti ke ALTCHAR')")
    err_text = dashboard_page.locator("#guide-error").inner_text()
    assert "Gagal mengganti ke ALTCHAR" in err_text

    # Dropdown and appState revert to BOMSHAK on failure
    assert dashboard_page.locator("#header-char-select").input_value() == "BOMSHAK"
    active_char = dashboard_page.evaluate(
        "async () => { const { appState } = await import('/js/state.js'); return appState.activeCharId; }"
    )
    assert active_char == "BOMSHAK"
