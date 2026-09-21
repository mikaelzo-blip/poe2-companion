"""Conservative level_interval parser.

Handles level interval specifications from PoE2 .build source files.
Supports:
- None / omitted -> Unrestricted
- [min, max] where 0 <= min <= max -> Explicit Range
- single non-negative uint -> Unresolved Single Uint (preserved without inventing semantics)
Rejects invalid types, negative numbers, inverted ranges, and non-2-element lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class IntervalKind(str, Enum):
    UNRESTRICTED = "UNRESTRICTED"
    RANGE = "RANGE"
    UNRESOLVED_SINGLE_UINT = "UNRESOLVED_SINGLE_UINT"


class InvalidLevelIntervalError(ValueError):
    """Raised when a level_interval value violates structural or range constraints."""
    pass


class UnresolvedIntervalEvaluationError(RuntimeError):
    """Raised when attempting to evaluate a level against an unresolved interval shape."""
    pass


@dataclass(frozen=True)
class LevelInterval:
    """Represents a validated level interval."""
    kind: IntervalKind
    min_level: int | None = None
    max_level: int | None = None
    single_val: int | None = None
    raw_value: Any = None

    @property
    def is_unrestricted(self) -> bool:
        return self.kind == IntervalKind.UNRESTRICTED

    @property
    def is_range(self) -> bool:
        return self.kind == IntervalKind.RANGE

    @property
    def is_unresolved(self) -> bool:
        return self.kind == IntervalKind.UNRESOLVED_SINGLE_UINT

    def contains_level(self, level: int) -> bool:
        """Check if a specific level falls within this interval.
        
        Raises UnresolvedIntervalEvaluationError if the interval is unresolved.
        """
        if self.kind == IntervalKind.UNRESTRICTED:
            return True
        if self.kind == IntervalKind.RANGE:
            assert self.min_level is not None and self.max_level is not None
            return self.min_level <= level <= self.max_level
        raise UnresolvedIntervalEvaluationError(
            f"Cannot evaluate level against unresolved interval with single uint: {self.single_val}"
        )


def parse_level_interval(raw: Any) -> LevelInterval:
    """Parse and conservatively validate a level_interval from raw build JSON."""
    if raw is None:
        return LevelInterval(kind=IntervalKind.UNRESTRICTED, raw_value=None)

    # Boolean is an instance of int in Python, so explicitly reject booleans
    if isinstance(raw, bool):
        raise InvalidLevelIntervalError(f"Boolean value is not a valid level_interval: {raw}")

    # Single non-negative integer
    if isinstance(raw, int):
        if raw < 0:
            raise InvalidLevelIntervalError(f"Negative single level interval is invalid: {raw}")
        return LevelInterval(
            kind=IntervalKind.UNRESOLVED_SINGLE_UINT,
            single_val=raw,
            raw_value=raw,
        )

    # List of bounds
    if isinstance(raw, (list, tuple)):
        if len(raw) != 2:
            raise InvalidLevelIntervalError(
                f"Level interval list must have exactly 2 elements [min, max], got {len(raw)}: {raw}"
            )

        min_val, max_val = raw
        if isinstance(min_val, bool) or isinstance(max_val, bool):
            raise InvalidLevelIntervalError(f"Boolean values not allowed in level interval: {raw}")

        if not isinstance(min_val, int) or not isinstance(max_val, int):
            raise InvalidLevelIntervalError(
                f"Level interval bounds must be integers, got types ({type(min_val).__name__}, {type(max_val).__name__}): {raw}"
            )

        if min_val < 0 or max_val < 0:
            raise InvalidLevelIntervalError(f"Level interval bounds cannot be negative: {raw}")

        if min_val > max_val:
            raise InvalidLevelIntervalError(
                f"Inverted level interval: min ({min_val}) > max ({max_val})"
            )

        return LevelInterval(
            kind=IntervalKind.RANGE,
            min_level=min_val,
            max_level=max_val,
            raw_value=list(raw),
        )

    raise InvalidLevelIntervalError(
        f"Invalid level_interval type '{type(raw).__name__}': {raw}"
    )
