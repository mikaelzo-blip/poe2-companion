"""Passive platform clipboard reader."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def _read_win32_clipboard() -> str:
    """Read Windows unicode clipboard text passively via ctypes user32."""
    try:
        import ctypes
        from ctypes import wintypes
        import time

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        # Retry OpenClipboard up to 5 times in case another process (e.g. PoE2) has it momentarily open.
        opened = False
        for _ in range(5):
            if user32.OpenClipboard(None):
                opened = True
                break
            time.sleep(0.015)

        if not opened:
            return ""
        try:
            h_data = user32.GetClipboardData(13)  # CF_UNICODETEXT
            if not h_data:
                return ""
            p_data = kernel32.GlobalLock(h_data)
            if not p_data:
                return ""
            try:
                return ctypes.wstring_at(p_data)
            finally:
                kernel32.GlobalUnlock(h_data)
        finally:
            user32.CloseClipboard()
    except Exception:
        return ""


def _read_os_clipboard() -> str:
    """Read text from platform clipboard passively without simulating inputs."""
    # Fast native Windows clipboard reader
    if sys.platform == "win32":
        return _read_win32_clipboard()

    # Linux / macOS fallback using cli tools (avoid GUI toolkit loops like Tkinter in background servers)
    if sys.platform == "darwin":
        try:
            res = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass
    else:
        # Linux xclip / wl-paste
        for cmd in (["wl-paste"], ["xclip", "-selection", "clipboard", "-o"]):
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    return res.stdout
            except Exception:
                continue

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

