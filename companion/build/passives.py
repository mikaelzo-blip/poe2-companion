"""Passive logical identity, hardened canonicalization, and passive delta evaluation."""

from __future__ import annotations

from typing import Any
from collections import OrderedDict
from pydantic import BaseModel, ConfigDict, Field

from companion.sources.models_normalized import (
    NormalizedPassiveEntry,
    WeaponSetContext,
    map_weapon_set_context,
)
from companion.sources.models_raw import RawPassiveEntry
from companion.state.provenance import VerificationState
from companion.state.schema import CharacterState
from companion.build.conflicts import ConflictRecord
from companion.build.eligibility import EligibilityState
from companion.build.input import ObservationCoverage
from companion.build.policy import DeltaReason, DeltaStatus, evaluate_delta_item


class CanonicalTargetPassive(BaseModel):
    """Canonical target passive node preserving source occurrences and duplicate audit."""
    model_config = ConfigDict(frozen=True)

    key: tuple[str, WeaponSetContext]
    passive_id: str
    weapon_set_context: WeaponSetContext
    required_count: int = 1  # Exactly 1 allocation required
    source_occurrences: int  # Total raw rows (e.g. 2)
    source_indices: list[int]  # Raw row indices (e.g. [9, 21])
    raw_weapon_sets: list[int | None] = Field(default_factory=list)
    has_conflict: bool = False
    source_provenance: str | None = None


class PassiveDeltaEntry(BaseModel):
    """Structured delta comparison result for a single passive requirement."""
    model_config = ConfigDict(frozen=True)

    key: tuple[str, WeaponSetContext]
    passive_id: str
    weapon_set_context: WeaponSetContext
    status: DeltaStatus
    reason: DeltaReason = DeltaReason.NONE
    required_count: int = 1
    observed_in_state: bool = False
    source_occurrences: int = 1
    provenance: str | None = None


def canonicalize_target_passives(
    passives: list[Any],
    source_provenance: str | None = None,
) -> tuple[list[CanonicalTargetPassive], list[ConflictRecord]]:
    """Canonicalize raw or normalized target passive rows into single allocation requirements.

    Rules:
    - Identity is the compound key (passive_id, weapon_set_context).
    - Preserves all raw source occurrences, counts, and original row indices.
    - Exactly 1 allocation requirement is generated per logical key.
    - Duplicate raw rows with identical metadata canonicalize cleanly without conflict.
    - Duplicate raw rows with materially conflicting metadata generate CONFLICTING_EVIDENCE records.
    """
    grouped: OrderedDict[tuple[str, WeaponSetContext], list[dict[str, Any]]] = OrderedDict()
    conflicts: list[ConflictRecord] = []

    for idx, item in enumerate(passives):
        if isinstance(item, NormalizedPassiveEntry):
            p_id = item.passive_id
            ws_ctx = item.weapon_set_context
            raw_ws = item.raw_weapon_set
            orig_indices = item.original_indices or [idx]
            extra = {}
        elif isinstance(item, RawPassiveEntry):
            p_id = item.passive_id_str
            ws_ctx, _ = map_weapon_set_context(item.weapon_set)
            raw_ws = item.weapon_set
            orig_indices = [idx]
            extra = item.model_extra or {}
        elif isinstance(item, dict):
            p_id = str(item.get("id", item.get("passive_id", "")))
            raw_ws = item.get("weapon_set")
            ws_ctx, _ = map_weapon_set_context(raw_ws)
            orig_indices = item.get("original_indices", [idx])
            extra = item.get("metadata", item.get("extra", {}))
        else:
            p_id = str(getattr(item, "id", getattr(item, "passive_id", "")))
            raw_ws = getattr(item, "weapon_set", None)
            ws_ctx, _ = map_weapon_set_context(raw_ws)
            orig_indices = [idx]
            extra = getattr(item, "metadata", {})

        compound_key = (p_id, ws_ctx)
        if compound_key not in grouped:
            grouped[compound_key] = []

        grouped[compound_key].append({
            "idx": idx,
            "orig_indices": orig_indices,
            "raw_ws": raw_ws,
            "metadata": extra,
        })

    canonical_list: list[CanonicalTargetPassive] = []

    for key, occurrences in grouped.items():
        p_id, ws_ctx = key
        all_indices: list[int] = []
        all_raw_ws: list[int | None] = []
        for occ in occurrences:
            all_indices.extend(occ["orig_indices"])
            all_raw_ws.append(occ["raw_ws"])

        # Check for material conflicts among duplicates
        has_conflict = False
        if len(occurrences) > 1:
            first_meta = occurrences[0]["metadata"]
            for occ in occurrences[1:]:
                if occ["metadata"] != first_meta:
                    has_conflict = True
                    conflicts.append(
                        ConflictRecord(
                            field_name=f"passive:{p_id}:{ws_ctx.value}",
                            conflicting_sources=[source_provenance or "TARGET_SNAPSHOT"],
                            conflicting_values=[occ["metadata"] for occ in occurrences],
                            status="CONFLICTING_EVIDENCE",
                            details="Duplicate raw passive entries have conflicting metadata.",
                        )
                    )
                    break

        canonical_list.append(
            CanonicalTargetPassive(
                key=key,
                passive_id=p_id,
                weapon_set_context=ws_ctx,
                required_count=1,
                source_occurrences=len(occurrences),
                source_indices=all_indices,
                raw_weapon_sets=all_raw_ws,
                has_conflict=has_conflict,
                source_provenance=source_provenance,
            )
        )

    return canonical_list, conflicts


def _extract_player_passives(
    character_state: CharacterState,
) -> tuple[set[tuple[str, WeaponSetContext]], bool, bool, VerificationState]:
    """Extract observed allocated passives, observation existence, freshness, and verification state."""
    audit = character_state.audit or {}

    allocated_raw = (
        getattr(character_state, "allocated_passives", None)
        or audit.get("allocated_passives")
        or audit.get("passives")
    )

    observation_exists = (
        allocated_raw is not None
        or audit.get("passive_checkpoint_last_completed") is not None
        or "passives_verification" in audit
    )

    is_stale = bool(
        audit.get("passives_is_stale", False)
        or audit.get("passives_verification") == VerificationState.STALE
    )

    v_state = audit.get("passives_verification", VerificationState.UNKNOWN)
    if isinstance(v_state, str):
        try:
            v_state = VerificationState(v_state)
        except ValueError:
            v_state = VerificationState.UNKNOWN

    allocated_set: set[tuple[str, WeaponSetContext]] = set()
    if allocated_raw:
        for item in allocated_raw:
            if isinstance(item, tuple) and len(item) == 2:
                p_id, ctx = item
                if isinstance(ctx, WeaponSetContext):
                    allocated_set.add((str(p_id), ctx))
                else:
                    mapped_ctx, _ = map_weapon_set_context(ctx if isinstance(ctx, int) else None)
                    allocated_set.add((str(p_id), mapped_ctx))
            elif isinstance(item, str):
                allocated_set.add((item, WeaponSetContext.DEFAULT_OR_SHARED))

    return allocated_set, observation_exists, is_stale, v_state


def evaluate_passive_delta(
    target_passives: list[CanonicalTargetPassive],
    character_state: CharacterState,
    coverage: ObservationCoverage = ObservationCoverage.UNKNOWN,
    target_eligibility: EligibilityState = EligibilityState.ACTIVE,
) -> list[PassiveDeltaEntry]:
    """Evaluate passive requirements against observed character state.

    Supports statuses PRESENT, MISSING, EXTRA, UNKNOWN, FUTURE, EXPIRED.
    Honors centralized observation coverage policy.
    """
    allocated_set, obs_exists, is_stale, v_state = _extract_player_passives(character_state)

    results: list[PassiveDeltaEntry] = []
    target_keys: set[tuple[str, WeaponSetContext]] = set()

    for target in target_passives:
        target_keys.add(target.key)
        is_present = target.key in allocated_set

        status, reason = evaluate_delta_item(
            target_eligibility=target_eligibility,
            player_observation_exists=obs_exists,
            is_stale=is_stale,
            verification_state=v_state,
            observation_coverage=coverage,
            is_entity_present=is_present,
        )

        results.append(
            PassiveDeltaEntry(
                key=target.key,
                passive_id=target.passive_id,
                weapon_set_context=target.weapon_set_context,
                status=status,
                reason=reason,
                required_count=target.required_count,
                observed_in_state=is_present,
                source_occurrences=target.source_occurrences,
                provenance=target.source_provenance,
            )
        )

    # If coverage is COMPLETE and observations exist, check for EXTRA passives
    if obs_exists and coverage == ObservationCoverage.COMPLETE and not is_stale:
        for player_passive_key in allocated_set:
            if player_passive_key not in target_keys:
                results.append(
                    PassiveDeltaEntry(
                        key=player_passive_key,
                        passive_id=player_passive_key[0],
                        weapon_set_context=player_passive_key[1],
                        status=DeltaStatus.EXTRA,
                        reason=DeltaReason.NONE,
                        required_count=0,
                        observed_in_state=True,
                        source_occurrences=0,
                        provenance=None,
                    )
                )

    return results
