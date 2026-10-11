import pytest

from companion.equipment.precedence import Verdict as PrecedenceVerdict
from companion.equipment.recommendation import Verdict as RecVerdict
from companion.equipment.tactical_advisor import merge_verdicts


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
        # Enums from precedence and recommendation
        (PrecedenceVerdict.EQUIP_NOW, PrecedenceVerdict.REJECT, "REJECT"),
        (RecVerdict.EQUIP_NOW, RecVerdict.REJECT, "REJECT"),
        (PrecedenceVerdict.REJECT, PrecedenceVerdict.EQUIP_NOW, "REJECT"),
        (RecVerdict.REJECT, RecVerdict.EQUIP_NOW, "REJECT"),
        (RecVerdict.CONDITIONAL_UPGRADE, RecVerdict.EQUIP_NOW, "CONDITIONAL_UPGRADE"),
        # None and whitespace handling
        ("EQUIP_NOW", None, "EQUIP_NOW"),
        ("REJECT", None, "REJECT"),
        (None, "REJECT", "REJECT"),
        (" equip_now ", " reject ", "REJECT"),
    ],
)
def test_merge_verdicts_matrix(policy, tactical, expected):
    assert merge_verdicts(policy, tactical) == expected
