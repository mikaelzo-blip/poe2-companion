"""Unit tests for Windows cross-process single-writer file locking."""

import os
from pathlib import Path
import subprocess
import sys
import time
import pytest

from companion.state.lock import StateLock, StateLockError


def test_lock_acquire_and_release(tmp_path: Path) -> None:
    lock_file = tmp_path / "state.lock"
    lock = StateLock(lock_file)

    with lock:
        assert lock_file.exists()
        assert lock_file.stat().st_size >= 1

    # Should be able to acquire again immediately after exit
    with StateLock(lock_file):
        pass


def test_cross_process_lock_contention(tmp_path: Path) -> None:
    """Spawns a child process holding the lock and verifies contention raises StateLockError."""
    lock_file = tmp_path / "cross_process.lock"

    # Script executed by child process
    child_code = (
        "import sys, time\n"
        "from companion.state.lock import StateLock\n"
        f"lock_path = r'{lock_file}'\n"
        "with StateLock(lock_path):\n"
        "    sys.stdout.write('LOCKED\\n')\n"
        "    sys.stdout.flush()\n"
        "    time.sleep(5)\n"
    )

    proc = subprocess.Popen(
        [sys.executable, "-c", child_code],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for child to output 'LOCKED'
        ready_line = proc.stdout.readline().strip()  # type: ignore[union-attr]
        assert ready_line == "LOCKED", f"Child failed to start: {proc.stderr.read()}"  # type: ignore[union-attr]

        # In parent process, attempting to acquire lock must fail immediately
        with pytest.raises(StateLockError):
            with StateLock(lock_file):
                pass
    finally:
        proc.terminate()
        proc.wait(timeout=3)

    # After child termination, parent should be able to acquire lock
    with StateLock(lock_file):
        assert True
