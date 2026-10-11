"""E2E test configuration and Playwright harness for the dashboard."""

from __future__ import annotations

import http.server
import json
import threading
import urllib.parse
from pathlib import Path
from typing import Any, Callable

import pytest
from playwright.sync_api import Page, Route, sync_playwright

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"

CANNED_DEFAULTS: dict[str, dict[str, Any]] = {
    "/api/status": {
        "status": "ok",
        "character": {"name": "BOMSHAK", "level": 1, "resistances": {}},
        "objective": {},
        "loadout": {
            "shared_slots": {},
            "weapon_set_1": {},
            "weapon_set_2": {},
        },
    },
    "/api/guides": {"guides": [], "active": {}},
    "/api/account-characters": {"characters": []},
    "/api/clipboard-poll": {"has_new_item": False},
    "/api/get-clipboard": {"clipboard_text": ""},
}


class _DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy HTTP logs during test runs
        pass


@pytest.fixture(scope="session")
def dashboard_server() -> str:
    """Serve dashboard/ static files on a free port in a daemon thread."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}"
    yield url
    server.shutdown()
    server.server_close()


def mock_api(
    page: Page,
    responses: dict[str, dict | Callable[[dict], dict]] | None = None,
) -> list[tuple[str, Any]]:
    """Install a route on page for **/api/** and record all matching requests."""
    active_responses = dict(responses or {})
    recorded: list[tuple[str, Any]] = []

    def handle_route(route: Route) -> None:
        path = urllib.parse.urlparse(route.request.url).path
        body: Any = None
        if route.request.post_data:
            try:
                body = route.request.post_data_json
            except Exception:
                body = route.request.post_data
        recorded.append((path, body))

        resp_val: Any = None
        if path in active_responses:
            resp_val = active_responses[path]
        elif path.lstrip("/") in active_responses:
            resp_val = active_responses[path.lstrip("/")]
        elif route.request.url in active_responses:
            resp_val = active_responses[route.request.url]
        elif path in CANNED_DEFAULTS:
            resp_val = CANNED_DEFAULTS[path]
        else:
            resp_val = {}

        if callable(resp_val):
            call_arg = body if isinstance(body, dict) else {}
            resp_data = resp_val(call_arg)
        else:
            resp_data = resp_val

        status = 200
        if isinstance(resp_data, dict) and "_status" in resp_data:
            resp_data = dict(resp_data)
            status = resp_data.pop("_status")

        route.fulfill(
            status=status,
            content_type="application/json",
            body=json.dumps(resp_data),
        )

    page.route("**/api/**", handle_route)
    return recorded


@pytest.fixture(name="mock_api")
def mock_api_fixture() -> Callable[..., list[tuple[str, Any]]]:
    return mock_api


@pytest.fixture
def dashboard_page(dashboard_server: str) -> Page:
    """Launch headless Chromium, install base API mock, navigate to dashboard."""
    playwright = None
    browser = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
    except Exception as exc:
        if playwright is not None:
            playwright.stop()
        pytest.skip(f"Chromium launch raised: {exc}")

    context = browser.new_context()
    page = context.new_page()

    orig_wait_for_function = page.wait_for_function

    def _async_safe_wait_for_function(expression: str, *args: Any, timeout: float | None = None, **kwargs: Any) -> Any:
        if "async ()" in expression or "async function" in expression:
            import time
            limit_ms = float(timeout) if timeout is not None else 30000.0
            deadline = time.time() + (limit_ms / 1000.0)
            while time.time() < deadline:
                if page.evaluate(f"({expression})()"):
                    return True
                page.wait_for_timeout(100)
            raise TimeoutError(f"Timed out waiting for: {expression}")
        return orig_wait_for_function(expression, *args, timeout=timeout, **kwargs)

    page.wait_for_function = _async_safe_wait_for_function  # type: ignore[assignment]

    mock_api(page, {})
    page.goto(dashboard_server)
    page.wait_for_load_state("domcontentloaded")
    yield page
    context.close()
    browser.close()
    playwright.stop()
