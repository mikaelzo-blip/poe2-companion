"""Cross-process runtime status inspection and heartbeat verification."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from companion.runtime.lease import WriterLeaseManager
from companion.runtime.models import RuntimeStatus, SessionLifecycleState


class RuntimeStatusSummary(BaseModel):
    """Summarized status output for cross-process inspection."""

    model_config = ConfigDict(frozen=True)

    status: str  # "ACTIVE", "STALE", "NOT RUNNING"
    runtime_pid: int | None = None
    lifecycle_state: SessionLifecycleState | None = None
    game_process_running: bool = False
    game_pid: int | None = None
    last_heartbeat: str | None = None
    heartbeat_age_seconds: float | None = None
    active_character_id: str | None = None
    last_consumed_offset: int = 0
    writer_lock_held: bool = False
    message: str = ""


def is_pid_alive(pid: int) -> bool:
    """Check if process PID is currently alive on the host OS."""
    if pid <= 0:
        return False

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_process = kernel32.OpenProcess(0x1000, False, pid)
        if not h_process:
            return False
        exit_code = wintypes.DWORD()
        success = kernel32.GetExitCodeProcess(h_process, ctypes.byref(exit_code))
        kernel32.CloseHandle(h_process)
        if not success:
            return False
        # STILL_ACTIVE = 259
        return exit_code.value == 259
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def inspect_runtime_status(runtime_dir: Path | str) -> RuntimeStatusSummary:
    """Inspect local status and lock files to determine accurate runtime operational state."""
    r_dir = Path(runtime_dir)
    status_file = r_dir / "runtime_status.json"
    lease_mgr = WriterLeaseManager(r_dir)
    writer_lock_held = lease_mgr.is_lock_actively_held()

    if not status_file.exists():
        if writer_lock_held:
            return RuntimeStatusSummary(
                status="ACTIVE",
                writer_lock_held=True,
                message="Runtime writer lock actively held (status file not yet written)",
            )
        return RuntimeStatusSummary(
            status="NOT RUNNING",
            writer_lock_held=False,
            message="No active runtime found",
        )

    try:
        raw_text = status_file.read_text(encoding="utf-8")
        status = RuntimeStatus.model_validate_json(raw_text)
    except Exception as e:
        return RuntimeStatusSummary(
            status="STALE",
            writer_lock_held=writer_lock_held,
            message=f"Corrupt status file: {e}",
        )

    # Check heartbeat age
    age_seconds: float | None = None
    heartbeat_stale = False
    try:
        hb_dt = datetime.fromisoformat(status.last_heartbeat)
        now = datetime.now(timezone.utc)
        age_seconds = max(0.0, (now - hb_dt).total_seconds())
        if age_seconds > 10.0:
            heartbeat_stale = True
    except Exception:
        heartbeat_stale = True

    proc_alive = is_pid_alive(status.runtime_pid)

    if writer_lock_held and proc_alive and not heartbeat_stale:
        overall_status = "ACTIVE"
        msg = f"Runtime active (PID: {status.runtime_pid})"
    elif not proc_alive or not writer_lock_held:
        overall_status = "NOT RUNNING"
        msg = "Runtime process terminated or writer lock released"
    else:
        overall_status = "STALE"
        msg = f"Heartbeat stale ({age_seconds:.1f}s ago)"

    return RuntimeStatusSummary(
        status=overall_status,
        runtime_pid=status.runtime_pid,
        lifecycle_state=status.lifecycle_state,
        game_process_running=status.game_process_running,
        game_pid=status.game_pid,
        last_heartbeat=status.last_heartbeat,
        heartbeat_age_seconds=age_seconds,
        active_character_id=status.active_character_id,
        last_consumed_offset=status.last_consumed_offset,
        writer_lock_held=writer_lock_held,
        message=msg,
    )
