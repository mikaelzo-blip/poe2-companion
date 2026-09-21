"""Session recap package providing milestone aggregation and progress reports."""

from __future__ import annotations

from companion.recap.generator import (
    format_recap_json,
    format_recap_text,
    generate_session_recap,
)
from companion.recap.schema import SessionRecap

__all__ = [
    "SessionRecap",
    "format_recap_json",
    "format_recap_text",
    "generate_session_recap",
]
