"""Privacy disclosures and sensitive region redaction for vision sensing."""

from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, ConfigDict


class VisionPrivacyConfig(BaseModel):
    """Configuration governing visual sensor privacy and external disclosure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["cloud", "local"] = "local"
    provider: str = "local-cpu"
    redaction_enabled: bool = True


def get_privacy_disclosure(config: VisionPrivacyConfig) -> str:
    """Return explicit disclosure statement based on vision operating mode."""
    if config.mode == "cloud":
        return (
            f"Vision sensor mode is CLOUD ({config.provider}): "
            "Cropped PoE2 image regions are transmitted to the configured model provider for visual analysis."
        )
    return (
        f"Vision sensor mode is LOCAL ({config.provider}): "
        "Image processing remains local according to the local model setup."
    )


def redact_sensitive_text(text: str) -> str:
    """Redact player identifiers, account names, and chat prefixes from extracted text."""
    # Redact account / character names following labels
    redacted = re.sub(
        r"(?:Character|Account|Player):\s*[A-Za-z0-9_]+",
        "[REDACTED_IDENTITY]",
        text,
        flags=re.IGNORECASE,
    )
    # Redact whisper / chat prefixes
    redacted = re.sub(
        r"(?:@From|@To|Whisper from)\s+[A-Za-z0-9_]+:\s*[^\n.]*",
        "[REDACTED_CHAT]",
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted
