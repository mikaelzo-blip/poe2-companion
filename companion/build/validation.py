"""Boundary level validation and error definitions for PoE2 Companion Build Brain."""

from __future__ import annotations


class InvalidCharacterLevelError(ValueError):
    """Raised when character level violates the supported range [1, 100]."""
    pass


def validate_character_level(level: int | None) -> int | None:
    """Validate character level against supported game bounds [1, 100].

    Returns None if level is None (unobserved).
    Raises InvalidCharacterLevelError if level <= 0 or level > 100, or if level is not an integer.
    """
    if level is None:
        return None
    if isinstance(level, bool) or not isinstance(level, int) or level <= 0 or level > 100:
        raise InvalidCharacterLevelError(
            f"Invalid character level: {level}. Level must be an integer between 1 and 100."
        )
    return level
