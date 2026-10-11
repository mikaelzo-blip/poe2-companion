from pathlib import Path

import pytest
from pydantic import ValidationError

from companion.builds.guide import BreakerRule
from companion.dashboard_api import update_guide_rules_payload


def test_exclude_slots_case_insensitivity_and_deduplication():
    rule = BreakerRule(pattern="x", reason="r", exclude_slots=["helmet", "Weapon 1 swap", "HELMET"])
    assert rule.exclude_slots == ["Helmet", "Weapon 1 Swap"]


def test_unknown_slot_raises_validation_error():
    with pytest.raises(ValidationError) as exc_info:
        BreakerRule(pattern="x", reason="r", exclude_slots=["unknown_slot"])
    assert "slot tidak dikenal" in str(exc_info.value)


def test_update_guide_rules_payload_unknown_slot(tmp_path: Path):
    res = update_guide_rules_payload(
        {"slug": "dummy", "rules": [{"pattern": "x", "reason": "r", "exclude_slots": ["unknown_slot"]}]},
        tmp_path,
    )
    assert res["error"].startswith("Aturan tidak valid: slot tidak dikenal")


def test_update_guide_rules_payload_invalid_regex(tmp_path: Path):
    res = update_guide_rules_payload(
        {"slug": "dummy", "rules": [{"pattern": "(", "reason": "r"}]},
        tmp_path,
    )
    assert res["error"].startswith("Pola regex tidak valid: regex tidak valid")
