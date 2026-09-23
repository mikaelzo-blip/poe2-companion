"""Requirement cascade validation for full loadout and build-critical gems."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.loadout import ALL_SHARED_SLOTS, ALL_WEAPON_SLOTS, EquippedLoadout
from companion.equipment.partial_projection import project_candidate_on_loadout
from companion.equipment.schema import ItemCandidate, SlotOccupancy, SlotType, WeaponSetContext


class GemRequirement(BaseModel):
    model_config = ConfigDict(frozen=True)

    gem_name: str
    level: int = 1
    strength: int = 0
    dexterity: int = 0
    intelligence: int = 0
    is_critical: bool = True


class RequirementDeficiency(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_type: str  # "candidate", "equipped_item", "gem"
    target_name: str
    slot: SlotType | None = None
    attribute: str  # "str", "dex", "int", "level"
    required_value: int
    projected_value: int | None = None
    shortfall: int = 0


class RequirementCascadeResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    is_satisfied: bool = True
    candidate_deficiencies: list[RequirementDeficiency] = Field(default_factory=list)
    loadout_cascading_deficiencies: list[RequirementDeficiency] = Field(default_factory=list)
    gem_cascading_deficiencies: list[RequirementDeficiency] = Field(default_factory=list)
    verdict_downgrade: str | None = None
    summary: str = ""


def validate_requirement_cascades(
    loadout: EquippedLoadout,
    candidate: ItemCandidate,
    slot: SlotType,
    baseline: CharacterStatBaseline | None = None,
    weapon_set: WeaponSetContext | None = None,
    critical_gems: list[GemRequirement] | None = None,
) -> RequirementCascadeResult:
    proj = project_candidate_on_loadout(
        loadout=loadout,
        candidate=candidate,
        slot=slot,
        baseline=baseline,
        weapon_set=weapon_set,
    )

    cand_defs: list[RequirementDeficiency] = []
    loadout_defs: list[RequirementDeficiency] = []
    gem_defs: list[RequirementDeficiency] = []

    proj_str = proj.strength.projected_absolute if proj.strength.is_absolute_known else None
    proj_dex = proj.dexterity.projected_absolute if proj.dexterity.is_absolute_known else None
    proj_int = proj.intelligence.projected_absolute if proj.intelligence.is_absolute_known else None

    # Check candidate requirements
    if proj_str is not None and candidate.required_str > proj_str:
        cand_defs.append(RequirementDeficiency(
            target_type="candidate",
            target_name=candidate.name,
            slot=slot,
            attribute="str",
            required_value=candidate.required_str,
            projected_value=proj_str,
            shortfall=candidate.required_str - proj_str,
        ))
    if proj_dex is not None and candidate.required_dex > proj_dex:
        cand_defs.append(RequirementDeficiency(
            target_type="candidate",
            target_name=candidate.name,
            slot=slot,
            attribute="dex",
            required_value=candidate.required_dex,
            projected_value=proj_dex,
            shortfall=candidate.required_dex - proj_dex,
        ))
    if proj_int is not None and candidate.required_int > proj_int:
        cand_defs.append(RequirementDeficiency(
            target_type="candidate",
            target_name=candidate.name,
            slot=slot,
            attribute="int",
            required_value=candidate.required_int,
            projected_value=proj_int,
            shortfall=candidate.required_int - proj_int,
        ))

    # Check remaining equipped items across loadout
    # 1. Shared slots
    for sl in ALL_SHARED_SLOTS:
        if sl == slot:
            continue
        entry = loadout.get_slot(sl)
        if entry and entry.item:
            item = entry.item
            if proj_str is not None and item.required_str > proj_str:
                loadout_defs.append(RequirementDeficiency(
                    target_type="equipped_item",
                    target_name=item.name,
                    slot=sl,
                    attribute="str",
                    required_value=item.required_str,
                    projected_value=proj_str,
                    shortfall=item.required_str - proj_str,
                ))
            if proj_dex is not None and item.required_dex > proj_dex:
                loadout_defs.append(RequirementDeficiency(
                    target_type="equipped_item",
                    target_name=item.name,
                    slot=sl,
                    attribute="dex",
                    required_value=item.required_dex,
                    projected_value=proj_dex,
                    shortfall=item.required_dex - proj_dex,
                ))
            if proj_int is not None and item.required_int > proj_int:
                loadout_defs.append(RequirementDeficiency(
                    target_type="equipped_item",
                    target_name=item.name,
                    slot=sl,
                    attribute="int",
                    required_value=item.required_int,
                    projected_value=proj_int,
                    shortfall=item.required_int - proj_int,
                ))

    # 2. Weapon sets
    for w_name, w_dict in (("set_1", loadout.weapon_set_1), ("set_2", loadout.weapon_set_2)):
        current_wset = WeaponSetContext.WEAPON_SET_1 if w_name == "set_1" else WeaponSetContext.WEAPON_SET_2
        for w_slot in ALL_WEAPON_SLOTS:
            if weapon_set == current_wset and (
                candidate.slot_occupancy == SlotOccupancy.TWO_HAND or w_slot == slot
            ):
                continue
            entry = w_dict.get(w_slot.value)
            if entry and entry.item:
                item = entry.item
                if proj_str is not None and item.required_str > proj_str:
                    loadout_defs.append(RequirementDeficiency(
                        target_type="equipped_item",
                        target_name=item.name,
                        slot=w_slot,
                        attribute="str",
                        required_value=item.required_str,
                        projected_value=proj_str,
                        shortfall=item.required_str - proj_str,
                    ))
                if proj_dex is not None and item.required_dex > proj_dex:
                    loadout_defs.append(RequirementDeficiency(
                        target_type="equipped_item",
                        target_name=item.name,
                        slot=w_slot,
                        attribute="dex",
                        required_value=item.required_dex,
                        projected_value=proj_dex,
                        shortfall=item.required_dex - proj_dex,
                    ))
                if proj_int is not None and item.required_int > proj_int:
                    loadout_defs.append(RequirementDeficiency(
                        target_type="equipped_item",
                        target_name=item.name,
                        slot=w_slot,
                        attribute="int",
                        required_value=item.required_int,
                        projected_value=proj_int,
                        shortfall=item.required_int - proj_int,
                    ))

    # 3. Check critical gems
    if critical_gems:
        for gem in critical_gems:
            if proj_str is not None and gem.strength > proj_str:
                gem_defs.append(RequirementDeficiency(
                    target_type="gem",
                    target_name=gem.gem_name,
                    attribute="str",
                    required_value=gem.strength,
                    projected_value=proj_str,
                    shortfall=gem.strength - proj_str,
                ))
            if proj_dex is not None and gem.dexterity > proj_dex:
                gem_defs.append(RequirementDeficiency(
                    target_type="gem",
                    target_name=gem.gem_name,
                    attribute="dex",
                    required_value=gem.dexterity,
                    projected_value=proj_dex,
                    shortfall=gem.dexterity - proj_dex,
                ))
            if proj_int is not None and gem.intelligence > proj_int:
                gem_defs.append(RequirementDeficiency(
                    target_type="gem",
                    target_name=gem.gem_name,
                    attribute="int",
                    required_value=gem.intelligence,
                    projected_value=proj_int,
                    shortfall=gem.intelligence - proj_int,
                ))

    all_defs = cand_defs + loadout_defs + gem_defs
    is_satisfied = len(all_defs) == 0

    verdict_downgrade = None
    if not is_satisfied:
        if len(cand_defs) > 0:
            verdict_downgrade = "REJECT"
        else:
            verdict_downgrade = "CONDITIONAL_UPGRADE"

    return RequirementCascadeResult(
        is_satisfied=is_satisfied,
        candidate_deficiencies=cand_defs,
        loadout_cascading_deficiencies=loadout_defs,
        gem_cascading_deficiencies=gem_defs,
        verdict_downgrade=verdict_downgrade,
        summary=f"{len(all_defs)} requirement deficiencies detected." if not is_satisfied else "All requirements satisfied.",
    )


def generate_cascade_report(result: RequirementCascadeResult) -> str:
    if result.is_satisfied:
        return "All equipment and gem requirements are fully satisfied."

    lines = [
        "=== REQUIREMENT DEFICIENCY REPORT ===",
        f"Verdict Downgrade: {result.verdict_downgrade}",
    ]

    for d in result.candidate_deficiencies:
        lines.append(f"  [CANDIDATE] {d.target_name} requires {d.attribute.capitalize()}: {d.required_value} (Projected: {d.projected_value}, Shortfall: {d.shortfall})")

    for d in result.loadout_cascading_deficiencies:
        slot_str = f" in slot {d.slot.value.upper()}" if d.slot else ""
        lines.append(f"  [EQUIPPED ITEM{slot_str}] {d.target_name} requires {d.attribute.capitalize()}: {d.required_value} (Projected: {d.projected_value}, Shortfall: {d.shortfall})")

    for d in result.gem_cascading_deficiencies:
        lines.append(f"  [SOCKETED GEM] {d.target_name} requires {d.attribute.capitalize()}: {d.required_value} (Projected: {d.projected_value}, Shortfall: {d.shortfall})")

    return "\n".join(lines)
