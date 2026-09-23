"""Multi-stage privacy filter and log sanitization."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PrivacyResult:
    """Evaluation result from PrivacyFilter."""

    is_safe: bool
    is_chat: bool
    has_credentials: bool
    is_approved_envelope: bool
    uncertain: bool
    sanitized_text: str | None


# Chat channel markers and indicators
_CHAT_INDICATORS = ("@From", "@To", "Whisper from", "Whisper to")
_CHAT_CHANNEL_REGEX = re.compile(r"(?:\]\s*|:\s*|^\s*|\s+)(?:@From|@To|Whisper from|[#\$%&!])(?=[a-zA-Z0-9_\u00C0-\u017F-]|[\s:])", re.IGNORECASE)

# Credential and token patterns
_CREDENTIAL_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9\-_\.=]+", re.IGNORECASE),
    re.compile(r"(?:oauth_token|access_token|refresh_token)\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
    re.compile(r"(?:password|passwd|secret)\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
    re.compile(r"Authorization:\s*[^\r\n]+", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+.*PRIVATE KEY-----", re.IGNORECASE),
]

# Approved engine/system debug envelopes
_APPROVED_ENVELOPES = [
    re.compile(r"\[(?:ENGINE|SYSTEM|SHADER|DEBUG|DEVICE|TEXTURE|AUDIO|PHYSICS|NETWORK|GRAPHICS|RENDER|CLIENT|SCRIPT|CACHE)\]", re.IGNORECASE),
    re.compile(r"\b(?:Async loading|Connecting to|Connected to|Generating level|Entering area|Abnormal termination|DirectX|Vulkan|Websocket)\b", re.IGNORECASE),
]

# Dynamic value sanitizers
_HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
_IP_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?\b")
_TIMESTAMP_RE = re.compile(r"^\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\s+\d+)?(?:\s+[a-f0-9]+)?\s*")
_UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_NUMERIC_ID_RE = re.compile(r"\b\d{5,}\b")


class PrivacyFilter:
    """Multi-stage fail-closed privacy filter for raw game logs."""

    def is_chat_line(self, line: str) -> bool:
        """Check if line matches any chat channel or whisper."""
        for ind in _CHAT_INDICATORS:
            if ind in line:
                return True
        return bool(_CHAT_CHANNEL_REGEX.search(line))

    def has_credentials(self, line: str) -> bool:
        """Check if line contains tokens or credentials."""
        for pattern in _CREDENTIAL_PATTERNS:
            if pattern.search(line):
                return True
        return False

    def is_approved_envelope(self, line: str) -> bool:
        """Check if line matches an approved non-chat debug/engine envelope."""
        for pattern in _APPROVED_ENVELOPES:
            if pattern.search(line):
                return True
        return False

    def sanitize(self, line: str) -> str:
        """Strip dynamic timestamps, addresses, and IDs from log line."""
        text = _TIMESTAMP_RE.sub("<TIMESTAMP> ", line)
        text = _HEX_RE.sub("<HEX>", text)
        text = _IP_RE.sub("<IP>", text)
        text = _UUID_RE.sub("<UUID>", text)
        text = _NUMERIC_ID_RE.sub("<ID>", text)
        return text.strip()

    def evaluate_line(self, line: str) -> PrivacyResult:
        """Evaluate line against all privacy stages."""
        clean = line.strip()
        if not clean:
            return PrivacyResult(
                is_safe=False,
                is_chat=False,
                has_credentials=False,
                is_approved_envelope=False,
                uncertain=False,
                sanitized_text=None,
            )

        if self.is_chat_line(clean):
            return PrivacyResult(
                is_safe=False,
                is_chat=True,
                has_credentials=False,
                is_approved_envelope=False,
                uncertain=False,
                sanitized_text=None,
            )

        if self.has_credentials(clean):
            return PrivacyResult(
                is_safe=False,
                is_chat=False,
                has_credentials=True,
                is_approved_envelope=False,
                uncertain=False,
                sanitized_text=None,
            )

        approved = self.is_approved_envelope(clean)
        sanitized = self.sanitize(clean)

        if approved:
            return PrivacyResult(
                is_safe=True,
                is_chat=False,
                has_credentials=False,
                is_approved_envelope=True,
                uncertain=False,
                sanitized_text=sanitized,
            )

        # Unapproved or ambiguous lines: fail-closed safety uncertainty
        return PrivacyResult(
            is_safe=True,
            is_chat=False,
            has_credentials=False,
            is_approved_envelope=False,
            uncertain=True,
            sanitized_text=sanitized,
        )
