import subprocess
import sys


def test_baseline_set_help_exits_cleanly():
    res = subprocess.run(
        [sys.executable, "-m", "companion.cli", "gear", "baseline", "set", "--help"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Character Movement Speed %" in res.stdout


def test_baseline_refresh_help_exits_cleanly():
    res = subprocess.run(
        [sys.executable, "-m", "companion.cli", "gear", "baseline", "refresh", "--help"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Character Movement Speed %" in res.stdout
