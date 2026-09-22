"""Vision sensor package for read-only visual extraction and budget management."""

from __future__ import annotations

from companion.vision.budget import VisionBudgetConfig, VisionBudgetTracker
from companion.vision.capture import (
    CapturedFrame,
    CaptureRegion,
    CaptureResult,
    FakeCaptureBackend,
    MSSCaptureBackend,
    PixelFormat,
    ScreenCaptureBackend,
    capture_region,
    capture_screen,
)
from companion.vision.privacy import VisionPrivacyConfig, get_privacy_disclosure, redact_sensitive_text
from companion.vision.schema import CharacterPanelStats, ScreenType, VisionExtractionResult

__all__ = [
    "CaptureRegion",
    "CaptureResult",
    "CapturedFrame",
    "CharacterPanelStats",
    "FakeCaptureBackend",
    "MSSCaptureBackend",
    "PixelFormat",
    "ScreenCaptureBackend",
    "ScreenType",
    "VisionBudgetConfig",
    "VisionBudgetTracker",
    "VisionExtractionResult",
    "VisionPrivacyConfig",
    "capture_region",
    "capture_screen",
    "get_privacy_disclosure",
    "redact_sensitive_text",
]
