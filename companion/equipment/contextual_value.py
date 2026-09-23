"""Contextual marginal value and deficiency impact evaluation."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.partial_projection import PartialLoadoutProjection, StatProjection
from companion.equipment.resistance import ResistanceType, ResistanceTarget


class MarginalValueTier(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"
    NO_IMMEDIATE_VALUE = "NO_IMMEDIATE_VALUE"
    UNKNOWN = "UNKNOWN"


class DeficiencyImpact(str, Enum):
    RESOLVES = "RESOLVES"
    IMPROVES = "IMPROVES"
    UNCHANGED = "UNCHANGED"
    WORSENS = "WORSENS"
    CREATES_NEW_DEFICIENCY = "CREATES_NEW_DEFICIENCY"
    UNKNOWN = "UNKNOWN"


class ContextualResistanceAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    res_type: ResistanceType
    current_raw: int | None = None
    current_effective: int | None = None
    delta: float = 0.0
    projected_raw: int | None = None
    projected_effective: int | None = None
    target: int = 75
    deficit_before: int = 0
    deficit_after: int = 0
    impact: DeficiencyImpact = DeficiencyImpact.UNCHANGED
    tier: MarginalValueTier = MarginalValueTier.NORMAL
    overcap_buffer_before: int = 0
    overcap_buffer_after: int = 0
    is_known: bool = True
    reason: str = ""


class ContextualAttributeAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    attribute_name: str
    current_value: int | None = None
    delta: float = 0.0
    projected_value: int | None = None
    highest_required: int | None = None
    deficit_before: int = 0
    deficit_after: int = 0
    impact: DeficiencyImpact = DeficiencyImpact.UNCHANGED
    tier: MarginalValueTier = MarginalValueTier.NORMAL
    is_known: bool = True
    reason: str = ""


class LoadoutContextualAnalysis(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    resistances: dict[ResistanceType, ContextualResistanceAnalysis] = Field(default_factory=dict)
    attributes: dict[str, ContextualAttributeAnalysis] = Field(default_factory=dict)
    has_critical_deficiency: bool = False
    critical_deficiency_details: list[str] = Field(default_factory=list)
    has_unchanged_critical_deficiency: bool = False
    has_worsened_deficiency: bool = False
    has_resolved_deficiency: bool = False
    has_improved_deficiency: bool = False
    has_created_deficiency: bool = False


def evaluate_contextual_resistance(
    baseline: CharacterStatBaseline | None,
    res_type: ResistanceType,
    delta: float,
    target: ResistanceTarget | int | None = None,
) -> ContextualResistanceAnalysis:
    """Evaluates contextual resistance value and deficiency impact based on baseline and delta."""
    effective_target: int
    overcap_target_buf: int = 20
    max_cap: int = 75

    if isinstance(target, ResistanceTarget):
        effective_target = target.target_effective
        overcap_target_buf = target.target_overcap_buffer
        max_cap = target.max_res
    elif isinstance(target, int):
        effective_target = target
        max_cap = max(75, target)
    else:
        if res_type == ResistanceType.CHAOS:
            effective_target = 0
            overcap_target_buf = 0
        else:
            effective_target = 75
            overcap_target_buf = 20

    if baseline is None:
        # Baseline unknown
        tier = MarginalValueTier.NORMAL if delta != 0 else MarginalValueTier.NO_IMMEDIATE_VALUE
        return ContextualResistanceAnalysis(
            res_type=res_type,
            delta=delta,
            target=effective_target,
            impact=DeficiencyImpact.UNKNOWN,
            tier=MarginalValueTier.UNKNOWN,
            is_known=False,
            reason="Character baseline unknown; cannot determine contextual resistance impact.",
        )

    # Resolve facts from baseline
    if res_type == ResistanceType.FIRE:
        raw_fact = baseline.raw_fire_res
        eff_fact = baseline.effective_fire_res
        max_fact = baseline.max_fire_res
    elif res_type == ResistanceType.COLD:
        raw_fact = baseline.raw_cold_res
        eff_fact = baseline.effective_cold_res
        max_fact = baseline.max_cold_res
    elif res_type == ResistanceType.LIGHTNING:
        raw_fact = baseline.raw_lightning_res
        eff_fact = baseline.effective_lightning_res
        max_fact = baseline.max_lightning_res
    else:
        raw_fact = baseline.raw_chaos_res
        eff_fact = baseline.effective_chaos_res
        max_fact = baseline.max_chaos_res

    # Check knownness
    if not eff_fact.is_known and not raw_fact.is_known:
        return ContextualResistanceAnalysis(
            res_type=res_type,
            delta=delta,
            target=effective_target,
            impact=DeficiencyImpact.UNKNOWN,
            tier=MarginalValueTier.UNKNOWN,
            is_known=False,
            reason=f"{res_type.value.capitalize()} resistance is not observed in baseline.",
        )

    # If raw is known, use raw, otherwise fall back to effective
    if raw_fact.is_known and raw_fact.value is not None:
        raw_val = raw_fact.value
        char_max = max_fact.value if (max_fact.is_known and max_fact.value is not None) else max_cap
        eff_val = min(raw_val, char_max)
        overcap_before = max(0, raw_val - char_max)

        proj_raw = int(raw_val + delta)
        proj_eff = min(proj_raw, char_max)
        overcap_after = max(0, proj_raw - char_max)
    else:
        # Effective is known, raw is not explicitly known
        eff_val = eff_fact.value if (eff_fact.is_known and eff_fact.value is not None) else 0
        raw_val = eff_val
        char_max = max_fact.value if (max_fact.is_known and max_fact.value is not None) else max_cap
        overcap_before = 0

        # Project effective with capping
        proj_raw = int(raw_val + delta)
        proj_eff = min(char_max, int(eff_val + delta))
        overcap_after = max(0, proj_raw - char_max)

    def_before = max(0, effective_target - eff_val)
    def_after = max(0, effective_target - proj_eff)

    # Classify impact
    impact: DeficiencyImpact
    tier: MarginalValueTier
    reason: str

    if def_before > 0:
        # There was a deficiency before
        if def_after == 0:
            impact = DeficiencyImpact.RESOLVES
            tier = MarginalValueTier.CRITICAL
            reason = f"Resolves {res_type.value} resistance deficit (from {eff_val}% to {proj_eff}%, target {effective_target}%)."
        elif def_after < def_before:
            impact = DeficiencyImpact.IMPROVES
            # High or critical depending on deficit size
            tier = MarginalValueTier.HIGH if def_before < 30 else MarginalValueTier.CRITICAL
            reason = f"Improves {res_type.value} resistance deficit (from {eff_val}% to {proj_eff}%, remaining deficit {def_after}%)."
        elif def_after == def_before:
            impact = DeficiencyImpact.UNCHANGED
            # Critical deficiency remains unchanged
            tier = MarginalValueTier.NO_IMMEDIATE_VALUE if delta == 0 else MarginalValueTier.LOW
            reason = f"No change to existing {res_type.value} resistance deficit of {def_before}%."
        else:
            impact = DeficiencyImpact.WORSENS
            tier = MarginalValueTier.CRITICAL
            reason = f"Worsens existing {res_type.value} resistance deficit (from {eff_val}% to {proj_eff}%)."
    else:
        # No deficiency before (character was at or above target)
        if def_after > 0:
            impact = DeficiencyImpact.CREATES_NEW_DEFICIENCY
            tier = MarginalValueTier.CRITICAL
            reason = f"Creates new {res_type.value} resistance deficit of {def_after}% (dropped to {proj_eff}%)."
        else:
            impact = DeficiencyImpact.UNCHANGED
            if delta > 0:
                # Adding more overcap
                if overcap_before < overcap_target_buf:
                    tier = MarginalValueTier.LOW
                    reason = f"Adds to overcap buffer ({proj_raw}% raw, buffer {overcap_after}%)."
                else:
                    tier = MarginalValueTier.NO_IMMEDIATE_VALUE
                    reason = f"Already overcapped past buffer; provides no immediate defensive gain ({proj_raw}% raw)."
            elif delta < 0:
                # Losing some overcap, but remaining at or above target
                if overcap_after < overcap_target_buf:
                    tier = MarginalValueTier.NORMAL
                    reason = f"Reduces overcap buffer from {overcap_before}% to {overcap_after}% (remains capped)."
                else:
                    tier = MarginalValueTier.LOW
                    reason = f"Losing excess overcap beyond buffer ({overcap_before}% -> {overcap_after}%), remains safely capped."
            else:
                tier = MarginalValueTier.NO_IMMEDIATE_VALUE
                reason = "No change."

    return ContextualResistanceAnalysis(
        res_type=res_type,
        current_raw=raw_val,
        current_effective=eff_val,
        delta=delta,
        projected_raw=proj_raw,
        projected_effective=proj_eff,
        target=effective_target,
        deficit_before=def_before,
        deficit_after=def_after,
        impact=impact,
        tier=tier,
        overcap_buffer_before=overcap_before,
        overcap_buffer_after=overcap_after,
        is_known=True,
        reason=reason,
    )


def evaluate_contextual_attribute(
    baseline: CharacterStatBaseline | None,
    attr_name: str,
    delta: float,
    highest_required: int | None = None,
) -> ContextualAttributeAnalysis:
    """Evaluates contextual attribute value and requirement deficiency impact."""
    normalized_name = attr_name.lower().strip()
    if normalized_name in ("str", "strength"):
        attr_key = "strength"
    elif normalized_name in ("dex", "dexterity"):
        attr_key = "dexterity"
    elif normalized_name in ("int", "intelligence"):
        attr_key = "intelligence"
    else:
        attr_key = normalized_name

    if baseline is None:
        return ContextualAttributeAnalysis(
            attribute_name=attr_key,
            delta=delta,
            highest_required=highest_required,
            impact=DeficiencyImpact.UNKNOWN,
            tier=MarginalValueTier.UNKNOWN,
            is_known=False,
            reason="Character baseline unknown; cannot determine contextual attribute impact.",
        )

    fact = getattr(baseline, attr_key, None)
    if fact is None or not fact.is_known or fact.value is None:
        return ContextualAttributeAnalysis(
            attribute_name=attr_key,
            delta=delta,
            highest_required=highest_required,
            impact=DeficiencyImpact.UNKNOWN,
            tier=MarginalValueTier.UNKNOWN,
            is_known=False,
            reason=f"Attribute '{attr_key}' is not observed in baseline.",
        )

    current_val = fact.value
    projected_val = int(current_val + delta)

    if highest_required is None:
        # No specific requirement threshold provided
        tier = MarginalValueTier.NORMAL if delta > 0 else (MarginalValueTier.LOW if delta < 0 else MarginalValueTier.NO_IMMEDIATE_VALUE)
        return ContextualAttributeAnalysis(
            attribute_name=attr_key,
            current_value=current_val,
            delta=delta,
            projected_value=projected_val,
            highest_required=None,
            deficit_before=0,
            deficit_after=0,
            impact=DeficiencyImpact.UNCHANGED,
            tier=tier,
            is_known=True,
            reason=f"No requirement threshold; delta is {delta:+0.0f}.",
        )

    def_before = max(0, highest_required - current_val)
    def_after = max(0, highest_required - projected_val)

    impact: DeficiencyImpact
    tier: MarginalValueTier
    reason: str

    if def_before > 0:
        if def_after == 0:
            impact = DeficiencyImpact.RESOLVES
            tier = MarginalValueTier.CRITICAL
            reason = f"Resolves {attr_key} requirement deficit (from {current_val} to {projected_val}, required {highest_required})."
        elif def_after < def_before:
            impact = DeficiencyImpact.IMPROVES
            tier = MarginalValueTier.HIGH
            reason = f"Improves {attr_key} requirement deficit (from {current_val} to {projected_val}, still short {def_after})."
        elif def_after == def_before:
            impact = DeficiencyImpact.UNCHANGED
            tier = MarginalValueTier.NO_IMMEDIATE_VALUE if delta == 0 else MarginalValueTier.LOW
            reason = f"No change to existing {attr_key} deficit of {def_before}."
        else:
            impact = DeficiencyImpact.WORSENS
            tier = MarginalValueTier.CRITICAL
            reason = f"Worsens existing {attr_key} deficit (dropped to {projected_val}, short {def_after})."
    else:
        if def_after > 0:
            impact = DeficiencyImpact.CREATES_NEW_DEFICIENCY
            tier = MarginalValueTier.CRITICAL
            reason = f"Causes new {attr_key} requirement deficiency of {def_after} (dropped from {current_val} to {projected_val}, required {highest_required})."
        else:
            impact = DeficiencyImpact.UNCHANGED
            tier = MarginalValueTier.LOW if delta != 0 else MarginalValueTier.NO_IMMEDIATE_VALUE
            reason = f"Surplus remains satisfied ({projected_val} vs required {highest_required})."

    return ContextualAttributeAnalysis(
        attribute_name=attr_key,
        current_value=current_val,
        delta=delta,
        projected_value=projected_val,
        highest_required=highest_required,
        deficit_before=def_before,
        deficit_after=def_after,
        impact=impact,
        tier=tier,
        is_known=True,
        reason=reason,
    )


def evaluate_loadout_contextual_analysis(
    baseline: CharacterStatBaseline | None,
    projection: PartialLoadoutProjection | None = None,
    delta_res: dict[ResistanceType, float] | None = None,
    delta_attrs: dict[str, float] | None = None,
    highest_attribute_requirements: dict[str, int] | None = None,
    resistance_targets: dict[ResistanceType, ResistanceTarget] | None = None,
) -> LoadoutContextualAnalysis:
    """Evaluates contextual analysis across all resistances and attributes for a candidate loadout change."""
    res_analysis: dict[ResistanceType, ContextualResistanceAnalysis] = {}
    attr_analysis: dict[str, ContextualAttributeAnalysis] = {}
    crit_details: list[str] = []

    # Map deltas from projection if provided
    res_deltas: dict[ResistanceType, float] = {}
    attr_deltas: dict[str, float] = {}

    if projection is not None:
        res_deltas[ResistanceType.FIRE] = projection.fire_res.delta
        res_deltas[ResistanceType.COLD] = projection.cold_res.delta
        res_deltas[ResistanceType.LIGHTNING] = projection.lightning_res.delta
        res_deltas[ResistanceType.CHAOS] = projection.chaos_res.delta

        attr_deltas["strength"] = projection.strength.delta
        attr_deltas["dexterity"] = projection.dexterity.delta
        attr_deltas["intelligence"] = projection.intelligence.delta

    if delta_res is not None:
        res_deltas.update(delta_res)

    if delta_attrs is not None:
        attr_deltas.update(delta_attrs)

    # Evaluate each resistance
    for r_type in (ResistanceType.FIRE, ResistanceType.COLD, ResistanceType.LIGHTNING, ResistanceType.CHAOS):
        r_delta = res_deltas.get(r_type, 0.0)
        target_obj = resistance_targets.get(r_type) if resistance_targets else None
        analysis = evaluate_contextual_resistance(baseline, r_type, r_delta, target=target_obj)
        res_analysis[r_type] = analysis

        if analysis.deficit_before > 0:
            crit_details.append(f"{r_type.value.capitalize()} resistance deficit ({analysis.deficit_before}% short of target).")

    # Evaluate each attribute
    reqs = highest_attribute_requirements or {}
    for a_name in ("strength", "dexterity", "intelligence"):
        a_delta = attr_deltas.get(a_name, 0.0)
        h_req = reqs.get(a_name) or reqs.get(a_name[:3])
        analysis = evaluate_contextual_attribute(baseline, a_name, a_delta, highest_required=h_req)
        attr_analysis[a_name] = analysis

        if analysis.deficit_before > 0:
            crit_details.append(f"{a_name.capitalize()} attribute deficit ({analysis.deficit_before} short of required {analysis.highest_required}).")

    # Check overall flags
    has_critical = len(crit_details) > 0
    has_unchanged_crit = any(
        (r.deficit_before > 0 and r.impact == DeficiencyImpact.UNCHANGED)
        for r in res_analysis.values()
    ) or any(
        (a.deficit_before > 0 and a.impact == DeficiencyImpact.UNCHANGED)
        for a in attr_analysis.values()
    )

    has_worsened = any(
        r.impact == DeficiencyImpact.WORSENS for r in res_analysis.values()
    ) or any(
        a.impact == DeficiencyImpact.WORSENS for a in attr_analysis.values()
    )

    has_resolved = any(
        r.impact == DeficiencyImpact.RESOLVES for r in res_analysis.values()
    ) or any(
        a.impact == DeficiencyImpact.RESOLVES for a in attr_analysis.values()
    )

    has_improved = any(
        r.impact == DeficiencyImpact.IMPROVES for r in res_analysis.values()
    ) or any(
        a.impact == DeficiencyImpact.IMPROVES for a in attr_analysis.values()
    )

    has_created = any(
        r.impact == DeficiencyImpact.CREATES_NEW_DEFICIENCY for r in res_analysis.values()
    ) or any(
        a.impact == DeficiencyImpact.CREATES_NEW_DEFICIENCY for a in attr_analysis.values()
    )

    return LoadoutContextualAnalysis(
        resistances=res_analysis,
        attributes=attr_analysis,
        has_critical_deficiency=has_critical,
        critical_deficiency_details=crit_details,
        has_unchanged_critical_deficiency=has_unchanged_crit,
        has_worsened_deficiency=has_worsened,
        has_resolved_deficiency=has_resolved,
        has_improved_deficiency=has_improved,
        has_created_deficiency=has_created,
    )
