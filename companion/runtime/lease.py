"""OS-backed lifetime single-writer lease management and CLI mutator guard."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Generator

from companion.runtime.models import WriterLease
from companion.state.lock import StateLock, StateLockError

logger = logging.getLogger(__name__)

RUNTIME_WRITER_ACTIVE_CODE = "RUNTIME_WRITER_ACTIVE"


class WriterActiveError(RuntimeError):
    """Raised when writer lease lock cannot be acquired because continuous runtime is active."""
    pass


class WriterLeaseManager:
    """Manages OS-backed lifetime single-writer locking on runtime/writer_lease.lock."""

    def __init__(self, runtime_dir: Path | str) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.lock_path = self.runtime_dir / "writer_lease.lock"
        self.metadata_path = self.runtime_dir / "writer_lease.json"
        self._lock: StateLock | None = None
        self._lease: WriterLease | None = None

    @property
    def current_lease(self) -> WriterLease | None:
        return self._lease

    def acquire(self, run_id: str, character_id: str | None = None) -> WriterLease:
        """Atomically acquire lifetime OS writer lock and write diagnostic metadata."""
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        lock = StateLock(self.lock_path)
        try:
            lock.acquire()
        except StateLockError as e:
            raise WriterActiveError(
                f"[{RUNTIME_WRITER_ACTIVE_CODE}] Continuous runtime writer lock is actively held on '{self.lock_path}'."
            ) from e

        self._lock = lock

        # Inspect any previous stale metadata for logging
        if self.metadata_path.exists():
            try:
                stale_data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
                stale = WriterLease.model_validate(stale_data)
                logger.info(
                    f"[LEASE] Acquired writer lock; replacing previous stale lease metadata from PID {stale.owner_pid}, run_id {stale.run_id}."
                )
            except Exception:
                pass

        now_iso = datetime.now(timezone.utc).isoformat()
        lease = WriterLease(
            owner_pid=os.getpid(),
            run_id=run_id,
            acquired_at=now_iso,
            last_heartbeat=now_iso,
            character_id=character_id,
        )
        self._write_metadata(lease)
        self._lease = lease
        return lease

    def heartbeat(self) -> None:
        """Update last_heartbeat timestamp in writer_lease.json."""
        if self._lease is not None:
            now_iso = datetime.now(timezone.utc).isoformat()
            updated = self._lease.model_copy(update={"last_heartbeat": now_iso})
            self._write_metadata(updated)
            self._lease = updated

    def release(self) -> None:
        """Unlink diagnostic metadata and release OS lock."""
        try:
            if self.metadata_path.exists():
                self.metadata_path.unlink(missing_ok=True)
        except OSError:
            pass

        if self._lock is not None:
            try:
                self._lock.release()
            except Exception:
                pass
            finally:
                self._lock = None
                self._lease = None

    def _write_metadata(self, lease: WriterLease) -> None:
        try:
            self.metadata_path.write_text(lease.model_dump_json(indent=2), encoding="utf-8")
        except OSError:
            pass

    def is_lock_actively_held(self) -> bool:
        """Test whether the OS writer lock is currently held by attempting non-blocking acquire."""
        if self._lock is not None:
            # We hold it ourselves
            return True

        if not self.lock_path.exists():
            return False

        probe_lock = StateLock(self.lock_path)
        try:
            probe_lock.acquire()
            probe_lock.release()
            return False
        except StateLockError:
            return True


@contextmanager
def guard_state_mutation(runtime_dir: Path | str) -> Generator[None, None, None]:
    """Context manager for mutating CLI commands to participate in the writer-lease contract."""
    r_dir = Path(runtime_dir)
    r_dir.mkdir(parents=True, exist_ok=True)
    lock_path = r_dir / "writer_lease.lock"
    lock = StateLock(lock_path)
    try:
        lock.acquire()
    except StateLockError as e:
        raise WriterActiveError(
            f"[{RUNTIME_WRITER_ACTIVE_CODE}] Continuous runtime writer lock is actively held. CharacterState mutation refused."
        ) from e

    try:
        yield
    finally:
        try:
            lock.release()
        except Exception:
            pass
