"""Unit tests for runtime console observability formatting."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from companion.runtime.models import RuntimeConfig
from companion.runtime.observability import RuntimeConsoleFormatter
from companion.runtime.orchestrator import ContinuousRuntimeOrchestrator


def test_console_formatter_tags() -> None:
    formatter = RuntimeConsoleFormatter()

    line_session = formatter.format_session("PoE2 launched (PID: 1234)")
    assert "[SESSION]" in line_session
    assert "PoE2 launched (PID: 1234)" in line_session

    line_zone = formatter.format_zone("The Mud Flats", is_safe=False)
    assert "[ZONE]" in line_zone
    assert "The Mud Flats" in line_zone

    line_level = formatter.format_level("Witch", 5)
    assert "[LEVEL]" in line_level
    assert "5" in line_level

    line_objective = formatter.format_objective("Equip higher armour boots")
    assert "[OBJECTIVE]" in line_objective
    assert "Equip higher armour boots" in line_objective

    line_notify = formatter.format_notify("Alert sent to console")
    assert "[NOTIFY]" in line_notify

    line_backfill = formatter.format_backfill("Catching up historical log (0 -> 500 bytes)")
    assert "[BACKFILL]" in line_backfill

    line_crash = formatter.format_crash_recovery("Resuming from offset 250")
    assert "[CRASH RECOVERY]" in line_crash
