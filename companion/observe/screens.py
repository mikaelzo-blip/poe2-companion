"""Opt-in event-triggered screenshot evidence capture worker."""

from __future__ import annotations

import hashlib
from pathlib import Path
import time
from typing import Any
import uuid

from companion.observe.models import ScreenshotRecord


class ScreenshotCaptureWorker:
    """Asynchronously captures screenshot evidence subject to strict rate limits and quotas."""

    DEFAULT_COOLDOWN_SECONDS = 30.0
    DEFAULT_MAX_SCREENSHOTS = 50
    DEFAULT_MAX_BYTES = 100 * 1024 * 1024  # 100 MB

    def __init__(
        self,
        output_dir: Path,
        backend: Any | None = None,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        max_screenshots: int = DEFAULT_MAX_SCREENSHOTS,
        max_bytes: int = DEFAULT_MAX_BYTES,
        monitor_index: int = 1,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.backend = backend
        self.cooldown_seconds = cooldown_seconds
        self.max_screenshots = max_screenshots
        self.max_bytes = max_bytes
        self.monitor_index = monitor_index

        self.last_capture_time: float = 0.0
        self.capture_count: int = 0
        self.total_bytes: int = 0
        self.degraded: bool = False

    def request_capture(
        self,
        trigger_event: str,
        correlation_ref: str | None = None,
        is_shutdown: bool = False,
    ) -> ScreenshotRecord:
        """Evaluate capture criteria and asynchronously capture screen frame if permitted."""
        screenshot_id = f"screen_{uuid.uuid4().hex[:12]}"

        if is_shutdown:
            return ScreenshotRecord(
                screenshot_id=screenshot_id,
                trigger_event=trigger_event,
                capture_result="SKIPPED_SHUTDOWN",
            )

        if self.capture_count >= self.max_screenshots or self.total_bytes >= self.max_bytes:
            return ScreenshotRecord(
                screenshot_id=screenshot_id,
                trigger_event=trigger_event,
                capture_result="SKIPPED_BUDGET",
            )

        now_mono = time.monotonic()
        if self.last_capture_time > 0 and (now_mono - self.last_capture_time) < self.cooldown_seconds:
            return ScreenshotRecord(
                screenshot_id=screenshot_id,
                trigger_event=trigger_event,
                capture_result="SKIPPED_COOLDOWN",
            )

        backend = self.backend
        if backend is None:
            from companion.vision.capture import MSSCaptureBackend
            backend = MSSCaptureBackend()

        try:
            frame = backend.capture_screen(source_id=self.monitor_index)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            img_filename = f"{screenshot_id}.png"
            img_path = self.output_dir / img_filename

            import mss.tools
            mss.tools.to_png(frame.pixels, (frame.width, frame.height), output=str(img_path))
            img_bytes = img_path.read_bytes()
            sha256 = hashlib.sha256(img_bytes).hexdigest()

            self.total_bytes += len(img_bytes)
            self.capture_count += 1
            self.last_capture_time = time.monotonic()

            return ScreenshotRecord(
                screenshot_id=screenshot_id,
                trigger_event=trigger_event,
                capture_result="CAPTURED",
                relative_path=f"screenshots/{img_filename}",
                sha256=sha256,
                width=frame.width,
                height=frame.height,
            )
        except Exception as e:
            self.degraded = True
            return ScreenshotRecord(
                screenshot_id=screenshot_id,
                trigger_event=trigger_event,
                capture_result="CAPTURE_FAILED",
                error_message=str(e),
            )
