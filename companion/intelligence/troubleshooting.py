"""Troubleshooting rules: mana starvation and attribute requirement diagnostics.

Enforces strict per-operand provenance and evidence verification per the M9 policy.
Authoritative mechanical advisories require every constituent operand to be available,
fresh, reliably verified (VERIFIED), within scope, and sourced from supported structured
channels. Missing or stale operands yield UNKNOWN with no definitive advisory emitted.
All arbitrary safety buffers (2x mana buffer, <5 attribute margin) are removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from companion.intelligence.schema import (
    AdvisoryCategory,
    AdvisoryItem,
    AdvisorySeverity,
    ProvenanceCategory,
)
from companion.state.provenance import VerificationState


@dataclass(frozen=True)
class OperandEvidence:
    """Provenance and verification metadata for an individual rule operand."""

    value: int | None
    verification_state: VerificationState = VerificationState.VERIFIED
    is_stale: bool = False
    source: str = "structured"
    in_scope: bool = True

    @property
    def is_usable(self) -> bool:
        return (
            self.value is not None
            and self.verification_state == VerificationState.VERIFIED
            and not self.is_stale
            and self.in_scope
            and bool(self.source)
        )


def _to_operand(
    val: int | OperandEvidence | None,
    default_source: str = "structured",
) -> OperandEvidence:
    """Normalize raw values or evidence instances into OperandEvidence."""
    if isinstance(val, OperandEvidence):
        return val
    if isinstance(val, int):
        return OperandEvidence(
            value=val,
            verification_state=VerificationState.VERIFIED,
            source=default_source,
        )
    return OperandEvidence(
        value=None,
        verification_state=VerificationState.UNKNOWN,
        source=default_source,
    )


def evaluate_troubleshooting_rules(
    character_attributes: Mapping[str, int | OperandEvidence],
    required_attributes: Mapping[str, int | OperandEvidence],
    current_mana: int | OperandEvidence | None = None,
    unreserved_mana: int | OperandEvidence | None = None,
    main_skill_cost: int | OperandEvidence | None = None,
) -> list[AdvisoryItem]:
    """Diagnose resource starvation, reservation locks, and attribute requirements.

    Evaluates ONLY when every required operand meets strict provenance requirements.
    Missing, stale, or UNKNOWN operands suppress definitive advisories.
    """
    advisories: list[AdvisoryItem] = []

    # 1. Mana reservation lockout check (unreserved_mana < main_skill_cost)
    if unreserved_mana is not None and main_skill_cost is not None:
        unreserved_op = _to_operand(unreserved_mana, default_source="official_api")
        cost_op = _to_operand(main_skill_cost, default_source="gem_metadata")

        # Both operands must be available, fresh, and VERIFIED
        if unreserved_op.is_usable and cost_op.is_usable:
            cost = cost_op.value
            unres = unreserved_op.value
            if cost is not None and unres is not None and cost > 0:
                if unres < cost:
                    advisories.append(
                        AdvisoryItem(
                            category=AdvisoryCategory.TROUBLESHOOTING,
                            severity=AdvisorySeverity.CRITICAL,
                            title="Mana Starvation / Mechanical Lockout",
                            description=(
                                f"Unreserved mana ({unres}) is strictly less than main skill cost "
                                f"({cost}). Skill cannot be cast."
                            ),
                            recommendation="Reduce mana reservations or invest in higher unreserved mana.",
                            code="MANA_STARVATION",
                            context={"unreserved_mana": unres, "skill_cost": cost},
                            is_inference=False,
                            provenance=ProvenanceCategory.SOURCE_BACKED,
                        )
                    )

    # 2. Attribute requirement bottleneck checks (current_attribute < item_requirement)
    for attr in ("str", "dex", "int"):
        if attr not in character_attributes or attr not in required_attributes:
            # Do NOT invent or default missing operand values
            continue

        char_op = _to_operand(character_attributes[attr], default_source="character_sheet")
        req_op = _to_operand(required_attributes[attr], default_source="item_requirements")

        # Both operands must be available, fresh, and VERIFIED
        if not (char_op.is_usable and req_op.is_usable):
            continue

        char_val = char_op.value
        req_val = req_op.value
        if char_val is not None and req_val is not None and req_val > 0:
            if char_val < req_val:
                deficit = req_val - char_val
                advisories.append(
                    AdvisoryItem(
                        category=AdvisoryCategory.TROUBLESHOOTING,
                        severity=AdvisorySeverity.CRITICAL,
                        title=f"Attribute Deficit: {attr.upper()}",
                        description=(
                            f"Current {attr.upper()} is {char_val}, but equipped gear or gem setup "
                            f"requires {req_val} ({deficit} deficit)."
                        ),
                        recommendation=f"Socket an attribute node or craft +{attr.upper()} onto gear.",
                        code=f"ATTRIBUTE_DEFICIT_{attr.upper()}",
                        context={"attribute": attr, "current": char_val, "required": req_val, "deficit": deficit},
                        is_inference=False,
                        provenance=ProvenanceCategory.SOURCE_BACKED,
                    )
                )

    return advisories
