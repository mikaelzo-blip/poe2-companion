"""Process presence detection and lifecycle monitoring for Path of Exile 2."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from enum import Enum
import io
import os
import subprocess
from typing import Callable
from pydantic import BaseModel, ConfigDict, Field


class ProcessState(str, Enum):
    """Execution state of the monitored game process."""

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"


class ProcessInfo(BaseModel):
    """Metadata describing a running game process."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pid: int
    executable_name: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProcessTransition(BaseModel):
    """Result of a process presence poll cycle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    previous_state: ProcessState
    current_state: ProcessState
    process_info: ProcessInfo | None = None
    is_transition: bool


def _default_os_process_detector() -> list[tuple[int, str]]:
    """Inspect active system processes without third-party dependencies."""
    results: list[tuple[int, str]] = []
    if os.name == "nt":
        try:
            # tasklist /FO CSV /NH
            cmd = ["tasklist", "/FO", "CSV", "/NH"]
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            reader = csv.reader(io.StringIO(output))
            for row in reader:
                if len(row) >= 2:
                    image_name = row[0].strip()
                    try:
                        pid = int(row[1].strip())
                        results.append((pid, image_name))
                    except ValueError:
                        continue
        except Exception:
            return []
    else:
        try:
            # ps -eo pid,comm
            cmd = ["ps", "-eo", "pid,comm"]
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            for line in output.strip().splitlines()[1:]:
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    try:
                        pid = int(parts[0])
                        results.append((pid, parts[1]))
                    except ValueError:
                        continue
        except Exception:
            return []
    return results


DEFAULT_POE2_EXECUTABLES = [
    "PathOfExileSteam.exe",
    "PathOfExile.exe",
    "PathOfExile_x64.exe",
    "PathOfExile_x64Steam.exe",
]


class ProcessMonitor:
    """Non-invasive process presence monitor tracking game execution state."""

    def __init__(
        self,
        target_executables: list[str] | None = None,
        detector_fn: Callable[[], list[tuple[int, str]]] | None = None,
    ) -> None:
        self.target_executables = [
            exe.lower() for exe in (target_executables or DEFAULT_POE2_EXECUTABLES)
        ]
        self._detector_fn = detector_fn or _default_os_process_detector
        self._current_state = ProcessState.IDLE
        self._active_process: ProcessInfo | None = None

    @property
    def current_state(self) -> ProcessState:
        """Return the current process state."""
        return self._current_state

    @property
    def active_process(self) -> ProcessInfo | None:
        """Return active process details if currently running."""
        return self._active_process

    def poll(self) -> ProcessTransition:
        """Execute one poll cycle and compute state transition."""
        processes = self._detector_fn()
        matching_proc: tuple[int, str] | None = None

        for pid, name in processes:
            if name.lower() in self.target_executables:
                matching_proc = (pid, name)
                break

        prev_state = self._current_state

        if matching_proc is not None:
            pid, name = matching_proc
            if prev_state != ProcessState.RUNNING:
                self._current_state = ProcessState.RUNNING
                self._active_process = ProcessInfo(pid=pid, executable_name=name)
                return ProcessTransition(
                    previous_state=prev_state,
                    current_state=ProcessState.RUNNING,
                    process_info=self._active_process,
                    is_transition=True,
                )
            else:
                # Already running
                return ProcessTransition(
                    previous_state=prev_state,
                    current_state=ProcessState.RUNNING,
                    process_info=self._active_process,
                    is_transition=False,
                )
        else:
            # Process not found
            if prev_state == ProcessState.RUNNING:
                self._current_state = ProcessState.TERMINATED
                terminated_info = self._active_process
                self._active_process = None
                return ProcessTransition(
                    previous_state=ProcessState.RUNNING,
                    current_state=ProcessState.TERMINATED,
                    process_info=terminated_info,
                    is_transition=True,
                )
            elif prev_state == ProcessState.TERMINATED:
                self._current_state = ProcessState.IDLE
                self._active_process = None
                return ProcessTransition(
                    previous_state=ProcessState.TERMINATED,
                    current_state=ProcessState.IDLE,
                    process_info=None,
                    is_transition=True,
                )
            else:
                # Still idle
                self._current_state = ProcessState.IDLE
                self._active_process = None
                return ProcessTransition(
                    previous_state=ProcessState.IDLE,
                    current_state=ProcessState.IDLE,
                    process_info=None,
                    is_transition=False,
                )
