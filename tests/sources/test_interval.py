"""Unit tests for conservative level_interval parsing."""

import pytest
from companion.sources.interval import (
    IntervalKind,
    InvalidLevelIntervalError,
    UnresolvedIntervalEvaluationError,
    parse_level_interval,
)


def test_omitted_or_none_is_unrestricted() -> None:
    interval = parse_level_interval(None)
    assert interval.kind == IntervalKind.UNRESTRICTED
    assert interval.is_unrestricted
    assert not interval.is_range
    assert not interval.is_unresolved
    assert interval.min_level is None
    assert interval.max_level is None
    assert interval.contains_level(1)
    assert interval.contains_level(100)


def test_valid_two_element_range() -> None:
    interval = parse_level_interval([1, 14])
    assert interval.kind == IntervalKind.RANGE
    assert interval.is_range
    assert interval.min_level == 1
    assert interval.max_level == 14
    assert interval.contains_level(1)
    assert interval.contains_level(7)
    assert interval.contains_level(14)
    assert not interval.contains_level(0)
    assert not interval.contains_level(15)


def test_equal_bounds_range() -> None:
    interval = parse_level_interval([50, 50])
    assert interval.kind == IntervalKind.RANGE
    assert interval.min_level == 50
    assert interval.max_level == 50
    assert interval.contains_level(50)
    assert not interval.contains_level(49)
    assert not interval.contains_level(51)


def test_single_uint_preserved_as_unresolved() -> None:
    interval = parse_level_interval(52)
    assert interval.kind == IntervalKind.UNRESOLVED_SINGLE_UINT
    assert interval.is_unresolved
    assert interval.single_val == 52
    assert interval.raw_value == 52
    assert interval.min_level is None
    assert interval.max_level is None
    with pytest.raises(UnresolvedIntervalEvaluationError):
        interval.contains_level(52)


def test_rejects_negative_single_int() -> None:
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval(-1)


def test_rejects_negative_bounds() -> None:
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval([-1, 10])
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval([10, -5])


def test_rejects_inverted_range() -> None:
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval([10, 5])
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval([100, 1])


def test_rejects_invalid_list_lengths() -> None:
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval([])
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval([1])
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval([1, 2, 3])


def test_rejects_booleans() -> None:
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval(True)
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval([True, False])
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval([0, True])


def test_rejects_floats_and_strings() -> None:
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval(3.14)
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval([1.5, 10])
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval("1-14")
    with pytest.raises(InvalidLevelIntervalError):
        parse_level_interval({"min": 1, "max": 14})
