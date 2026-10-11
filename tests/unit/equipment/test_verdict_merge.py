import pytest

from companion.equipment.tactical_advisor import Verdict, merge_verdicts


@pytest.mark.parametrize(
    ("policy", "tactical", "expected"),
    [
        # All 9 combinations of (EQUIP_NOW, CONDITIONAL_UPGRADE, REJECT)
        ("EQUIP_NOW", "EQUIP_NOW", "EQUIP_NOW"),
        ("EQUIP_NOW", "CONDITIONAL_UPGRADE", "EQUIP_NOW"),
        ("EQUIP_NOW", "REJECT", "REJECT"),
        ("CONDITIONAL_UPGRADE", "EQUIP_NOW", "CONDITIONAL_UPGRADE"),
        ("CONDITIONAL_UPGRADE", "CONDITIONAL_UPGRADE", "CONDITIONAL_UPGRADE"),
        ("CONDITIONAL_UPGRADE", "REJECT", "REJECT"),
        ("REJECT", "EQUIP_NOW", "REJECT"),
        ("REJECT", "CONDITIONAL_UPGRADE", "REJECT"),
        ("REJECT", "REJECT", "REJECT"),
        # Verdict enum members
        (Verdict.EQUIP_NOW, Verdict.REJECT, "REJECT"),
        (Verdict.REJECT, Verdict.EQUIP_NOW, "REJECT"),
        (Verdict.CONDITIONAL_UPGRADE, Verdict.EQUIP_NOW, "CONDITIONAL_UPGRADE"),
        # None and whitespace handling
        ("EQUIP_NOW", None, "EQUIP_NOW"),
        ("REJECT", None, "REJECT"),
        (None, "REJECT", "REJECT"),
        (" equip_now ", " reject ", "REJECT"),
    ],
)
def test_merge_verdicts_matrix(policy, tactical, expected):
    assert merge_verdicts(policy, tactical) == expected
