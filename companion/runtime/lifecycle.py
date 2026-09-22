"""Session lifecycle state machine and exit log drain coordinator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
import uuid

from companion.runtime.models import SessionLifecycleState
from companion.sensing.process_presence import ProcessState, ProcessTransition


class SessionLifecycleManager:
    """Manages session lifecycle states (IDLE -> GAME_RUNNING -> SESSION_ACTIVE -> GAME_EXITED -> IDLE)."""

    def __init__(self) -> None:
        self._state: SessionLifecycleState = SessionLifecycleState.IDLE
        self._session_id: str | None = None
        self._started_at: datetime | None = None
        self._active_game_pid: int | None = None
        self._active_game_executable: str | None = None

    @property
    def state(self) -> SessionLifecycleState:
        return self._state

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    @property
    def active_game_pid(self) -> int | None:
        return self._active_game_pid

    @property
    def active_game_executable(self) -> str | None:
        return self._active_game_executable

    def handle_process_transition(self, transition: ProcessTransition) -> SessionLifecycleState:
        """Update lifecycle state based on process monitor transition."""
        if transition.current_state == ProcessState.RUNNING:
            if self._state == SessionLifecycleState.IDLE or self._session_id is None:
                self._state = SessionLifecycleState.GAME_RUNNING
                self._session_id = uuid.uuid4().hex
                self._started_at = datetime.now(timezone.utc)
                if transition.process_info is not None:
                    self._active_game_pid = transition.process_info.pid
                    self._active_game_executable = transition.process_info.executable_name
        elif transition.current_state in (ProcessState.TERMINATED, ProcessState.IDLE):
            if self._state in (SessionLifecycleState.GAME_RUNNING, SessionLifecycleState.SESSION_ACTIVE):
                self._state = SessionLifecycleState.GAME_EXITED

        return self._state

    def handle_observation(self, observation: Any = None) -> SessionLifecycleState:
        """Promote state to SESSION_ACTIVE upon receiving the first game observation."""
        if self._state == SessionLifecycleState.GAME_RUNNING:
            self._state = SessionLifecycleState.SESSION_ACTIVE
        return self._state

    def finalize_session(
        self,
        drain_callback: Callable[[], Any] | None = None,
        recap_callback: Callable[[str, datetime | None], Any] | None = None,
    ) -> None:
        """Execute bounded final drain, produce recap, and return lifecycle to IDLE."""
        if drain_callback is not None:
            try:
                drain_callback()
            except Exception:
                pass

        if recap_callback is not None and self._session_id is not None:
            try:
                recap_callback(self._session_id, self._started_at)
            except Exception:
                pass

        self._state = SessionLifecycleState.IDLE
        self._session_id = None
        self._started_at = None
        self._active_game_pid = None
        self._active_game_executable = None

    def reset_to_idle(self) -> None:
        """Directly reset state to IDLE."""
        self._state = SessionLifecycleState.IDLE
        self._session_id = None
        self._started_at = None
        self._active_game_pid = None
        self._active_game_executable = None
