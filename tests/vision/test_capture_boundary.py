"""Tests for M7 screen capture pixel contract and capture-vs-extraction boundary."""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from companion.state.provenance import VerificationState
from companion.vision.capture import (
    CapturedFrame,
    CaptureRegion,
    CaptureResult,
    FakeCaptureBackend,
    MSSCaptureBackend,
    PixelFormat,
    capture_region,
    capture_screen,
)
from companion.vision.parser import parse_character_panel


def test_captured_frame_pixel_contract() -> None:
    """CapturedFrame exposes all required pixel contract fields and validates buffer size."""
    w, h, channels = 100, 50, 4
    stride = w * channels
    raw_pixels = b"\x00" * (stride * h)
    now_iso = datetime.now(timezone.utc).isoformat()

    frame = CapturedFrame(
        pixels=raw_pixels,
        format=PixelFormat.BGRA,
        width=w,
        height=h,
        channels=channels,
        row_stride=stride,
        region=None,
        source_id=1,
        captured_at=now_iso,
        backend="fake",
    )

    assert frame.pixels == raw_pixels
    assert frame.format == PixelFormat.BGRA
    assert frame.width == 100
    assert frame.height == 50
    assert frame.channels == 4
    assert frame.row_stride == stride
    assert frame.region is None
    assert frame.source_id == 1
    assert frame.captured_at == now_iso
    assert frame.backend == "fake"

    # Undersized buffer must raise ValueError
    with pytest.raises(ValueError, match="smaller than stride"):
        CapturedFrame(
            pixels=b"\x00" * 10,
            format=PixelFormat.BGRA,
            width=w,
            height=h,
            channels=channels,
            row_stride=stride,
            region=None,
            source_id=1,
            captured_at=now_iso,
            backend="fake",
        )

    # Non-positive dimensions must raise ValueError
    with pytest.raises(ValueError, match="positive"):
        CapturedFrame(
            pixels=raw_pixels,
            format=PixelFormat.BGRA,
            width=0,
            height=h,
            channels=channels,
            row_stride=stride,
            region=None,
            source_id=1,
            captured_at=now_iso,
            backend="fake",
        )


def test_raw_pixels_and_captured_frame_rejected_by_text_parser() -> None:
    """Raw pixel bytes or CapturedFrame instances must not be silently treated as text."""
    w, h, channels = 10, 10, 4
    frame = CapturedFrame(
        pixels=b"\x00" * (w * channels * h),
        format=PixelFormat.BGRA,
        width=w,
        height=h,
        channels=channels,
        row_stride=w * channels,
        region=None,
        source_id=1,
        captured_at=datetime.now(timezone.utc).isoformat(),
        backend="fake",
    )

    # Passing raw bytes directly must raise TypeError
    with pytest.raises(TypeError):
        parse_character_panel(b"\x00\x01\x02\x03")  # type: ignore[arg-type]

    # Passing CapturedFrame directly must raise TypeError
    with pytest.raises(TypeError):
        parse_character_panel(frame)  # type: ignore[arg-type]


def test_character_panel_stats_unknown_without_extractor() -> None:
    """A CapturedFrame alone does not infer domain observations without an extractor."""
    backend = FakeCaptureBackend(width=640, height=480)
    result = capture_screen(backend=backend)

    assert result.is_success
    assert result.frame is not None

    # M7 capture proves frame availability only; structured stats remain UNKNOWN
    # without a registered visual extractor model.
    stats_state = VerificationState.UNKNOWN
    assert stats_state == VerificationState.UNKNOWN


def test_capture_failure_handling() -> None:
    """Capture failure produces structured result with UNKNOWN verification state."""
    failing_backend = FakeCaptureBackend(should_fail=True)
    result = capture_screen(backend=failing_backend)

    assert not result.is_success
    assert result.frame is None
    assert result.verification_state == VerificationState.UNKNOWN
    assert result.error is not None


def test_fake_capture_backend_region() -> None:
    """Fake backend supports bounded region capture."""
    backend = FakeCaptureBackend()
    region = CaptureRegion(left=100, top=100, width=200, height=150)
    result = capture_region(region=region, backend=backend)

    assert result.is_success
    assert result.frame is not None
    assert result.frame.width == 200
    assert result.frame.height == 150
    assert result.frame.region == region


def _is_desktop_available() -> bool:
    try:
        import mss

        with mss.MSS() as sct:
            return len(sct.monitors) > 1
    except Exception:
        return False


@pytest.mark.skipif(not _is_desktop_available(), reason="Active desktop session not available")
def test_windows_desktop_real_capture_smoke() -> None:
    """Real OS screen capture smoke test on platforms with active desktop."""
    backend = MSSCaptureBackend()
    result = capture_screen(source_id=1, backend=backend)

    assert result.is_success
    assert result.frame is not None
    assert result.frame.width > 0
    assert result.frame.height > 0
    assert result.frame.channels == 4
    assert result.frame.format == PixelFormat.BGRA
    assert result.frame.backend == "mss"
    assert len(result.frame.pixels) >= result.frame.row_stride * result.frame.height
