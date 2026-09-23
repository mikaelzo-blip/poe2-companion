"""Unit tests for build-breaker certainty states and High-Risk Unknown Gate."""

import pytest
from companion.equipment.schema import SlotType
from companion.equipment.parser import parse_item_text
from companion.equipment.rules import (
    BuildBreakerCertainty,
    BuildProgressionStage,
    RuleSeverity,
)
from companion.equipment.build_breaker import evaluate_candidate_build_safety
from companion.equipment.build_breaker_gate import apply_build_breaker_gate

AMAZING_RING_UNKNOWN_FIRE = """Item Class: Rings
Rarity: Rare
Miracle Knot
Prismatic Ring
--------
Requirements:
Level: 60
--------
Gain 10% of Physical Damage as Extra Fire Damage during Focus
+80 to maximum Life
+30% to Fire Resistance
+30% to Cold Resistance
+30% to Lightning Resistance
"""

SAFE_RING = """Item Class: Rings
Rarity: Rare
Gold Ring
Gold Ring
--------
Requirements:
Level: 40
--------
+80 to maximum Life
+30% to Fire Resistance
+30% to Cold Resistance
"""

HARMFUL_RING = """Item Class: Rings
Rarity: Rare
Pyre Band
Iron Ring
--------
Requirements:
Level: 40
--------
Adds 15 to 30 Fire Damage to Attacks
+80 to maximum Life
+30% to Fire Resistance
"""


def test_unknown_fire_applicability_blocks_equip_now():
    item = parse_item_text(AMAZING_RING_UNKNOWN_FIRE, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=item,
        slot=SlotType.RING_1,
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )
    assert ev.certainty == BuildBreakerCertainty.UNKNOWN_APPLICABILITY

    # Gate downgrades any prospective EQUIP_NOW to CONDITIONAL_UPGRADE or INSUFFICIENT_DATA with HIGH_RISK
    final_verdict, flags = apply_build_breaker_gate(
        prospective_verdict="EQUIP_NOW",
        safety_eval=ev,
    )
    assert final_verdict != "EQUIP_NOW"
    assert "HIGH_RISK" in flags
    assert final_verdict in ("CONDITIONAL_UPGRADE", "INSUFFICIENT_DATA")


def test_harmful_fire_forces_reject():
    item = parse_item_text(HARMFUL_RING, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=item,
        slot=SlotType.RING_1,
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER

    final_verdict, flags = apply_build_breaker_gate(
        prospective_verdict="EQUIP_NOW",
        safety_eval=ev,
    )
    assert final_verdict == "REJECT"
    assert "BUILD_BREAKER" in flags


def test_safe_fire_permits_equip_now():
    item = parse_item_text(SAFE_RING, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=item,
        slot=SlotType.RING_1,
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_SAFE

    final_verdict, flags = apply_build_breaker_gate(
        prospective_verdict="EQUIP_NOW",
        safety_eval=ev,
    )
    assert final_verdict == "EQUIP_NOW"
    assert "BUILD_BREAKER" not in flags
    assert "HIGH_RISK" not in flags
