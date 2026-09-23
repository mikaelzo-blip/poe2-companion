"""Post-setup baseline reconciler enforcing Resistance Rebase Policy and defense staleness."""

from __future__ import annotations

from datetime import datetime, timezone
from companion.state.provenance import VerificationState
from companion.equipment.baseline import (
    BaselineSource,
    CharacterFact,
    CharacterStatBaseline,
)
from companion.equipment.contribution import ItemContribution


def reconcile_baseline_after_swap(
    baseline: CharacterStatBaseline,
    displaced_contributions: list[ItemContribution],
    candidate_contribution: ItemContribution | None,
    new_loadout_revision: int,
) -> CharacterStatBaseline:
    """Reconcile baseline after an equipment mutation under strict Resistance Rebase Policy.

    - Rebase raw uncapped resistance when proven, clamping via min(new_raw, max_res)
    - If raw state is unproven, mark effective resistance STALE / UNKNOWN
    - Safely rebase linear attributes (Str, Dex, Int)
    - Mark complex non-linear defenses (Armour, Evasion, ES) STALE
    - Anchor to new_loadout_revision
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # Sum displaced contributions
    disp_fire = sum(c.fire_res_delta for c in displaced_contributions)
    disp_cold = sum(c.cold_res_delta for c in displaced_contributions)
    disp_light = sum(c.lightning_res_delta for c in displaced_contributions)
    disp_chaos = sum(c.chaos_res_delta for c in displaced_contributions)
    disp_str = sum(c.str_delta for c in displaced_contributions)
    disp_dex = sum(c.dex_delta for c in displaced_contributions)
    disp_int = sum(c.int_delta for c in displaced_contributions)
    disp_life = sum(c.life_delta for c in displaced_contributions)
    disp_armour = sum(c.local_armour for c in displaced_contributions)
    disp_evasion = sum(c.local_evasion for c in displaced_contributions)
    disp_es = sum(c.local_energy_shield for c in displaced_contributions)

    # Candidate contributions
    cand_fire = candidate_contribution.fire_res_delta if candidate_contribution else 0.0
    cand_cold = candidate_contribution.cold_res_delta if candidate_contribution else 0.0
    cand_light = candidate_contribution.lightning_res_delta if candidate_contribution else 0.0
    cand_chaos = candidate_contribution.chaos_res_delta if candidate_contribution else 0.0
    cand_str = candidate_contribution.str_delta if candidate_contribution else 0
    cand_dex = candidate_contribution.dex_delta if candidate_contribution else 0
    cand_int = candidate_contribution.int_delta if candidate_contribution else 0
    cand_life = candidate_contribution.life_delta if candidate_contribution else 0.0
    cand_armour = candidate_contribution.local_armour if candidate_contribution else 0
    cand_evasion = candidate_contribution.local_evasion if candidate_contribution else 0
    cand_es = candidate_contribution.local_energy_shield if candidate_contribution else 0

    net_fire = cand_fire - disp_fire
    net_cold = cand_cold - disp_cold
    net_light = cand_light - disp_light
    net_chaos = cand_chaos - disp_chaos
    net_str = cand_str - disp_str
    net_dex = cand_dex - disp_dex
    net_int = cand_int - disp_int
    net_life = cand_life - disp_life

    # Helper for reconciling resistance families
    def reconcile_res(
        raw_fact: CharacterFact[int],
        eff_fact: CharacterFact[int],
        max_fact: CharacterFact[int],
        buf_fact: CharacterFact[int],
        net_delta: float,
    ) -> tuple[CharacterFact[int], CharacterFact[int], CharacterFact[int], CharacterFact[int]]:
        # Can raw state be proven?
        # Proven if raw_fact.value is not None, OR eff_fact + overcap buffer is known
        proven_raw: int | None = None
        if raw_fact.value is not None and raw_fact.verification != VerificationState.UNKNOWN:
            proven_raw = raw_fact.value
        elif (
            eff_fact.value is not None
            and eff_fact.verification != VerificationState.UNKNOWN
            and buf_fact.value is not None
            and buf_fact.verification != VerificationState.UNKNOWN
        ):
            proven_raw = eff_fact.value + buf_fact.value

        if proven_raw is not None:
            new_raw = int(proven_raw + net_delta)
            cap_limit = max_fact.value if max_fact.is_known and max_fact.value is not None else 75
            new_eff = min(new_raw, cap_limit)
            new_buf = max(0, new_raw - cap_limit)
            return (
                CharacterFact[int](
                    value=new_raw,
                    source=BaselineSource.DERIVED_CALCULATION,
                    observed_at=now_iso,
                    verification=VerificationState.VERIFIED,
                ),
                CharacterFact[int](
                    value=new_eff,
                    source=BaselineSource.DERIVED_CALCULATION,
                    observed_at=now_iso,
                    verification=VerificationState.VERIFIED,
                ),
                max_fact,
                CharacterFact[int](
                    value=new_buf,
                    source=BaselineSource.DERIVED_CALCULATION,
                    observed_at=now_iso,
                    verification=VerificationState.VERIFIED,
                ),
            )

        # Raw state cannot be proven -> mark effective STALE / UNKNOWN without fabricating numbers!
        stale_eff = eff_fact.mark_stale() if eff_fact.value is not None else eff_fact
        return raw_fact, stale_eff, max_fact, buf_fact

    new_raw_fire, new_eff_fire, new_max_fire, new_buf_fire = reconcile_res(
        baseline.raw_fire_res, baseline.effective_fire_res, baseline.max_fire_res, baseline.fire_overcap_buffer, net_fire
    )
    new_raw_cold, new_eff_cold, new_max_cold, new_buf_cold = reconcile_res(
        baseline.raw_cold_res, baseline.effective_cold_res, baseline.max_cold_res, baseline.cold_overcap_buffer, net_cold
    )
    new_raw_light, new_eff_light, new_max_light, new_buf_light = reconcile_res(
        baseline.raw_lightning_res, baseline.effective_lightning_res, baseline.max_lightning_res, baseline.lightning_overcap_buffer, net_light
    )
    new_raw_chaos, new_eff_chaos, new_max_chaos, new_buf_chaos = reconcile_res(
        baseline.raw_chaos_res, baseline.effective_chaos_res, baseline.max_chaos_res, baseline.chaos_overcap_buffer, net_chaos
    )

    # Linear attributes rebase
    def reconcile_linear_stat(fact: CharacterFact[int], delta: int) -> CharacterFact[int]:
        if fact.is_known and fact.value is not None:
            return CharacterFact[int](
                value=fact.value + delta,
                source=BaselineSource.DERIVED_CALCULATION,
                observed_at=now_iso,
                verification=VerificationState.VERIFIED,
            )
        return fact

    new_str = reconcile_linear_stat(baseline.strength, net_str)
    new_dex = reconcile_linear_stat(baseline.dexterity, net_dex)
    new_int = reconcile_linear_stat(baseline.intelligence, net_int)

    # Defenses: complex non-linear stats subject to global multipliers are marked STALE
    new_armour = baseline.armour.mark_stale() if baseline.armour.value is not None else baseline.armour
    new_evasion = baseline.evasion.mark_stale() if baseline.evasion.value is not None else baseline.evasion
    new_es = baseline.energy_shield.mark_stale() if baseline.energy_shield.value is not None else baseline.energy_shield

    # Life (can also mark stale or rebase if additive)
    new_life = reconcile_linear_stat(baseline.life, int(net_life))

    return CharacterStatBaseline(
        baseline_id=baseline.baseline_id,
        character_id=baseline.character_id,
        anchored_loadout_revision=new_loadout_revision,
        life=new_life,
        armour=new_armour,
        evasion=new_evasion,
        energy_shield=new_es,
        raw_fire_res=new_raw_fire,
        effective_fire_res=new_eff_fire,
        max_fire_res=new_max_fire,
        fire_overcap_buffer=new_buf_fire,
        raw_cold_res=new_raw_cold,
        effective_cold_res=new_eff_cold,
        max_cold_res=new_max_cold,
        cold_overcap_buffer=new_buf_cold,
        raw_lightning_res=new_raw_light,
        effective_lightning_res=new_eff_light,
        max_lightning_res=new_max_light,
        lightning_overcap_buffer=new_buf_light,
        raw_chaos_res=new_raw_chaos,
        effective_chaos_res=new_eff_chaos,
        max_chaos_res=new_max_chaos,
        chaos_overcap_buffer=new_buf_chaos,
        strength=new_str,
        dexterity=new_dex,
        intelligence=new_int,
        movement_speed=baseline.movement_speed,
        observed_at=baseline.observed_at,
        updated_at=now_iso,
    )
