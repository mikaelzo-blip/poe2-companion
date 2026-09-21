"""Conservative equipment delta evaluation adhering to slot-scoped observation coverage."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict

from companion.sources.interval import LevelInterval, parse_level_interval
from companion.sources.models_normalized import NormalizedInventorySlot
from companion.state.provenance import VerificationState
from companion.state.schema import CharacterState
from companion.build.eligibility import evaluate_eligibility
from companion.build.input import ObservationCoverage
from companion.build.policy import DeltaReason, DeltaStatus, evaluate_delta_item
from companion.build.validation import validate_character_level


class EquipmentDeltaEntry(BaseModel):
    """Factual delta comparison result for a single equipment inventory slot."""
    model_config = ConfigDict(frozen=True)

    slot_id: str
    weapon_set_context: str | None = None
    expected_unique_name: str | None = None
    expected_base_type: str | None = None
    observed_unique_name: str | None = None
    observed_base_type: str | None = None
    status: DeltaStatus
    reason: DeltaReason = DeltaReason.NONE
    observed_provenance: str | None = None


def _normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return name.lower().strip()


def evaluate_equipment_delta(
    target_slots: list[NormalizedInventorySlot] | list[Any],
    character_state: CharacterState,
    coverage_map: dict[str, ObservationCoverage] | None = None,
    character_level: int | None = None,
) -> list[EquipmentDeltaEntry]:
    """Conservatively evaluate target equipment slots against observed character equipment.

    Rules:
    - Strictly factual: no gear scoring, upgrade scoring, pricing, economy, or OCR.
    - Uses slot-scoped observation coverage: each slot looks up its coverage in coverage_map.
    - Missing slot in coverage_map evaluates to ObservationCoverage.UNKNOWN.
    - Complete observation on one slot (e.g. Helm) establishes absence for Helm only and
      never implies coverage for boots, weapons, or rings.
    - Honors centralized evaluate_delta_item policy.
    """
    if coverage_map is None:
        coverage_map = {}

    if character_level is None and character_state.level:
        character_level = character_state.level.value
    valid_level = validate_character_level(character_level)

    audit = character_state.audit or {}
    observed_equipment: dict[str, Any] = (
        getattr(character_state, "equipment", None)
        or audit.get("equipment")
        or audit.get("equipment_slots")
        or {}
    )

    results: list[EquipmentDeltaEntry] = []

    for slot in target_slots:
        if isinstance(slot, NormalizedInventorySlot):
            slot_id = slot.inventory_id
            exp_unique = slot.unique_name
            interval = slot.level_interval
        elif isinstance(slot, dict):
            slot_id = str(slot.get("inventory_id", ""))
            exp_unique = slot.get("unique_name")
            interval = slot.get("level_interval")
        else:
            slot_id = str(getattr(slot, "inventory_id", ""))
            exp_unique = getattr(slot, "unique_name", None)
            interval = getattr(slot, "level_interval", None)

        if not slot_id:
            continue

        if interval is not None and not isinstance(interval, LevelInterval):
            interval = parse_level_interval(interval)

        # 1. Level eligibility
        elig_res = evaluate_eligibility(interval, valid_level)

        # 2. Slot-scoped observation coverage (conservative default: UNKNOWN)
        slot_coverage = coverage_map.get(slot_id, ObservationCoverage.UNKNOWN)

        # 3. Check observed equipment for this slot
        obs_item = observed_equipment.get(slot_id)
        if obs_item is None:
            status, reason = evaluate_delta_item(
                target_eligibility=elig_res.state,
                player_observation_exists=False,
                is_stale=False,
                verification_state=VerificationState.UNKNOWN,
                observation_coverage=slot_coverage,
                is_entity_present=False,
            )
            results.append(
                EquipmentDeltaEntry(
                    slot_id=slot_id,
                    expected_unique_name=exp_unique,
                    status=status,
                    reason=reason,
                )
            )
            continue

        # Observation exists for this slot
        is_stale = bool(
            obs_item.get("is_stale", False)
            or obs_item.get("verification_state") == VerificationState.STALE
        )
        v_state = obs_item.get("verification_state", VerificationState.UNKNOWN)
        if isinstance(v_state, str):
            try:
                v_state = VerificationState(v_state)
            except ValueError:
                v_state = VerificationState.UNKNOWN

        obs_unique = obs_item.get("unique_name")
        obs_base = obs_item.get("base_type")
        obs_prov = obs_item.get("provenance")

        # Check match
        if exp_unique:
            is_present = _normalize_name(exp_unique) == _normalize_name(obs_unique)
        else:
            is_present = bool(obs_unique or obs_base)

        status, reason = evaluate_delta_item(
            target_eligibility=elig_res.state,
            player_observation_exists=True,
            is_stale=is_stale,
            verification_state=v_state,
            observation_coverage=slot_coverage,
            is_entity_present=is_present,
        )

        results.append(
            EquipmentDeltaEntry(
                slot_id=slot_id,
                expected_unique_name=exp_unique,
                observed_unique_name=obs_unique,
                observed_base_type=obs_base,
                status=status,
                reason=reason,
                observed_provenance=obs_prov,
            )
        )

    return results
