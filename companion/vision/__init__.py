"""Vision sensor package for read-only visual extraction and budget management."""

from __future__ import annotations

from companion.vision.budget import VisionBudgetConfig, VisionBudgetTracker
from companion.vision.privacy import VisionPrivacyConfig, get_privacy_disclosure, redact_sensitive_text
from companion.vision.schema import CharacterPanelStats, ScreenType, VisionExtractionResult

__all__ = [
    "CharacterPanelStats",
    "ScreenType",
    "VisionBudgetConfig",
    "VisionBudgetTracker",
    "VisionExtractionResult",
    "VisionPrivacyConfig",
    "get_privacy_disclosure",
    "redact_sensitive_text",
]
