"""Dashboard launcher and static asset server for PoE2 Companion Suite."""

from __future__ import annotations

import http.server
import json
import os
from pathlib import Path
import socketserver
import sys
import time
import webbrowser
from typing import Any

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


_GLOBAL_POB_SESSION: Any = None
_GLOBAL_POB_SESSIONS: dict[str, Any] = {}
_FAILED_CHARACTERS: dict[str, float] = {}
POB_RETRY_INTERVAL_SECONDS = 300.0


def normalize_char_id(char_id: str | None) -> str:
    """Normalize character ID case-insensitively against runtime files."""
    if not char_id:
        return "BOMSHAK"
    raw = char_id.strip()
    chars_dir = PROJECT_ROOT / "runtime" / "characters"
    if chars_dir.is_dir():
        for f in chars_dir.glob("*.json"):
            if f.stem.lower() == raw.lower():
                return f.stem
    return raw


def get_or_create_pob_session(character_id: str = "BOMSHAK", force_retry: bool = False):
    """Reuse or lazily initialize the PoB2 simulation session.
    
    Caches successful sessions per character and uses a retry cooldown on failed characters
    to prevent UI stalling and Docker thrashing on 800ms clipboard polls.
    """
    global _GLOBAL_POB_SESSION, _GLOBAL_POB_SESSIONS, _FAILED_CHARACTERS
    character_id = normalize_char_id(character_id)
    if (
        _GLOBAL_POB_SESSION is not None
        and getattr(_GLOBAL_POB_SESSION, "character_name", None) == character_id
        and getattr(_GLOBAL_POB_SESSION, "is_available", False)
    ):
        return _GLOBAL_POB_SESSION

    existing = _GLOBAL_POB_SESSIONS.get(character_id)
    if (
        existing is not None
        and getattr(existing, "character_name", None) == character_id
        and getattr(existing, "is_available", False)
    ):
        return existing

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
        _FAILED_CHARACTERS[character_id] = now
    return None


def sync_equipped_item_to_pob_session(character_id: str, slot: str, raw_text: str) -> bool:
    """Synchronize an equipped item directly into the active PoB2 session."""
    global _GLOBAL_POB_SESSION, _GLOBAL_POB_SESSIONS
    if (
        _GLOBAL_POB_SESSION is not None
        and getattr(_GLOBAL_POB_SESSION, "character_name", None) == character_id
        and getattr(_GLOBAL_POB_SESSION, "is_available", False)
    ):
        try:
            return _GLOBAL_POB_SESSION.equip_item(slot, raw_text)
        except Exception:
            pass

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
    global _GLOBAL_POB_SESSION, _GLOBAL_POB_SESSIONS, _FAILED_CHARACTERS
    if _GLOBAL_POB_SESSION is not None:
        if character_id is None or getattr(_GLOBAL_POB_SESSION, "character_name", None) == character_id:
            try:
                _GLOBAL_POB_SESSION.sync_character()
            except Exception:
                _GLOBAL_POB_SESSION = None
    if character_id:
        sess = _GLOBAL_POB_SESSIONS.pop(character_id, None)
        if sess is not None:
            try:
                sess.sync_character()
            except Exception:
                pass
        _FAILED_CHARACTERS.pop(character_id, None)
    else:
        _GLOBAL_POB_SESSION = None
        _GLOBAL_POB_SESSIONS.clear()
        _FAILED_CHARACTERS.clear()


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler providing static files and Companion Suite APIs."""
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, directory: str | None = None, **kwargs) -> None:
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

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

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "":
            self.path = "/dashboard/index.html"
        elif self.path.startswith("/style.css"):
            self.path = "/dashboard/style.css"
        elif self.path.startswith("/app.js"):
            self.path = "/dashboard/app.js"
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        elif self.path.startswith("/api/status"):
            try:
                from urllib.parse import urlparse, parse_qs
                from companion.dashboard_api import get_dashboard_status
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                char_id = normalize_char_id(params.get("char_id", [None])[0])
                pob_sess = get_or_create_pob_session(char_id) if char_id else None

                data = get_dashboard_status(PROJECT_ROOT / "runtime", char_id=char_id, pob_session=pob_sess)
                self.send_json(data)
            except ConnectionError:
                return
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        elif self.path.startswith("/api/clipboard-poll"):
            try:
                from urllib.parse import urlparse, parse_qs
                from companion.dashboard_api import check_auto_clipboard
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                char_id = normalize_char_id(params.get("char_id", ["BOMSHAK"])[0])
                stage = params.get("stage", ["lvl 1-14"])[0]
                guide = params.get("guide", [None])[0]
                zone = params.get("zone", [None])[0]

                result = check_auto_clipboard(
                    runtime_dir=PROJECT_ROOT / "runtime",
                    char_id=char_id,
                    stage_str=stage,
                    pob_session=None,
                    guide=guide,
                    zone=zone,
                    pob_session_resolver=lambda: get_or_create_pob_session(char_id),
                )
                self.send_json(result)
            except ConnectionError:
                return
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        elif self.path.startswith("/api/account-characters"):
            try:
                from urllib.parse import urlparse, parse_qs
                from companion.dashboard_api import get_account_characters
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                account_name = params.get("account", ["mikaelzo#5674"])[0]
                result = get_account_characters(account_name=account_name, runtime_dir=PROJECT_ROOT / "runtime")
                self.send_json(result)
            except ConnectionError:
                return
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        elif self.path.startswith("/api/guides"):
            try:
                from companion.dashboard_api import get_available_guides
                result = get_available_guides()
                self.send_json(result)
            except ConnectionError:
                return
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        elif self.path == "/api/get-clipboard":
            try:
                from companion.equipment.clipboard import get_clipboard_text
                text = get_clipboard_text().strip()
                self.send_json({"clipboard_text": text})
            except ConnectionError:
                return
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/evaluate-item":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
                from companion.dashboard_api import evaluate_item_payload
                char_id = normalize_char_id(payload.get("character_id", "BOMSHAK"))
                payload["character_id"] = char_id
                pob = get_or_create_pob_session(char_id, force_retry=True)
                result = evaluate_item_payload(
                    payload,
                    runtime_dir=PROJECT_ROOT / "runtime",
                    pob_session=pob,
                )
                res_bytes = json.dumps(result).encode("utf-8")
                self.send_json(result)
            except ConnectionError:
                return
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        elif self.path == "/api/equip-item":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
                from companion.dashboard_api import update_loadout_item_payload
                result = update_loadout_item_payload(payload, runtime_dir=PROJECT_ROOT / "runtime")
                if result.get("success"):
                    char_id = payload.get("character_id", "BOMSHAK")
                    target_slot = result.get("slot") or payload.get("slot")
                    raw_text = payload.get("raw_text")
                    if target_slot and raw_text:
                        sync_equipped_item_to_pob_session(char_id, target_slot, raw_text)
                self.send_json(result)
            except ConnectionError:
                return
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        elif self.path == "/api/import-character":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
                from companion.dashboard_api import import_character_payload
                result = import_character_payload(payload, runtime_dir=PROJECT_ROOT / "runtime")
                if result.get("success"):
                    char_id = payload.get("character_id", "BOMSHAK")
                    invalidate_pob_session(char_id)
                self.send_json(result)
            except ConnectionError:
                return
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        elif self.path == "/api/update-stats":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
                from companion.dashboard_api import update_character_stats_payload
                result = update_character_stats_payload(payload, runtime_dir=PROJECT_ROOT / "runtime")
                if result.get("success"):
                    char_id = payload.get("character_id", "BOMSHAK")
                    invalidate_pob_session(char_id)
                self.send_json(result)
            except ConnectionError:
                return
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        elif self.path == "/api/select-character":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
                from companion.dashboard_api import select_character_payload
                result = select_character_payload(payload, runtime_dir=PROJECT_ROOT / "runtime")
                if result.get("success"):
                    new_char = result.get("active_character_id")
                    if new_char:
                        import threading
                        threading.Thread(
                            target=get_or_create_pob_session,
                            args=(new_char,),
                            daemon=True,
                            name=f"PoB2-Prewarm-{new_char}",
                        ).start()
                self.send_json(result)
            except ConnectionError:
                return
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        elif self.path == "/api/fetch-public-profile":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
                account_name = payload.get("account_name", "")
                character_id = payload.get("character_id", "BOMSHAK")
                overwrite = payload.get("overwrite", True)
                from companion.dashboard_api import fetch_public_profile
                result = fetch_public_profile(account_name, character_id, runtime_dir=PROJECT_ROOT / "runtime", overwrite=overwrite)
                if result.get("success"):
                    invalidate_pob_session(character_id)
                self.send_json(result)
            except ConnectionError:
                return
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return

        self.send_response(404)
        self.end_headers()


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
    # Serve from project root so both /dashboard and /runtime are accessible via HTTP
    os.chdir(PROJECT_ROOT)

    try:
        # Pre-warm PoB2 session in background thread
        import threading
        active_char_path = PROJECT_ROOT / "runtime" / "active_character.json"
        char_to_warm = "BOMSHAK"
        if active_char_path.is_file():
            import json
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
        httpd = ThreadingDashboardServer(("", port), DashboardRequestHandler)
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
            httpd = ThreadingDashboardServer(("", alt_port), DashboardRequestHandler)
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
