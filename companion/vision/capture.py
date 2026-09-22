"""Read-only screen and bounded region capture adapter for Windows.

Adheres strictly to no-input compliance: zero keystrokes, zero mouse simulation,
zero game memory reading, and zero window hooking. Provides an immutable pixel contract
and isolates raw display pixels from downstream text parsing and extraction layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

import mss

from companion.state.provenance import VerificationState


class PixelFormat(str, Enum):
    """Pixel color format and channel byte order."""
    BGRA = "BGRA"  # Native Windows GDI / DIB / MSS byte order
    RGBA = "RGBA"


@dataclass(frozen=True)
class CaptureRegion:
    """Bounding coordinates for a sub-region capture."""
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class CapturedFrame:
    """Immutable pixel contract for raw captured screen frames."""
    pixels: bytes
    format: PixelFormat
    width: int
    height: int
    channels: int
    row_stride: int
    region: CaptureRegion | None
    source_id: str | int
    captured_at: str
    backend: str

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Frame dimensions must be positive, got {self.width}x{self.height}")
        expected_len = self.row_stride * self.height
        if len(self.pixels) < expected_len:
            raise ValueError(
                f"Pixel buffer size {len(self.pixels)} smaller than stride * height {expected_len}"
            )


class CaptureError(Exception):
    """Raised when screen or region capture operation fails."""


@dataclass(frozen=True)
class CaptureResult:
    """Structured capture result enforcing uncertainty handling."""
    frame: CapturedFrame | None = None
    verification_state: VerificationState = VerificationState.UNKNOWN
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.frame is not None

    @property
    def state(self) -> VerificationState:
        return self.verification_state


class ScreenCaptureBackend(Protocol):
    """Protocol for screen capture implementations."""
    def capture_screen(self, source_id: int = 1) -> CapturedFrame:
        ...

    def capture_region(self, region: CaptureRegion, source_id: int = 1) -> CapturedFrame:
        ...


class MSSCaptureBackend:
    """Production screen capture backend using Python mss."""

    def capture_screen(self, source_id: int = 1) -> CapturedFrame:
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with mss.MSS() as sct:
                monitors = sct.monitors
                if source_id < 1 or source_id >= len(monitors):
                    raise CaptureError(
                        f"Requested monitor index {source_id} out of bounds (monitors: {len(monitors) - 1})"
                    )
                monitor = monitors[source_id]
                shot = sct.grab(monitor)
                width = shot.width
                height = shot.height
                channels = 4
                row_stride = width * channels
                raw_pixels = bytes(shot.raw)
                return CapturedFrame(
                    pixels=raw_pixels,
                    format=PixelFormat.BGRA,
                    width=width,
                    height=height,
                    channels=channels,
                    row_stride=row_stride,
                    region=None,
                    source_id=source_id,
                    captured_at=now_iso,
                    backend="mss",
                )
        except CaptureError:
            raise
        except Exception as e:
            raise CaptureError(f"Screen capture failed: {e}") from e

    def capture_region(self, region: CaptureRegion, source_id: int = 1) -> CapturedFrame:
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with mss.MSS() as sct:
                bbox = {
                    "left": region.left,
                    "top": region.top,
                    "width": region.width,
                    "height": region.height,
                }
                shot = sct.grab(bbox)
                width = shot.width
                height = shot.height
                channels = 4
                row_stride = width * channels
                raw_pixels = bytes(shot.raw)
                return CapturedFrame(
                    pixels=raw_pixels,
                    format=PixelFormat.BGRA,
                    width=width,
                    height=height,
                    channels=channels,
                    row_stride=row_stride,
                    region=region,
                    source_id=source_id,
                    captured_at=now_iso,
                    backend="mss",
                )
        except Exception as e:
            raise CaptureError(f"Region capture failed: {e}") from e


class FakeCaptureBackend:
    """Test double providing synthetic pixel frames."""

    def __init__(
        self,
        width: int = 800,
        height: int = 600,
        format: PixelFormat = PixelFormat.BGRA,
        should_fail: bool = False,
    ) -> None:
        self.width = width
        self.height = height
        self.format = format
        self.should_fail = should_fail

    def capture_screen(self, source_id: int = 1) -> CapturedFrame:
        if self.should_fail:
            raise CaptureError("Simulated capture failure")
        now_iso = datetime.now(timezone.utc).isoformat()
        channels = 4
        stride = self.width * channels
        raw_pixels = b"\x00" * (stride * self.height)
        return CapturedFrame(
            pixels=raw_pixels,
            format=self.format,
            width=self.width,
            height=self.height,
            channels=channels,
            row_stride=stride,
            region=None,
            source_id=source_id,
            captured_at=now_iso,
            backend="fake",
        )

    def capture_region(self, region: CaptureRegion, source_id: int = 1) -> CapturedFrame:
        if self.should_fail:
            raise CaptureError("Simulated region capture failure")
        now_iso = datetime.now(timezone.utc).isoformat()
        channels = 4
        stride = region.width * channels
        raw_pixels = b"\x00" * (stride * region.height)
        return CapturedFrame(
            pixels=raw_pixels,
            format=self.format,
            width=region.width,
            height=region.height,
            channels=channels,
            row_stride=stride,
            region=region,
            source_id=source_id,
            captured_at=now_iso,
            backend="fake",
        )


def capture_screen(
    source_id: int = 1,
    backend: ScreenCaptureBackend | None = None,
) -> CaptureResult:
    """Acquire a full screen capture into volatile memory.

    Structured failure handling ensures UNKNOWN verification state rather than
    fabricated frames upon capture failure.
    """
    active_backend = backend or MSSCaptureBackend()
    try:
        frame = active_backend.capture_screen(source_id=source_id)
        return CaptureResult(frame=frame, verification_state=VerificationState.SINGLE_SOURCE)
    except Exception as e:
        return CaptureResult(
            frame=None,
            verification_state=VerificationState.UNKNOWN,
            error=str(e),
        )


def capture_region(
    region: CaptureRegion,
    source_id: int = 1,
    backend: ScreenCaptureBackend | None = None,
) -> CaptureResult:
    """Acquire a bounded sub-region capture into volatile memory."""
    active_backend = backend or MSSCaptureBackend()
    try:
        frame = active_backend.capture_region(region=region, source_id=source_id)
        return CaptureResult(frame=frame, verification_state=VerificationState.SINGLE_SOURCE)
    except Exception as e:
        return CaptureResult(
            frame=None,
            verification_state=VerificationState.UNKNOWN,
            error=str(e),
        )
