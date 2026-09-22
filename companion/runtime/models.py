"""Domain and persistence models for PoE2 Companion continuous runtime."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


class SessionLifecycleState(str, Enum):
    """Discrete session lifecycle states."""

    IDLE = "IDLE"
    GAME_RUNNING = "GAME_RUNNING"
    SESSION_ACTIVE = "SESSION_ACTIVE"
    GAME_EXITED = "GAME_EXITED"


class FileFingerprint(BaseModel):
    """Lightweight file identity descriptor for Client.txt."""

    model_config = ConfigDict(frozen=True)

    path: str
    created_at: float
    prefix_hash: str  # SHA-256 of first 512 bytes
    file_size_at_fingerprint: int


class RuntimeCheckpoint(BaseModel):
    """Crash-consistent durable runtime checkpoint."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    file_fingerprint: FileFingerprint
    stream_epoch: int = 1
    last_offset: int
    last_file_size: int
    updated_at: str
    clean_shutdown: bool = False
    clean_shutdown_at: str | None = None
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


class WriterLease(BaseModel):
    """Diagnostic metadata descriptor for runtime/writer_lease.json.

    Authority for writer ownership is held strictly by the OS file lock
    on runtime/writer_lease.lock (StateLock). This JSON model contains
    diagnostic telemetry only and does not grant ownership independently.
    """

    model_config = ConfigDict(frozen=True)

    owner_pid: int
    run_id: str
    acquired_at: str
    last_heartbeat: str
    character_id: str | None = None


class RuntimeStatus(BaseModel):
    """Cross-process observability status published to runtime/runtime_status.json."""

    model_config = ConfigDict(frozen=True)

    runtime_pid: int
    lifecycle_state: SessionLifecycleState
    session_id: str | None = None
    game_process_running: bool = False
    game_pid: int | None = None
    last_heartbeat: str
    last_consumed_offset: int = 0
    active_character_id: str | None = None
    started_at: str


class RuntimeConfig(BaseModel):
    """Configuration for continuous runtime orchestrator."""

    runtime_dir: Path = Field(default_factory=lambda: Path("runtime"))
    client_log_path: Path | None = None
    character_id: str | None = None
    poll_interval: float = 1.0
    backfill: bool = False
    verbose: bool = False


class RuntimeEvent(BaseModel):
    """Internal runtime event for status and telemetry."""

    model_config = ConfigDict(frozen=True)

    event_type: str
    timestamp: str
    payload: dict[str, Any] = Field(default_factory=dict)
