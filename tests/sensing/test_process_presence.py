"""Unit tests for ProcessMonitor and process presence sensing."""

from __future__ import annotations

import pytest

from companion.sensing.process_presence import (
    ProcessInfo,
    ProcessMonitor,
    ProcessState,
    ProcessTransition,
)


def test_process_monitor_initial_state() -> None:
    monitor = ProcessMonitor(
        target_executables=["PathOfExileSteam.exe"],
        detector_fn=lambda: [],
    )
    assert monitor.current_state == ProcessState.IDLE
    assert monitor.active_process is None


def test_process_monitor_detects_launch() -> None:
    calls = 0

    def mock_detector() -> list[tuple[int, str]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return []
        return [(1234, "PathOfExileSteam.exe")]

    monitor = ProcessMonitor(
        target_executables=["PathOfExileSteam.exe"],
        detector_fn=mock_detector,
    )

    # Initial poll -> IDLE
    t1 = monitor.poll()
    assert t1.previous_state == ProcessState.IDLE
    assert t1.current_state == ProcessState.IDLE
    assert t1.is_transition is False

    # Second poll -> transition to RUNNING
    t2 = monitor.poll()
    assert t2.previous_state == ProcessState.IDLE
    assert t2.current_state == ProcessState.RUNNING
    assert t2.is_transition is True
    assert t2.process_info is not None
    assert t2.process_info.pid == 1234
    assert t2.process_info.executable_name == "PathOfExileSteam.exe"
    assert monitor.current_state == ProcessState.RUNNING


def test_process_monitor_detects_termination() -> None:
    running = True

    def mock_detector() -> list[tuple[int, str]]:
        if running:
            return [(5678, "PathOfExile.exe")]
        return []

    monitor = ProcessMonitor(
        target_executables=["PathOfExile.exe"],
        detector_fn=mock_detector,
    )

    # 1. Start running
    t1 = monitor.poll()
    assert t1.current_state == ProcessState.RUNNING

    # 2. Process exits
    running = False
    t2 = monitor.poll()
    assert t2.previous_state == ProcessState.RUNNING
    assert t2.current_state == ProcessState.TERMINATED
    assert t2.is_transition is True
    assert monitor.current_state == ProcessState.TERMINATED

    # 3. Next poll returns to IDLE
    t3 = monitor.poll()
    assert t3.previous_state == ProcessState.TERMINATED
    assert t3.current_state == ProcessState.IDLE
    assert monitor.current_state == ProcessState.IDLE
