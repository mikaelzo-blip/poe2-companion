"""Build-specific Fubgun Weapon Profile Router.

RESPONSIBILITY BOUNDARY:
- Build-specific weapon progression routing for Fubgun 0.5.5 Flameblast / Oil Grenade.
- Maps candidates to progression stages (pre-swap leveling vs post-swap dual-set).
- Resolves target weapon set (Set 1 vs Set 2), target slot, and relevant skill context.
- Enforces build-breaker gating on weapon slots (e.g. flat fire to attacks on Crossbows).
- Exempts Flameblast staves in Weapon Set 1 from the fire rule.
- Produces explicit WeaponSimulationContext for mathematical simulation execution.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.build_breaker import evaluate_candidate_build_safety
from companion.equipment.rules import BuildBreakerCertainty, BuildProgressionStage, RuleSeverity
from companion.equipment.schema import ItemCandidate, SlotType, WeaponSetContext
from companion.equipment.weapon_topology import (
    WeaponArchetype,
    WeaponTopologyPlan,
    WeaponTopologyResolver,
    derive_weapon_archetype,
)


class WeaponSimulationContext(BaseModel):
    """Explicit, strongly typed context bundle for headless PoB2 weapon simulation."""

    model_config = ConfigDict(frozen=True)

    target_set: WeaponSetContext
    target_slot: str
    skill_context: str | None = None
    weapon_archetype: WeaponArchetype
    topology_plan: WeaponTopologyPlan
    build_stage: BuildProgressionStage
    candidate_id: int = 0
    candidate_name: str = ""
    raw_candidate: str = ""


class FubgunWeaponRoutingResult(BaseModel):
    """Result of evaluating a weapon candidate against the Fubgun weapon plan."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool
    rejection_reason: str = ""
    target_set: WeaponSetContext = WeaponSetContext.WEAPON_SET_1
    target_slot: str = "Weapon 1"
    skill_context: str | None = None
    weapon_archetype: WeaponArchetype = WeaponArchetype.UNKNOWN_WEAPON
    topology_plan: WeaponTopologyPlan | None = None
    context: WeaponSimulationContext | None = None


class FubgunWeaponProfileRouter:
    """Build-specific router for Fubgun Flameblast / Oil Grenade weapon progression."""

    def __init__(self, topology_resolver: WeaponTopologyResolver | None = None):
        self.topology_resolver = topology_resolver or WeaponTopologyResolver()

    def route_candidate(
        self,
        candidate: ItemCandidate,
        stage: BuildProgressionStage,
        raw_text: str = "",
        candidate_id: int = 0,
        currently_equipped: dict[str, str | None] | None = None,
    ) -> FubgunWeaponRoutingResult:
        """Route a candidate weapon against the stage-aware Fubgun weapon plan."""
        archetype = derive_weapon_archetype(candidate)
        candidate_name = candidate.name or candidate.base_type or "Candidate Weapon"

        # 1. Reject Bows and Quivers across all stages
        if archetype == WeaponArchetype.TWO_HAND_BOW:
            return FubgunWeaponRoutingResult(
                is_valid=False,
                rejection_reason="Bows are not part of Fubgun Flameblast / Oil Grenade build.",
                weapon_archetype=archetype,
            )
        if archetype == WeaponArchetype.OFF_HAND_QUIVER:
            return FubgunWeaponRoutingResult(
                is_valid=False,
                rejection_reason="Quivers are not part of Fubgun Flameblast / Oil Grenade build.",
                weapon_archetype=archetype,
            )

        # 2. Reject 2H weapons other than Staff or Crossbow
        if archetype == WeaponArchetype.TWO_HAND_OTHER:
            return FubgunWeaponRoutingResult(
                is_valid=False,
                rejection_reason="Two-handed melee weapons (Axes, Swords, Maces) are not supported by Fubgun build.",
                weapon_archetype=archetype,
            )

        # 3. Pre-swap progression stages
        if stage.is_pre_swap:
            if archetype == WeaponArchetype.TWO_HAND_CROSSBOW:
                target_set = WeaponSetContext.WEAPON_SET_1
                target_slot = "Weapon 1"
                # Pre-swap stages (lvl 1-14, lvl 15-32, lvl 33-51) use stage-resolved crossbow leveling context
                skill_context = "CROSSBOW_LEVELING"
                plan = self.topology_resolver.resolve_topology(
                    candidate=candidate,
                    target_set=target_set,
                    currently_equipped=currently_equipped,
                )
                sim_ctx = WeaponSimulationContext(
                    target_set=target_set,
                    target_slot=target_slot,
                    skill_context=skill_context,
                    weapon_archetype=archetype,
                    topology_plan=plan,
                    build_stage=stage,
                    candidate_id=candidate_id,
                    candidate_name=candidate_name,
                    raw_candidate=raw_text,
                )
                return FubgunWeaponRoutingResult(
                    is_valid=True,
                    target_set=target_set,
                    target_slot=target_slot,
                    skill_context=skill_context,
                    weapon_archetype=archetype,
                    topology_plan=plan,
                    context=sim_ctx,
                )

            if archetype == WeaponArchetype.TWO_HAND_STAFF:
                return FubgunWeaponRoutingResult(
                    is_valid=False,
                    rejection_reason="Staves are used post-swap (level 52+) for Flameblast; use a Crossbow during leveling.",
                    weapon_archetype=archetype,
                )

            return FubgunWeaponRoutingResult(
                is_valid=False,
                rejection_reason=f"Weapon type '{archetype.value}' is not used during pre-swap leveling.",
                weapon_archetype=archetype,
            )

        # 4. Post-swap progression stages (Swap 52, Endgame, etc.)
        if archetype == WeaponArchetype.TWO_HAND_STAFF:
            # Weapon Set 1: Flameblast Staff (Fire spell damage is explicitly exempt)
            target_set = WeaponSetContext.WEAPON_SET_1
            target_slot = "Weapon 1"
            skill_context = "Flameblast"
            plan = self.topology_resolver.resolve_topology(
                candidate=candidate,
                target_set=target_set,
                currently_equipped=currently_equipped,
            )
            sim_ctx = WeaponSimulationContext(
                target_set=target_set,
                target_slot=target_slot,
                skill_context=skill_context,
                weapon_archetype=archetype,
                topology_plan=plan,
                build_stage=stage,
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                raw_candidate=raw_text,
            )
            return FubgunWeaponRoutingResult(
                is_valid=True,
                target_set=target_set,
                target_slot=target_slot,
                skill_context=skill_context,
                weapon_archetype=archetype,
                topology_plan=plan,
                context=sim_ctx,
            )

        if archetype == WeaponArchetype.TWO_HAND_CROSSBOW:
            # Weapon Set 2: Oil Grenade Crossbow
            # Enforce build-breaker check: flat fire to attacks breaks Oil Grenade ignite!
            safety = evaluate_candidate_build_safety(
                candidate=candidate,
                slot=SlotType.MAIN_HAND,
                weapon_set=WeaponSetContext.WEAPON_SET_2,
                stage=stage,
            )
            if safety.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER:
                return FubgunWeaponRoutingResult(
                    is_valid=False,
                    rejection_reason=f"BUILD BREAKER: {safety.reason}",
                    target_set=WeaponSetContext.WEAPON_SET_2,
                    target_slot="Weapon 1 Swap",
                    skill_context="Oil Grenade",
                    weapon_archetype=archetype,
                )

            target_set = WeaponSetContext.WEAPON_SET_2
            target_slot = "Weapon 1 Swap"
            skill_context = "Oil Grenade"
            plan = self.topology_resolver.resolve_topology(
                candidate=candidate,
                target_set=target_set,
                currently_equipped=currently_equipped,
            )
            sim_ctx = WeaponSimulationContext(
                target_set=target_set,
                target_slot=target_slot,
                skill_context=skill_context,
                weapon_archetype=archetype,
                topology_plan=plan,
                build_stage=stage,
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                raw_candidate=raw_text,
            )
            return FubgunWeaponRoutingResult(
                is_valid=True,
                target_set=target_set,
                target_slot=target_slot,
                skill_context=skill_context,
                weapon_archetype=archetype,
                topology_plan=plan,
                context=sim_ctx,
            )

        return FubgunWeaponRoutingResult(
            is_valid=False,
            rejection_reason=f"Weapon type '{archetype.value}' is not used in Fubgun post-swap dual-set loadout (Set 1: Staff, Set 2: Crossbow).",
            weapon_archetype=archetype,
        )
