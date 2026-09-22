"""Unit tests for runtime session lifecycle and exit drain."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from companion.runtime.lifecycle import SessionLifecycleManager
from companion.runtime.models import SessionLifecycleState
from companion.sensing.process_presence import ProcessInfo, ProcessState, ProcessTransition


def test_initial_state_idle() -> None:
    mgr = SessionLifecycleManager()
    assert mgr.state == SessionLifecycleState.IDLE
    assert mgr.session_id is None


def test_transition_idle_to_game_running() -> None:
    mgr = SessionLifecycleManager()
    proc_info = ProcessInfo(pid=1234, executable_name="PathOfExileSteam.exe")
    transition = ProcessTransition(
        previous_state=ProcessState.IDLE,
        current_state=ProcessState.RUNNING,
        process_info=proc_info,
        is_transition=True,
    )

    new_state = mgr.handle_process_transition(transition)
    assert new_state == SessionLifecycleState.GAME_RUNNING
    assert mgr.state == SessionLifecycleState.GAME_RUNNING
    assert mgr.session_id is not None
    assert mgr.active_game_pid == 1234


def test_transition_game_running_to_session_active_on_observation() -> None:
    mgr = SessionLifecycleManager()
    proc_info = ProcessInfo(pid=1234, executable_name="PathOfExileSteam.exe")
    mgr.handle_process_transition(
        ProcessTransition(
            previous_state=ProcessState.IDLE,
            current_state=ProcessState.RUNNING,
            process_info=proc_info,
            is_transition=True,
        )
    )

    new_state = mgr.handle_observation()
    assert new_state == SessionLifecycleState.SESSION_ACTIVE
    assert mgr.state == SessionLifecycleState.SESSION_ACTIVE


def test_transition_to_game_exited_and_bounded_drain() -> None:
    mgr = SessionLifecycleManager()
    proc_info = ProcessInfo(pid=1234, executable_name="PathOfExileSteam.exe")
    mgr.handle_process_transition(
        ProcessTransition(
            previous_state=ProcessState.IDLE,
            current_state=ProcessState.RUNNING,
            process_info=proc_info,
            is_transition=True,
        )
    )
    mgr.handle_observation()
    assert mgr.state == SessionLifecycleState.SESSION_ACTIVE

    # Process terminates
    exit_transition = ProcessTransition(
        previous_state=ProcessState.RUNNING,
        current_state=ProcessState.TERMINATED,
        process_info=proc_info,
        is_transition=True,
    )
    state = mgr.handle_process_transition(exit_transition)
    assert state == SessionLifecycleState.GAME_EXITED
    assert mgr.state == SessionLifecycleState.GAME_EXITED

    # Drain callback executed during finalization
    drain_mock = MagicMock()
    mgr.finalize_session(drain_callback=drain_mock)

    drain_mock.assert_called_once()
    assert mgr.state == SessionLifecycleState.IDLE
    assert mgr.session_id is None
    assert mgr.active_game_pid is None
