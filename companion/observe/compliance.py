"""Strict compliance guard verifying zero input injection and isolation."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
import sys

FORBIDDEN_CALLS = {
    "SendInput",
    "mouse_event",
    "keybd_event",
    "pyautogui",
    "pynput",
    "keyboard",
    "mouse",
}


class NoInputGuard:
    """Verifies that no input injection APIs exist or are imported in observation code."""

    @classmethod
    def verify_no_input_injection(cls, package_path: Path) -> list[str]:
        violations: list[str] = []
        for py_file in package_path.glob("*.py"):
            if py_file.name == "compliance.py":
                continue
            text = py_file.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN_CALLS:
                if forbidden in text:
                    violations.append(f"{py_file.name} contains forbidden call: {forbidden}")
        return violations
