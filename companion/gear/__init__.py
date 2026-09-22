"""Gear auto-analysis package for tooltips, hashing, audit, and conflict detection."""

from __future__ import annotations

from companion.gear.advisor import (
    InvestmentAdvice,
    UpgradeComparison,
    compare_candidate_upgrade,
    generate_investment_advice,
)
from companion.gear.audit import (
    load_gear_audit_state,
    record_slot_audit,
    save_gear_audit_state,
)
from companion.gear.conflicts import ConflictType, ConflictWarning, detect_mechanic_conflicts
from companion.gear.evaluator import (
    ComparisonResult,
    compare_equipped_against_target,
    evaluate_gear_staleness,
)
from companion.gear.hasher import compute_item_hash
from companion.gear.schema import (
    EquippedItem,
    GearAuditState,
    ItemMod,
    ItemRarity,
    ItemSlot,
    ModType,
)
from companion.gear.tooltip import parse_item_tooltip, verify_tooltip_stability

__all__ = [
    "ComparisonResult",
    "ConflictType",
    "ConflictWarning",
    "EquippedItem",
    "GearAuditState",
    "InvestmentAdvice",
    "ItemMod",
    "ItemRarity",
    "ItemSlot",
    "ModType",
    "UpgradeComparison",
    "compare_candidate_upgrade",
    "compare_equipped_against_target",
    "compute_item_hash",
    "detect_mechanic_conflicts",
    "evaluate_gear_staleness",
    "generate_investment_advice",
    "load_gear_audit_state",
    "parse_item_tooltip",
    "record_slot_audit",
    "save_gear_audit_state",
    "verify_tooltip_stability",
]
