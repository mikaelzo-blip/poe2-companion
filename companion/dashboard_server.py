"""Dashboard launcher and static asset server for PoE2 Companion Suite."""

from __future__ import annotations

import http.server
import json
import logging
from pathlib import Path
import socketserver
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse
import webbrowser
from typing import Any, Callable

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = PROJECT_ROOT / "runtime"
logger = logging.getLogger(__name__)


_GLOBAL_POB_SESSIONS: dict[str, Any] = {}
_FAILED_CHARACTERS: dict[str, float] = {}
POB_RETRY_INTERVAL_SECONDS = 300.0


def normalize_char_id(char_id: str | None) -> str:
    """Normalize character ID case-insensitively against runtime files."""
    from companion.dashboard_api import resolve_char_id
    return resolve_char_id(char_id, RUNTIME_DIR)


def get_or_create_pob_session(character_id: str = "BOMSHAK", force_retry: bool = False):
    """Reuse or lazily initialize the PoB2 simulation session.
    
    Caches successful sessions per character and uses a retry cooldown on failed characters
    to prevent UI stalling and Docker thrashing on 800ms clipboard polls.
    """
    global _GLOBAL_POB_SESSIONS, _FAILED_CHARACTERS
    character_id = normalize_char_id(character_id)
    existing = _GLOBAL_POB_SESSIONS.get(character_id)
    if (
        existing is not None
        and getattr(existing, "character_name", None) == character_id
        and getattr(existing, "is_available", False)
    ):
        return existing
    if existing is not None:
        _GLOBAL_POB_SESSIONS.pop(character_id, None)
        try:
            existing.close()
        except Exception:
            logger.warning("Failed to close stale PoB2 session %s", character_id, exc_info=True)

    now = time.time()
    last_fail = _FAILED_CHARACTERS.get(character_id, 0.0)
    if not force_retry and (now - last_fail < POB_RETRY_INTERVAL_SECONDS):
        return None

    try:
        from companion.equipment.pob2_equipment_advisor import Pob2EquipmentSession
        sess = Pob2EquipmentSession(character_name=character_id)
        if sess.initialize():
            _GLOBAL_POB_SESSIONS[character_id] = sess
            _FAILED_CHARACTERS.pop(character_id, None)
            return sess
        _FAILED_CHARACTERS[character_id] = now
    except Exception:
        logger.warning("PoB2 session init failed for %s", character_id, exc_info=True)
        _FAILED_CHARACTERS[character_id] = now
    return None


_REFRESHING: set[str] = set()
_REFRESH_LOCK = threading.Lock()


def _spawn_daemon(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


def maybe_refresh_pob_session(
    character_id: str,
    level: int | None,
    zone: str | None,
    spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
) -> bool:
    """Re-sync a cached session in the background when stale; True if a refresh was started."""
    sess = _GLOBAL_POB_SESSIONS.get(character_id)
    if sess is None or not sess.needs_refresh(level, zone):
        return False
    with _REFRESH_LOCK:
        if character_id in _REFRESHING:
            return False
        _REFRESHING.add(character_id)

    def run() -> None:
        try:
            sess.sync_character()
        except Exception:
            logger.warning("PoB2 refresh failed for %s", character_id, exc_info=True)
        finally:
            with _REFRESH_LOCK:
                _REFRESHING.discard(character_id)

    try:
        spawn(run)
    except Exception:
        with _REFRESH_LOCK:
            _REFRESHING.discard(character_id)
        raise
    return True


def sync_equipped_item_to_pob_session(character_id: str, slot: str, raw_text: str) -> bool:
    """Synchronize an equipped item directly into the active PoB2 session."""
    global _GLOBAL_POB_SESSIONS
    sess = _GLOBAL_POB_SESSIONS.get(character_id)
    if (
        sess is not None
        and getattr(sess, "character_name", None) == character_id
        and getattr(sess, "is_available", False)
    ):
        try:
            return sess.equip_item(slot, raw_text)
        except Exception:
            pass
    return False


def invalidate_pob_session(character_id: str | None = None) -> None:
    """Invalidate or reset the cached PoB2 session so it will re-initialize on next use."""
    global _GLOBAL_POB_SESSIONS, _FAILED_CHARACTERS
    if character_id:
        sess = _GLOBAL_POB_SESSIONS.get(character_id)
        if sess is not None:
            try:
                sess.sync_character()
            except Exception:
                logger.warning("PoB2 sync failed for %s", character_id, exc_info=True)
        _FAILED_CHARACTERS.pop(character_id, None)
    else:
        for sess in list(_GLOBAL_POB_SESSIONS.values()):
            try:
                sess.close()
            except Exception:
                logger.warning("Failed to close PoB2 session", exc_info=True)
        _GLOBAL_POB_SESSIONS.clear()
        _FAILED_CHARACTERS.clear()


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler providing static files and Companion Suite APIs."""
    protocol_version = "HTTP/1.1"
    # ES modules require a JS MIME type; the Windows registry can map .js to text/plain.
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def __init__(self, *args, directory: str | None = None, **kwargs) -> None:
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except ConnectionError:
            self.close_connection = True

    def send_json(self, data: Any, status: int = 200) -> None:
        """Send JSON response; drop cleanly if client already disconnected."""
        try:
            res_bytes = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(res_bytes)))
            self.end_headers()
            self.wfile.write(res_bytes)
        except ConnectionError:
            self.close_connection = True

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress routine high-frequency polling requests to prevent terminal spam."""
        if args and isinstance(args[0], str):
            req = args[0]
            if "/api/status" in req or "/api/clipboard-poll" in req:
                return
        super().log_message(format, *args)

    def end_headers(self) -> None:
        if any(self.path.endswith(ext) for ext in (".js", ".css", ".html")) or self.path in ("/", ""):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def _request_allowed(self, check_origin: bool = False) -> bool:
        """Block DNS rebinding (bad Host) and cross-site POSTs (foreign Origin)."""
        hosts = ("localhost", "127.0.0.1", "::1")
        host = urlparse("//" + self.headers.get("Host", "")).hostname
        origin = self.headers.get("Origin") if check_origin else None
        if host in hosts and (origin is None or urlparse(origin).hostname in hosts):
            return True
        self.close_connection = True  # unread POST body must not poison keep-alive
        self.send_json({"error": "forbidden"}, 403)
        return False

    def _dispatch(self, compute: Callable[[], Any]) -> None:
        try:
            self.send_json(compute())
        except ConnectionError:
            return
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_GET(self) -> None:
        path, _, query = self.path.partition("?")
        if path.startswith("/api/"):
            if not self._request_allowed():
                return
            route = GET_ROUTES.get(path)
            if route is None:
                self.send_json({"error": "not found"}, 404)
                return
            params = {k: v[0] for k, v in parse_qs(query).items()}
            self._dispatch(lambda: route(params))
            return
        if path in ("/", ""):
            self.path = "/index.html"
        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        return super().do_GET()

    def do_POST(self) -> None:
        if not self._request_allowed(check_origin=True):
            return
        route = POST_ROUTES.get(self.path)
        if route is None:
            self.close_connection = True  # unread POST body must not poison keep-alive
            self.send_response(404)
            self.end_headers()
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._dispatch(lambda: route(json.loads(body.decode("utf-8")) if body else {}))


def _api_status(q: dict[str, str]) -> Any:
    from companion.dashboard_api import get_dashboard_status
    char_id = normalize_char_id(q.get("char_id"))
    data = get_dashboard_status(RUNTIME_DIR, char_id=char_id, pob_session=get_or_create_pob_session(char_id))
    character = data.get("character") if isinstance(data, dict) else None
    if isinstance(character, dict):
        from companion.dashboard_api import character_level_and_zone
        maybe_refresh_pob_session(char_id, *character_level_and_zone(character))
    return data


def _api_clipboard_poll(q: dict[str, str]) -> Any:
    from companion.dashboard_api import check_auto_clipboard
    char_id = normalize_char_id(q.get("char_id"))
    return check_auto_clipboard(
        runtime_dir=RUNTIME_DIR,
        char_id=char_id,
        stage_str=q.get("stage", "lvl 1-14"),
        pob_session=None,
        guide=q.get("guide"),
        zone=q.get("zone"),
        pob_session_resolver=lambda: get_or_create_pob_session(char_id),
    )


def _api_account_characters(q: dict[str, str]) -> Any:
    from companion.dashboard_api import get_account_characters
    return get_account_characters(account_name=q.get("account", "mikaelzo#5674"), runtime_dir=RUNTIME_DIR)


def _api_guides(q: dict[str, str]) -> Any:
    from companion.dashboard_api import get_available_guides
    return get_available_guides()


def _api_get_clipboard(q: dict[str, str]) -> Any:
    from companion.equipment.clipboard import get_clipboard_text
    return {"clipboard_text": get_clipboard_text().strip()}


def _api_evaluate_item(payload: dict[str, Any]) -> Any:
    from companion.dashboard_api import evaluate_item_payload
    char_id = payload["character_id"] = normalize_char_id(payload.get("character_id"))
    pob = get_or_create_pob_session(char_id, force_retry=True)
    return evaluate_item_payload(payload, runtime_dir=RUNTIME_DIR, pob_session=pob)


def _api_equip_item(payload: dict[str, Any]) -> Any:
    from companion.dashboard_api import update_loadout_item_payload
    result = update_loadout_item_payload(payload, runtime_dir=RUNTIME_DIR)
    if result.get("success"):
        target_slot = result.get("slot") or payload.get("slot")
        raw_text = payload.get("raw_text")
        if target_slot and raw_text:
            sync_equipped_item_to_pob_session(normalize_char_id(payload.get("character_id")), target_slot, raw_text)
    return result


def _api_import_character(payload: dict[str, Any]) -> Any:
    from companion.dashboard_api import import_character_payload
    result = import_character_payload(payload, runtime_dir=RUNTIME_DIR)
    if result.get("success"):
        invalidate_pob_session(normalize_char_id(payload.get("character_id")))
    return result


def _api_update_stats(payload: dict[str, Any]) -> Any:
    from companion.dashboard_api import update_character_stats_payload
    result = update_character_stats_payload(payload, runtime_dir=RUNTIME_DIR)
    if result.get("success"):
        invalidate_pob_session(normalize_char_id(payload.get("character_id")))
    return result


def _api_select_character(payload: dict[str, Any]) -> Any:
    from companion.dashboard_api import select_character_payload
    result = select_character_payload(payload, runtime_dir=RUNTIME_DIR)
    new_char = result.get("active_character_id") if result.get("success") else None
    if new_char:
        threading.Thread(
            target=get_or_create_pob_session,
            args=(new_char,),
            daemon=True,
            name=f"PoB2-Prewarm-{new_char}",
        ).start()
    return result


def _api_fetch_public_profile(payload: dict[str, Any]) -> Any:
    from companion.dashboard_api import fetch_public_profile
    character_id = payload.get("character_id", "BOMSHAK")
    result = fetch_public_profile(
        payload.get("account_name", ""),
        character_id,
        runtime_dir=RUNTIME_DIR,
        overwrite=payload.get("overwrite", True),
    )
    if result.get("success"):
        invalidate_pob_session(normalize_char_id(character_id))
    return result


GET_ROUTES: dict[str, Callable[[dict[str, str]], Any]] = {
    "/api/status": _api_status,
    "/api/clipboard-poll": _api_clipboard_poll,
    "/api/account-characters": _api_account_characters,
    "/api/guides": _api_guides,
    "/api/get-clipboard": _api_get_clipboard,
}

POST_ROUTES: dict[str, Callable[[dict[str, Any]], Any]] = {
    "/api/evaluate-item": _api_evaluate_item,
    "/api/equip-item": _api_equip_item,
    "/api/import-character": _api_import_character,
    "/api/update-stats": _api_update_stats,
    "/api/select-character": _api_select_character,
    "/api/fetch-public-profile": _api_fetch_public_profile,
}


# Alias for backward compatibility
CustomHandler = DashboardRequestHandler


class ThreadingDashboardServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, ConnectionError):
            return
        super().handle_error(request, client_address)


def serve_dashboard(port: int = 8080, open_browser: bool = True) -> None:
    """Start local HTTP server for dashboard without external dependencies."""
    try:
        # Pre-warm PoB2 session in background thread
        active_char_path = RUNTIME_DIR / "active_character.json"
        char_to_warm = "BOMSHAK"
        if active_char_path.is_file():
            try:
                cdata = json.loads(active_char_path.read_text(encoding="utf-8"))
                char_to_warm = cdata.get("active_character_id") or "BOMSHAK"
            except Exception:
                pass
        threading.Thread(
            target=get_or_create_pob_session,
            args=(char_to_warm,),
            daemon=True,
            name="PoB2-Prewarm",
        ).start()
    except Exception:
        pass

    try:
        httpd = ThreadingDashboardServer(("127.0.0.1", port), DashboardRequestHandler)
    except OSError:
        url = f"http://localhost:{port}"
        is_our_dashboard = False
        try:
            import urllib.request
            with urllib.request.urlopen(f"{url}/api/get-clipboard", timeout=1) as resp:
                if resp.status == 200:
                    is_our_dashboard = True
        except Exception:
            pass

        if is_our_dashboard:
            print(f"Dashboard PoE2 Companion sudah aktif berjalan di latar belakang: {url}")
            if open_browser:
                webbrowser.open(url)
            return

        # Port used by another process, try port + 1
        alt_port = port + 1
        try:
            httpd = ThreadingDashboardServer(("127.0.0.1", alt_port), DashboardRequestHandler)
            port = alt_port
        except OSError:
            print(f"Error: Port {port} dan {alt_port} sudah digunakan oleh proses lain.")
            print(f"Gunakan perintah: uv run python -m companion.cli dashboard --port <nomor_port>")
            return

    with httpd:
        url = f"http://localhost:{port}"
        print(f"PoE2 Hermes Companion Suite Dashboard aktif di: {url}")
        print("Tekan Ctrl+C untuk berhenti.")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard server dihentikan.")
