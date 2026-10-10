import pytest

from companion.dashboard_api import _resolve_stage
from companion.equipment.rules import BuildProgressionStage as S


@pytest.mark.parametrize(
    "label, level, expected",
    [
        ("Act 1 & 2", 90, S.LEVELING_1_14),
        ("Act 2", 1, S.LEVELING_15_32),
        ("Act 3", 1, S.LEVELING_15_32),
        ("Act 4 to Endgame", 1, S.LEVELING_33_51),
        ("Early Endgame", 1, S.LEVELING_53_68),
        ("Mid-Endgame", 1, S.LEVEL_85),
        ("Late Endgame", 1, S.LEVEL_85),
        ("Uber Endgame", 1, S.ENDGAME),
        ("lvl 15-32", None, S.LEVELING_15_32),
        ("lvl 33-51", None, S.LEVELING_33_51),
        ("lvl 52 swap", None, S.SWAP_52),
        ("lvl 53-68", None, S.LEVELING_53_68),
        ("lvl 85", None, S.LEVEL_85),
        ("endgame", None, S.ENDGAME),
        ("mageblood", None, S.MAGEBLOOD),
        ("dot cap", None, S.DOT_CAP),
        ("auto", 90, S.ENDGAME),
        ("auto", None, S.LEVELING_1_14),
        ("", 10, S.LEVELING_1_14),
        ("lvl 1-14", 40, S.LEVELING_33_51),  # legacy: treated as auto
        ("garbage", 60, S.LEVELING_53_68),
        ("garbage", None, S.LEVELING_1_14),
        ("  ACT 3 ", 1, S.LEVELING_15_32),
    ],
)
def test_resolve_stage(label, level, expected):
    assert _resolve_stage(label, level) == expected


def test_resolve_char_id(tmp_path):
    from companion.dashboard_api import resolve_char_id

    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "BOMSHAK.json").write_text("{}")
    assert resolve_char_id(" bomshak ", tmp_path) == "BOMSHAK"
    assert resolve_char_id("Other", tmp_path) == "Other"
    assert resolve_char_id(None, tmp_path) == "BOMSHAK"
    assert resolve_char_id("", tmp_path) == "BOMSHAK"
