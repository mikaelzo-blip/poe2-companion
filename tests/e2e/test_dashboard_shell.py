"""E2E tests for the dashboard shell structure and tab navigation."""

from __future__ import annotations

from playwright.sync_api import Page


def test_no_transition_tab_and_no_console_errors(dashboard_page: Page) -> None:
    errors: list[str] = []
    dashboard_page.on(
        "console",
        lambda msg: errors.append(f"console: {msg.text}") if msg.type == "error" else None,
    )
    dashboard_page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

    # Assert transition tab nav-item and section do not exist
    assert dashboard_page.locator('.nav-item[data-tab="tab-transition"]').count() == 0
    assert dashboard_page.locator("#tab-transition").count() == 0

    # Click every remaining nav-item and ensure no console errors
    nav_items = dashboard_page.locator(".nav-item")
    count = nav_items.count()
    assert count > 0
    for i in range(count):
        nav_items.nth(i).click()
        dashboard_page.wait_for_timeout(50)

    assert errors == []
