"""Unit tests for static no-input compliance guard."""

from pathlib import Path
import pytest
from companion.compliance.no_input_guard import (
    ComplianceViolationError,
    assert_no_input_compliance,
    scan_directory,
    scan_file,
)


def test_clean_companion_codebase_passes() -> None:
    """The companion package itself must pass compliance with 0 violations."""
    companion_dir = Path(__file__).resolve().parent.parent.parent / "companion"
    violations = scan_directory(companion_dir)
    assert violations == [], f"Expected clean codebase, got: {violations}"
    assert_no_input_compliance(companion_dir)


def test_detects_direct_import(tmp_path: Path) -> None:
    """Direct import of prohibited module is detected."""
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("import pyautogui\n", encoding="utf-8")
    violations = scan_file(bad_file)
    assert len(violations) == 1
    assert violations[0].symbol == "pyautogui"
    assert violations[0].category == "PROHIBITED_IMPORT"
    assert violations[0].line == 1


def test_detects_submodule_import(tmp_path: Path) -> None:
    """Import of submodule from prohibited module is detected."""
    bad_file = tmp_path / "bad_sub.py"
    bad_file.write_text("import pynput.keyboard\n", encoding="utf-8")
    violations = scan_file(bad_file)
    assert len(violations) >= 1
    assert any("pynput" in v.symbol for v in violations)


def test_detects_from_import(tmp_path: Path) -> None:
    """From-import of prohibited module is detected."""
    bad_file = tmp_path / "bad_from.py"
    bad_file.write_text("from pynput import mouse\n", encoding="utf-8")
    violations = scan_file(bad_file)
    assert len(violations) >= 1
    assert any(v.symbol == "pynput" for v in violations)


def test_detects_prohibited_symbol_import(tmp_path: Path) -> None:
    """Importing prohibited token symbol is detected."""
    bad_file = tmp_path / "bad_symbol.py"
    bad_file.write_text("from ctypes.windll.user32 import SendInput\n", encoding="utf-8")
    violations = scan_file(bad_file)
    assert len(violations) >= 1
    assert any(v.symbol == "SendInput" for v in violations)


def test_detects_aliased_import(tmp_path: Path) -> None:
    """Aliasing prohibited package or token is detected."""
    bad_file = tmp_path / "bad_alias.py"
    bad_file.write_text("import pyautogui as pag\n", encoding="utf-8")
    violations = scan_file(bad_file)
    assert any(v.symbol == "pag" or v.symbol == "pyautogui" for v in violations)


def test_detects_native_call_tokens(tmp_path: Path) -> None:
    """Direct reference or invocation of native input tokens is detected."""
    bad_file = tmp_path / "bad_call.py"
    bad_file.write_text(
        "def simulate():\n"
        "    SendInput(1, 2, 3)\n"
        "    user32.keybd_event(0, 0, 0, 0)\n"
        "    mouse_event(1, 0, 0, 0, 0)\n",
        encoding="utf-8",
    )
    violations = scan_file(bad_file)
    symbols = {v.symbol for v in violations}
    assert "SendInput" in symbols
    assert "keybd_event" in symbols
    assert "mouse_event" in symbols


def test_exclusions_ignored(tmp_path: Path) -> None:
    """Directories named in exclusions (like docs, .venv, runtime, tests) are ignored."""
    venv_dir = tmp_path / ".venv" / "sub"
    venv_dir.mkdir(parents=True)
    bad_venv = venv_dir / "lib.py"
    bad_venv.write_text("import pyautogui\n", encoding="utf-8")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True)
    bad_test = tests_dir / "fixture.py"
    bad_test.write_text("import keyboard\n", encoding="utf-8")

    violations = scan_directory(tmp_path)
    assert violations == []


def test_assert_no_input_compliance_raises_on_violations(tmp_path: Path) -> None:
    """assert_no_input_compliance raises ComplianceViolationError when violations exist."""
    bad_file = tmp_path / "evil.py"
    bad_file.write_text("import keyboard\n", encoding="utf-8")
    with pytest.raises(ComplianceViolationError) as exc_info:
        assert_no_input_compliance(tmp_path)
    assert "keyboard" in str(exc_info.value)


def test_vision_capture_module_strictly_compliant() -> None:
    """companion/vision/capture.py must contain zero prohibited input/hooking imports."""
    capture_file = Path(__file__).resolve().parent.parent.parent / "companion" / "vision" / "capture.py"
    assert capture_file.exists()
    violations = scan_file(capture_file)
    assert violations == [], f"Expected clean capture module, got: {violations}"
