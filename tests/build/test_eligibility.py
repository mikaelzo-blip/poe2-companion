"""Unit tests for character level boundary validation and level eligibility evaluation."""

import pytest
from companion.sources.interval import IntervalKind, LevelInterval, parse_level_interval
from companion.build.validation import (
    InvalidCharacterLevelError,
    validate_character_level,
)
from companion.build.eligibility import (
    EligibilityState,
    EligibilityEvaluation,
    evaluate_eligibility,
)


def test_validate_character_level_valid_bounds() -> None:
    """Supported character levels in [1, 100] pass validation and return the level."""
    assert validate_character_level(1) == 1
    assert validate_character_level(50) == 50
    assert validate_character_level(100) == 100
    assert validate_character_level(None) is None


def test_validate_character_level_rejects_zero_and_negative() -> None:
    """Levels <= 0 are rejected with InvalidCharacterLevelError."""
    with pytest.raises(InvalidCharacterLevelError):
        validate_character_level(0)

    with pytest.raises(InvalidCharacterLevelError):
        validate_character_level(-1)

    with pytest.raises(InvalidCharacterLevelError):
        validate_character_level(-5)


def test_validate_character_level_rejects_above_maximum() -> None:
    """Levels > 100 are rejected with InvalidCharacterLevelError."""
    with pytest.raises(InvalidCharacterLevelError):
        validate_character_level(101)

    with pytest.raises(InvalidCharacterLevelError):
        validate_character_level(999)


def test_validate_character_level_rejects_non_integers_and_booleans() -> None:
    """Non-integer types including booleans must be rejected."""
    with pytest.raises(InvalidCharacterLevelError):
        validate_character_level(True)  # type: ignore[arg-type]

    with pytest.raises(InvalidCharacterLevelError):
        validate_character_level(False)  # type: ignore[arg-type]

    with pytest.raises(InvalidCharacterLevelError):
        validate_character_level("50")  # type: ignore[arg-type]

    with pytest.raises(InvalidCharacterLevelError):
        validate_character_level(50.5)  # type: ignore[arg-type]


def test_evaluate_eligibility_unrestricted_interval() -> None:
    """Unrestricted intervals evaluate to ACTIVE across all levels, including None/unknown."""
    interval = LevelInterval(kind=IntervalKind.UNRESTRICTED)

    assert evaluate_eligibility(interval, 1).state == EligibilityState.ACTIVE
    assert evaluate_eligibility(interval, 50).state == EligibilityState.ACTIVE
    assert evaluate_eligibility(interval, 100).state == EligibilityState.ACTIVE
    assert evaluate_eligibility(interval, None).state == EligibilityState.ACTIVE


def test_evaluate_eligibility_closed_range_boundaries() -> None:
    """Test boundary evaluations for closed range [15, 32]: min-1, min, inside, max, max+1."""
    interval = LevelInterval(kind=IntervalKind.RANGE, min_level=15, max_level=32)

    # min - 1 -> FUTURE
    res_14 = evaluate_eligibility(interval, 14)
    assert res_14.state == EligibilityState.FUTURE
    assert not res_14.unresolved_semantics

    # min -> ACTIVE
    res_15 = evaluate_eligibility(interval, 15)
    assert res_15.state == EligibilityState.ACTIVE
    assert not res_15.unresolved_semantics

    # inside -> ACTIVE
    res_20 = evaluate_eligibility(interval, 20)
    assert res_20.state == EligibilityState.ACTIVE
    assert not res_20.unresolved_semantics

    # max -> ACTIVE
    res_32 = evaluate_eligibility(interval, 32)
    assert res_32.state == EligibilityState.ACTIVE
    assert not res_32.unresolved_semantics

    # max + 1 -> EXPIRED
    res_33 = evaluate_eligibility(interval, 33)
    assert res_33.state == EligibilityState.EXPIRED
    assert not res_33.unresolved_semantics


def test_evaluate_eligibility_unknown_level_with_bounded_interval() -> None:
    """Bounded interval with unknown character level (None) returns UNKNOWN."""
    interval = LevelInterval(kind=IntervalKind.RANGE, min_level=52, max_level=68)
    res = evaluate_eligibility(interval, None)
    assert res.state == EligibilityState.UNKNOWN
    assert not res.unresolved_semantics


def test_evaluate_eligibility_unresolved_single_uint() -> None:
    """Unresolved single uint interval evaluates to UNKNOWN with unresolved_semantics flag."""
    interval = LevelInterval(kind=IntervalKind.UNRESOLVED_SINGLE_UINT, single_val=52)

    res_52 = evaluate_eligibility(interval, 52)
    assert res_52.state == EligibilityState.UNKNOWN
    assert res_52.unresolved_semantics is True

    res_10 = evaluate_eligibility(interval, 10)
    assert res_10.state == EligibilityState.UNKNOWN
    assert res_10.unresolved_semantics is True

    res_none = evaluate_eligibility(interval, None)
    assert res_none.state == EligibilityState.UNKNOWN
    assert res_none.unresolved_semantics is True


def test_evaluate_eligibility_validates_character_level() -> None:
    """Invalid character levels raise InvalidCharacterLevelError during eligibility evaluation."""
    interval = LevelInterval(kind=IntervalKind.RANGE, min_level=1, max_level=14)
    with pytest.raises(InvalidCharacterLevelError):
        evaluate_eligibility(interval, 0)

    with pytest.raises(InvalidCharacterLevelError):
        evaluate_eligibility(interval, -5)

    with pytest.raises(InvalidCharacterLevelError):
        evaluate_eligibility(interval, 105)
