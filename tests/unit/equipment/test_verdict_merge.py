from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from companion.dashboard_api import evaluate_item_payload
from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
from companion.equipment.precedence import Verdict as PrecedenceVerdict
from companion.equipment.recommendation import Verdict as RecVerdict
from companion.equipment.tactical_advisor import TacticalAdvice, merge_verdicts


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


def _make_dummy_tactical(verdict: PrecedenceVerdict) -> TacticalAdvice:
    return TacticalAdvice(
        verdict=verdict,
        verdict_badge="TAHAN" if verdict == PrecedenceVerdict.REJECT else "BAGUS",
        tactical_headline="Tactical Headline",
        zone_name="Test Zone",
        actionable_recommendation="Test recommendation",
    )


@pytest.mark.parametrize(
    ("policy_verdict", "tactical_verdict", "expected_final"),
    [
        (RecVerdict.EQUIP_NOW, PrecedenceVerdict.EQUIP_NOW, "EQUIP_NOW"),
        (RecVerdict.EQUIP_NOW, PrecedenceVerdict.REJECT, "REJECT"),
        (RecVerdict.CONDITIONAL_UPGRADE, PrecedenceVerdict.EQUIP_NOW, "CONDITIONAL_UPGRADE"),
        (RecVerdict.CONDITIONAL_UPGRADE, PrecedenceVerdict.REJECT, "REJECT"),
        (RecVerdict.REJECT, PrecedenceVerdict.EQUIP_NOW, "REJECT"),
        (RecVerdict.REJECT, PrecedenceVerdict.REJECT, "REJECT"),
    ],
)
def test_generic_slot_path_verdict_merging(
    tmp_path: Path,
    policy_verdict: RecVerdict,
    tactical_verdict: PrecedenceVerdict,
    expected_final: str,
):
    """Verify generic slot path uses merge_verdicts and cannot be overridden to EQUIP_NOW by tactical."""
    class MockGenericSession:
        is_available = True
        xml = "<PathOfBuilding></PathOfBuilding>"
        level = 20

        def submit_candidate(self, raw_text: str, candidate_name: str, slot: str) -> int:
            return 1

        def simulate_item(self, slot: str, raw_candidate: str, candidate_id: int, candidate_name: str):
            return PobEquipmentDelta(
                slot="Helmet",
                candidate_id=candidate_id,
                candidate_name="Test Helm",
                current_item_name="Current Helm",
            )

        def get_current_item_name(self, slot: str) -> str:
            return "Current Helm"

    mock_rec = MagicMock()
    mock_rec.verdict = policy_verdict
    mock_rec.formatted_output = "Policy Report"
    mock_rec.reason = "Policy reason"
    mock_rec.gains = []
    mock_rec.trade_offs = []

    mock_tac = _make_dummy_tactical(tactical_verdict)

    with (
        patch("companion.dashboard_api.evaluate_fubgun_equipment_policy", return_value=mock_rec),
        patch("companion.dashboard_api.generate_tactical_advice", return_value=mock_tac),
        patch("companion.equipment.tactical_advisor.generate_tactical_advice", return_value=mock_tac),
    ):
        res = evaluate_item_payload(
            {
                "raw_text": "Item Class: Helmets\nRarity: Rare\nTest Helm\nIron Mask\n",
                "character_id": "BOMSHAK",
                "stage": "lvl 15-32",
            },
            runtime_dir=tmp_path,
            pob_session=MockGenericSession(),
        )
        assert res.get("success") is True
        assert res.get("verdict") == expected_final


@pytest.mark.parametrize(
    ("policy_verdict", "tactical_verdict", "expected_final"),
    [
        (RecVerdict.EQUIP_NOW, PrecedenceVerdict.EQUIP_NOW, "EQUIP_NOW"),
        (RecVerdict.EQUIP_NOW, PrecedenceVerdict.REJECT, "REJECT"),
        (RecVerdict.CONDITIONAL_UPGRADE, PrecedenceVerdict.EQUIP_NOW, "CONDITIONAL_UPGRADE"),
        (RecVerdict.CONDITIONAL_UPGRADE, PrecedenceVerdict.REJECT, "REJECT"),
        (RecVerdict.REJECT, PrecedenceVerdict.EQUIP_NOW, "REJECT"),
        (RecVerdict.REJECT, PrecedenceVerdict.REJECT, "REJECT"),
    ],
)
def test_weapon_path_verdict_merging(
    tmp_path: Path,
    policy_verdict: RecVerdict,
    tactical_verdict: PrecedenceVerdict,
    expected_final: str,
):
    """Verify weapon path uses merge_verdicts and cannot be overridden to EQUIP_NOW by tactical."""
    class MockWeaponSession:
        is_available = True
        xml = "<PathOfBuilding></PathOfBuilding>"
        level = 20

        def submit_candidate(self, raw_text: str, candidate_name: str, slot: str) -> int:
            return 1

        def simulate_item(self, slot: str, raw_candidate: str, candidate_id: int, candidate_name: str):
            return PobEquipmentDelta(
                slot="Weapon 1",
                candidate_id=candidate_id,
                candidate_name="Test Bow",
                current_item_name="Current Bow",
            )

        def get_current_item_name(self, slot: str) -> str:
            return "Current Bow"

    mock_rec = MagicMock()
    mock_rec.verdict = policy_verdict
    mock_rec.formatted_output = "Weapon Policy Report"
    mock_rec.reason = "Weapon policy reason"
    mock_rec.gains = []
    mock_rec.trade_offs = []

    mock_tac = _make_dummy_tactical(tactical_verdict)

    with (
        patch("companion.dashboard_api.evaluate_fubgun_weapon_policy", return_value=mock_rec),
        patch("companion.dashboard_api.generate_tactical_advice", return_value=mock_tac),
        patch("companion.equipment.tactical_advisor.generate_tactical_advice", return_value=mock_tac),
    ):
        res = evaluate_item_payload(
            {
                "raw_text": "Item Class: Crossbows\nRarity: Rare\nTest Crossbow\nBombard Crossbow\n",
                "character_id": "BOMSHAK",
                "stage": "lvl 15-32",
            },
            runtime_dir=tmp_path,
            pob_session=MockWeaponSession(),
        )
        assert res.get("success") is True
        assert res.get("verdict") == expected_final


@pytest.mark.parametrize(
    ("policy_verdict", "tactical_verdict", "expected_final"),
    [
        (RecVerdict.EQUIP_NOW, PrecedenceVerdict.EQUIP_NOW, "EQUIP_NOW"),
        (RecVerdict.EQUIP_NOW, PrecedenceVerdict.REJECT, "REJECT"),
        (RecVerdict.CONDITIONAL_UPGRADE, PrecedenceVerdict.EQUIP_NOW, "CONDITIONAL_UPGRADE"),
        (RecVerdict.CONDITIONAL_UPGRADE, PrecedenceVerdict.REJECT, "REJECT"),
        (RecVerdict.REJECT, PrecedenceVerdict.EQUIP_NOW, "REJECT"),
        (RecVerdict.REJECT, PrecedenceVerdict.REJECT, "REJECT"),
    ],
)
def test_ring_path_verdict_merging(
    tmp_path: Path,
    policy_verdict: RecVerdict,
    tactical_verdict: PrecedenceVerdict,
    expected_final: str,
):
    """Verify ring path uses merge_verdicts and cannot be overridden to EQUIP_NOW by tactical."""
    class MockRingSession:
        is_available = True
        xml = "<PathOfBuilding></PathOfBuilding>"
        level = 20

        def submit_candidate(self, raw_text: str, candidate_name: str, slot: str) -> int:
            return 1

        def simulate_ring_candidate(self, raw_candidate: str, candidate_id: int, candidate_name: str):
            from companion.equipment.pob2_equipment_advisor import DualRingSimulationResult
            d1 = PobEquipmentDelta(slot="Ring 1", candidate_id=candidate_id, candidate_name="Test Ring", current_item_name="Current Ring 1")
            d2 = PobEquipmentDelta(slot="Ring 2", candidate_id=candidate_id, candidate_name="Test Ring", current_item_name="Current Ring 2")
            return DualRingSimulationResult(candidate_id=candidate_id, candidate_name="Test Ring", ring1_delta=d1, ring2_delta=d2)

        def is_slot_empty(self, slot: str) -> bool:
            return False

        def get_current_item_name(self, slot: str) -> str:
            return "Current Ring 1"

    mock_advice = MagicMock()
    mock_advice.recommended_slot = "Ring 1"
    mock_advice.ring1_recommendation.verdict = policy_verdict
    mock_advice.ring1_recommendation.gains = []
    mock_advice.ring1_recommendation.trade_offs = []
    mock_advice.trade_off_notes = []
    mock_advice.summary_verdict = "Ring summary"
    mock_advice.formatted_output = "Ring report"

    mock_tac = _make_dummy_tactical(tactical_verdict)

    with (
        patch("companion.equipment.fubgun_priorities.evaluate_dual_ring_policy", return_value=mock_advice),
        patch("companion.dashboard_api.generate_tactical_advice", return_value=mock_tac),
        patch("companion.equipment.tactical_advisor.generate_tactical_advice", return_value=mock_tac),
    ):
        res = evaluate_item_payload(
            {
                "raw_text": "Item Class: Rings\nRarity: Rare\nTest Ring\nIron Ring\n",
                "character_id": "BOMSHAK",
                "stage": "lvl 15-32",
            },
            runtime_dir=tmp_path,
            pob_session=MockRingSession(),
        )
        assert res.get("success") is True
        assert res.get("verdict") == expected_final
