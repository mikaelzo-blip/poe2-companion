"""Tests asserting zero input injection, zero runtime divergence, and git isolation."""

from pathlib import Path
import pytest

from companion.observe.compliance import NoInputGuard
from companion.runtime.models import RuntimeConfig
from companion.runtime.orchestrator import ContinuousRuntimeOrchestrator


def test_compliance_no_input_injection():
    """Verify that observation mode contains zero keyboard/mouse input injection calls."""
    observe_dir = Path("companion/observe")
    violations = NoInputGuard.verify_no_input_injection(observe_dir)
    assert violations == [], f"Input injection violations found: {violations}"


def test_compliance_zero_runtime_divergence_when_disabled(tmp_path: Path):
    """Verify that when observe_dev is disabled, orchestrator has no observer and leaves no artifacts."""
    runtime_dir = tmp_path / "runtime"
    log_file = tmp_path / "Client.txt"
    log_file.write_text("2026/09/23 12:00:00 12345 [INFO Client 1234] : You have entered Lioneye's Watch.\n", encoding="utf-8")

    cfg = RuntimeConfig(
        runtime_dir=runtime_dir,
        client_log_path=log_file,
        observe_dev=False,
    )
    orch = ContinuousRuntimeOrchestrator(cfg)
    orch.initialize_startup()

    assert orch.observer is None

    # Run poll tick
    orch.poll_tick()

    # Verify no observations directory created
    obs_dir = runtime_dir / "observations"
    assert not obs_dir.exists()

    orch.shutdown()


def test_compliance_git_status_isolation():
    """Verify that runtime observation storage paths are ignored in git."""
    gitignore_path = Path(".gitignore")
    assert gitignore_path.exists()
    content = gitignore_path.read_text(encoding="utf-8")
    assert "/runtime/" in content or "runtime/" in content
