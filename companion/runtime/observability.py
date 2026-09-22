"""Structured low-noise console observability for continuous runtime."""

from __future__ import annotations

from datetime import datetime, timezone
import sys


class RuntimeConsoleFormatter:
    """Formats structured runtime events with standardized tags."""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def format_session(self, msg: str) -> str:
        return f"[{self._now()}] [SESSION] {msg}"

    def format_zone(self, zone: str, is_safe: bool = False) -> str:
        safe_str = " (Safe Zone)" if is_safe else " (Combat)"
        return f"[{self._now()}] [ZONE] {zone}{safe_str}"

    def format_level(self, char_name: str, level: int) -> str:
        return f"[{self._now()}] [LEVEL] {char_name} reached level {level}!"

    def format_objective(self, title: str) -> str:
        return f"[{self._now()}] [OBJECTIVE] Next: {title}"

    def format_notify(self, msg: str) -> str:
        return f"[{self._now()}] [NOTIFY] {msg}"

    def format_backfill(self, msg: str) -> str:
        return f"[{self._now()}] [BACKFILL] {msg}"

    def format_crash_recovery(self, msg: str) -> str:
        return f"[{self._now()}] [CRASH RECOVERY] {msg}"

    def log(self, formatted_line: str) -> None:
        """Write formatted line to stdout."""
        print(formatted_line, flush=True)

    def log_debug(self, msg: str) -> None:
        """Write debug line if verbose mode is enabled."""
        if self.verbose:
            print(f"[{self._now()}] [DEBUG] {msg}", flush=True)
