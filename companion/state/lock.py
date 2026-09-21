"""Cross-process single-writer file locking for Windows.

Uses Windows standard-library msvcrt.locking with LK_NBLCK on runtime/state.lock.
Guarantees exclusive single-writer access across independent processes throughout
the entire logical state mutation transaction.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore[assignment]


class StateLockError(RuntimeError):
    """Raised when the exclusive writer lock cannot be acquired due to contention."""
    pass


class StateLock:
    """Context manager for cross-process single-writer locking on Windows."""

    def __init__(self, lock_path: str | Path) -> None:
        self.lock_path = Path(lock_path)
        self._file: BinaryIO | None = None
        self._locked = False

    def __enter__(self) -> StateLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()

    def acquire(self) -> None:
        """Acquire exclusive non-blocking lock on 1 byte."""
        if msvcrt is None:
            raise RuntimeError("StateLock requires Windows platform with msvcrt module.")

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Ensure file exists and contains at least 1 byte
        if not self.lock_path.exists() or self.lock_path.stat().st_size == 0:
            with open(self.lock_path, "wb") as f_init:
                f_init.write(b"\x00")
                f_init.flush()
                os.fsync(f_init.fileno())

        # Open in read-write binary mode
        f = open(self.lock_path, "r+b")
        self._file = f

        try:
            f.seek(0, os.SEEK_SET)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            self._locked = True
        except (OSError, PermissionError) as e:
            f.close()
            self._file = None
            raise StateLockError(
                f"Cannot acquire state lock on '{self.lock_path}': another process holds the lock."
            ) from e

    def release(self) -> None:
        """Unlock byte 0 and close the file descriptor."""
        if self._file is not None:
            try:
                if self._locked and msvcrt is not None:
                    self._file.seek(0, os.SEEK_SET)
                    msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
            finally:
                self._locked = False
                self._file.close()
                self._file = None
