"""Semantic skill-group identity, gem level eligibility, and skill delta evaluation."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from companion.sources.interval import LevelInterval
from companion.sources.models_normalized import (
    NormalizedSkillEntry,
    NormalizedSupportSkill,
    is_cast_on_dodge_id,
)
from companion.sources.models_raw import RawSkillEntry
from companion.state.provenance import VerificationState
from companion.state.schema import CharacterState
from companion.build.eligibility import EligibilityState, evaluate_eligibility
from companion.build.input import ObservationCoverage
from companion.build.policy import DeltaReason, DeltaStatus, evaluate_delta_item
from companion.build.validation import validate_character_level


class TargetSupportGem(BaseModel):
    """Normalized target support gem within a skill group."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    level_interval: LevelInterval
    is_cast_on_dodge: bool = False
    source_provenance: str | None = None


class TargetSkillGroup(BaseModel):
    """Semantic target skill group with stable logical identity independent of group index."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    logical_key: tuple[str, str | None]  # (primary_gem_id, parent_meta_gem_id)
    primary_gem_id: str
    parent_meta_gem_id: str | None = None
    level_interval: LevelInterval
    is_meta_gem: bool = False
    child_active_gem_id: str | None = None
    support_skills: list[TargetSupportGem] = Field(default_factory=list)
    source_group_index: int = 0  # Retained strictly for audit provenance
    source_provenance: str | None = None


class SkillGroupDeltaEntry(BaseModel):
    """Structured delta comparison result for a target skill group."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    logical_key: tuple[str, str | None]
    primary_gem_id: str
    parent_meta_gem_id: str | None = None
    status: DeltaStatus
    reason: DeltaReason = DeltaReason.NONE
    level_interval: LevelInterval | None = None
    is_meta_gem: bool = False
    child_active_gem_id: str | None = None
    source_group_index: int = 0
    missing_support_ids: list[str] = Field(default_factory=list)
    present_support_ids: list[str] = Field(default_factory=list)
    provenance: str | None = None


def _is_active_skill_id(gem_id: str) -> bool:
    """Check if a gem ID refers to an active skill rather than a support gem."""
    norm = gem_id.lower()
    return "skillgem" in norm and not ("supportgem" in norm)


def canonicalize_target_skills(
    skills: list[Any],
    source_provenance: str | None = None,
) -> list[TargetSkillGroup]:
    """Canonicalize build skills into semantic skill groups.

    Preserves distinction between standalone active skills and gems socketed inside meta-gems.
    Retains source group index strictly for audit provenance.
    Does not infer weapon-set assignments absent from build sources.
    """
    skill_groups: list[TargetSkillGroup] = []

    for idx, s in enumerate(skills):
        if isinstance(s, (NormalizedSkillEntry, RawSkillEntry)):
            s_id = str(s.id)
            interval = s.level_interval
            is_cod = getattr(s, "is_cast_on_dodge", False) or is_cast_on_dodge_id(s_id)
            raw_supports = s.support_skills
        elif isinstance(s, dict):
            s_id = str(s.get("id", ""))
            interval = s.get("level_interval")
            is_cod = s.get("is_cast_on_dodge", False) or is_cast_on_dodge_id(s_id)
            raw_supports = s.get("support_skills", [])
        else:
            s_id = str(getattr(s, "id", ""))
            interval = getattr(s, "level_interval", None)
            is_cod = is_cast_on_dodge_id(s_id)
            raw_supports = getattr(s, "support_skills", [])

        # Process supports and meta-gem child gems
        child_active_id: str | None = None
        target_supports: list[TargetSupportGem] = []

        for sup in raw_supports:
            if isinstance(sup, (NormalizedSupportSkill, TargetSupportGem)):
                sup_id = str(sup.id)
                sup_interval = sup.level_interval
                sup_cod = getattr(sup, "is_cast_on_dodge", False) or is_cast_on_dodge_id(sup_id)
            elif isinstance(sup, dict):
                sup_id = str(sup.get("id", ""))
                sup_interval = sup.get("level_interval")
                sup_cod = sup.get("is_cast_on_dodge", False) or is_cast_on_dodge_id(sup_id)
            else:
                sup_id = str(getattr(sup, "id", ""))
                sup_interval = getattr(sup, "level_interval", None)
                sup_cod = is_cast_on_dodge_id(sup_id)

            # If parent is a meta-gem (e.g. Cast on Dodge) and this child is an active skill
            if is_cod and _is_active_skill_id(sup_id):
                child_active_id = sup_id
            else:
                target_supports.append(
                    TargetSupportGem(
                        id=sup_id,
                        level_interval=sup_interval,
                        is_cast_on_dodge=sup_cod,
                        source_provenance=source_provenance,
                    )
                )

        group_key = (s_id, None)

        skill_groups.append(
            TargetSkillGroup(
                logical_key=group_key,
                primary_gem_id=s_id,
                parent_meta_gem_id=None,
                level_interval=interval,
                is_meta_gem=is_cod,
                child_active_gem_id=child_active_id,
                support_skills=target_supports,
                source_group_index=idx,
                source_provenance=source_provenance,
            )
        )

    return skill_groups


def _gem_matches(pattern: str, candidate: str) -> bool:
    """Fuzzy-safe match between target gem ID and observed player gem ID."""
    p_norm = pattern.lower().replace("_", "").replace(" ", "")
    c_norm = candidate.lower().replace("_", "").replace(" ", "")
    return p_norm == c_norm or p_norm.endswith(c_norm) or c_norm.endswith(p_norm)


def _extract_player_skills(
    character_state: CharacterState,
) -> tuple[list[dict[str, Any]], bool, bool, VerificationState]:
    """Extract observed skills, observation existence, freshness, and verification state."""
    audit = character_state.audit or {}

    skills_raw = (
        getattr(character_state, "skills", None)
        or audit.get("skills")
        or audit.get("skills_observed")
    )

    obs_exists = (
        skills_raw is not None
        or audit.get("skill_last_completed") is not None
        or "skills_verification" in audit
    )

    is_stale = bool(
        audit.get("skills_is_stale", False)
        or audit.get("skills_verification") == VerificationState.STALE
    )

    v_state = audit.get("skills_verification", VerificationState.UNKNOWN)
    if isinstance(v_state, str):
        try:
            v_state = VerificationState(v_state)
        except ValueError:
            v_state = VerificationState.UNKNOWN

    extracted_skills: list[dict[str, Any]] = []
    if skills_raw:
        for item in skills_raw:
            if isinstance(item, str):
                extracted_skills.append({"id": item, "supports": []})
            elif isinstance(item, dict):
                extracted_skills.append(item)
            elif hasattr(item, "id"):
                extracted_skills.append({
                    "id": getattr(item, "id", ""),
                    "supports": [getattr(s, "id", str(s)) for s in getattr(item, "support_skills", [])],
                })

    return extracted_skills, obs_exists, is_stale, v_state


def evaluate_skill_delta(
    target_skills: list[TargetSkillGroup],
    character_state: CharacterState,
    coverage: ObservationCoverage = ObservationCoverage.UNKNOWN,
    character_level: int | None = None,
) -> list[SkillGroupDeltaEntry]:
    """Evaluate skill requirements against observed character state.

    Supports statuses PRESENT, MISSING, UNKNOWN, FUTURE, EXPIRED.
    Honors gem level eligibility (e.g. Cast on Dodge [58, 100] is FUTURE at level 52).
    Honors centralized observation coverage policy.
    """
    if character_level is None and character_state.level:
        character_level = character_state.level.value
    valid_level = validate_character_level(character_level)

    player_skills, obs_exists, is_stale, v_state = _extract_player_skills(character_state)

    results: list[SkillGroupDeltaEntry] = []

    for target in target_skills:
        # 1. Level eligibility
        elig_res = evaluate_eligibility(target.level_interval, valid_level)

        # 2. Check if primary gem is observed
        matched_obs: dict[str, Any] | None = None
        for obs in player_skills:
            obs_id = obs.get("id", "")
            if _gem_matches(target.primary_gem_id, obs_id):
                matched_obs = obs
                break

        is_present = matched_obs is not None

        # 3. Policy evaluation
        status, reason = evaluate_delta_item(
            target_eligibility=elig_res.state,
            player_observation_exists=obs_exists,
            is_stale=is_stale,
            verification_state=v_state,
            observation_coverage=coverage,
            is_entity_present=is_present,
        )

        # 4. Supports evaluation if primary gem is present
        present_supports: list[str] = []
        missing_supports: list[str] = []
        if matched_obs:
            obs_supports = [str(s) for s in matched_obs.get("supports", [])]
            for sup in target.support_skills:
                if any(_gem_matches(sup.id, o_sup) for o_sup in obs_supports):
                    present_supports.append(sup.id)
                else:
                    missing_supports.append(sup.id)

        results.append(
            SkillGroupDeltaEntry(
                logical_key=target.logical_key,
                primary_gem_id=target.primary_gem_id,
                parent_meta_gem_id=target.parent_meta_gem_id,
                status=status,
                reason=reason,
                level_interval=target.level_interval,
                is_meta_gem=target.is_meta_gem,
                child_active_gem_id=target.child_active_gem_id,
                source_group_index=target.source_group_index,
                missing_support_ids=missing_supports,
                present_support_ids=present_supports,
                provenance=target.source_provenance,
            )
        )

    return results
