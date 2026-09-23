"""Tests for opt-in asynchronous screenshot capture worker."""

from pathlib import Path
import time
import pytest

from companion.observe.models import ScreenshotRecord
from companion.observe.screens import ScreenshotCaptureWorker
from companion.vision.capture import CapturedFrame, PixelFormat


class FakeCaptureBackend:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.call_count = 0

    def capture_screen(self, source_id: int = 1) -> CapturedFrame:
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("Fake OS display capture error")
        return CapturedFrame(
            pixels=b"\x00\x00\x00\xff" * 100,
            format=PixelFormat.BGRA,
            width=10,
            height=10,
            channels=4,
            row_stride=40,
            region=None,
            source_id=source_id,
            captured_at="2026-09-23T14:00:00Z",
            backend="fake",
        )


def test_screenshot_worker_success(tmp_path: Path):
    output_dir = tmp_path / "screenshots"
    backend = FakeCaptureBackend()
    worker = ScreenshotCaptureWorker(
        output_dir=output_dir,
        backend=backend,
        cooldown_seconds=0.01,
        max_screenshots=5,
    )

    rec = worker.request_capture(trigger_event="TOP_OBJECTIVE_CHANGED")
    assert rec.capture_result == "CAPTURED"
    assert rec.relative_path is not None
    assert rec.sha256 is not None
    assert worker.degraded is False
    assert (output_dir / Path(rec.relative_path).name).exists()


def test_screenshot_worker_cooldown_and_budget(tmp_path: Path):
    output_dir = tmp_path / "screenshots"
    backend = FakeCaptureBackend()
    worker = ScreenshotCaptureWorker(
        output_dir=output_dir,
        backend=backend,
        cooldown_seconds=10.0,
        max_screenshots=2,
    )

    # 1. First capture succeeds
    r1 = worker.request_capture("TRIGGER_1")
    assert r1.capture_result == "CAPTURED"

    # 2. Immediate second capture skipped due to cooldown
    r2 = worker.request_capture("TRIGGER_2")
    assert r2.capture_result == "SKIPPED_COOLDOWN"

    # Reset cooldown timer manually for test
    worker.last_capture_time = 0.0

    # 3. Second allowed capture reaches quota of 2
    r3 = worker.request_capture("TRIGGER_3")
    assert r3.capture_result == "CAPTURED"

    worker.last_capture_time = 0.0

    # 4. Third capture skipped due to budget
    r4 = worker.request_capture("TRIGGER_4")
    assert r4.capture_result == "SKIPPED_BUDGET"


def test_screenshot_worker_failure_transitions_to_degraded(tmp_path: Path):
    output_dir = tmp_path / "screenshots"
    backend = FakeCaptureBackend(should_fail=True)
    worker = ScreenshotCaptureWorker(
        output_dir=output_dir,
        backend=backend,
        cooldown_seconds=0.01,
        max_screenshots=5,
    )

    rec = worker.request_capture("TRIGGER_FAIL")
    assert rec.capture_result == "CAPTURE_FAILED"
    assert rec.error_message is not None
    assert worker.degraded is True
