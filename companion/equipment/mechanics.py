"""Material build mechanic registry and projection-safety evaluation model."""

from __future__ import annotations

import re
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.schema import (
    NormalizedModifier,
    NormalizedModifierType,
    SlotType,
)
from companion.state.provenance import VerificationState


class ProjectionSupport(str, Enum):
    """Level of projection support currently implemented for a build mechanic."""

    UNMODELED = "UNMODELED"
    PARTIALLY_MODELED = "PARTIALLY_MODELED"
    FULLY_MODELED = "FULLY_MODELED"


class MechanicImpactCertainty(str, Enum):
    """Certainty classification for equipment mechanic swaps."""

    MODELED_SAFE = "MODELED_SAFE"
    PRESERVED = "PRESERVED"
    UNMODELED_ADDED = "UNMODELED_ADDED"
    UNMODELED_REMOVED = "UNMODELED_REMOVED"
    UNMODELED_CHANGED = "UNMODELED_CHANGED"
    NO_MECHANIC_CHANGE = "NO_MECHANIC_CHANGE"
    UNKNOWN = "UNKNOWN"


class SpecialMechanicDefinition(BaseModel):
    """Metadata describing a recognized special / build mechanic."""

    model_config = ConfigDict(frozen=True)

    mechanic_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    verification: VerificationState = VerificationState.VERIFIED
    projection_support: ProjectionSupport = ProjectionSupport.UNMODELED
    description: str = ""


RE_UNSCALABLE_VALUE_STRIP = re.compile(r"\s*[—–-]\s*Unscalable Value\s*$", re.IGNORECASE)


def normalize_mechanic_key(raw_text: str) -> str:
    """Normalize a mechanic text or keystone name to a canonical snake_case key."""
    clean = RE_UNSCALABLE_VALUE_STRIP.sub("", raw_text.strip()).strip()
    clean = re.sub(r"[^\w\s-]", "", clean)
    clean = re.sub(r"[\s-]+", "_", clean).lower()
    return clean


KNOWN_SPECIAL_MECHANICS: dict[str, SpecialMechanicDefinition] = {
    "iron_reflexes": SpecialMechanicDefinition(
        mechanic_id="iron_reflexes",
        canonical_name="Iron Reflexes",
        aliases=["Iron Reflexes — Unscalable Value"],
        verification=VerificationState.VERIFIED,
        projection_support=ProjectionSupport.UNMODELED,
        description="Converts all Evasion Rating to Armour.",
    ),
    "chaos_inoculation": SpecialMechanicDefinition(
        mechanic_id="chaos_inoculation",
        canonical_name="Chaos Inoculation",
        aliases=["Chaos Inoculation — Unscalable Value"],
        verification=VerificationState.VERIFIED,
        projection_support=ProjectionSupport.UNMODELED,
        description="Maximum Life becomes 1, immune to Chaos Damage.",
    ),
    "resolute_technique": SpecialMechanicDefinition(
        mechanic_id="resolute_technique",
        canonical_name="Resolute Technique",
        aliases=["Resolute Technique — Unscalable Value"],
        verification=VerificationState.VERIFIED,
        projection_support=ProjectionSupport.UNMODELED,
        description="Your hits cannot be Evaded, never deal Critical Strikes.",
    ),
    "avatar_of_fire": SpecialMechanicDefinition(
        mechanic_id="avatar_of_fire",
        canonical_name="Avatar of Fire",
        aliases=["Avatar of Fire — Unscalable Value"],
        verification=VerificationState.VERIFIED,
        projection_support=ProjectionSupport.UNMODELED,
        description="50% of Physical, Cold and Lightning Damage Converted to Fire Damage. Deal no Non-Fire Damage.",
    ),
    "eldritch_battery": SpecialMechanicDefinition(
        mechanic_id="eldritch_battery",
        canonical_name="Eldritch Battery",
        aliases=["Eldritch Battery — Unscalable Value"],
        verification=VerificationState.VERIFIED,
        projection_support=ProjectionSupport.UNMODELED,
        description="Energy Shield protects Mana instead of Life.",
    ),
    "blood_magic": SpecialMechanicDefinition(
        mechanic_id="blood_magic",
        canonical_name="Blood Magic",
        aliases=["Blood Magic — Unscalable Value"],
        verification=VerificationState.VERIFIED,
        projection_support=ProjectionSupport.UNMODELED,
        description="Removes all Mana. Spend Life instead of Mana for Skills.",
    ),
    "acrobatics": SpecialMechanicDefinition(
        mechanic_id="acrobatics",
        canonical_name="Acrobatics",
        aliases=["Acrobatics — Unscalable Value"],
        verification=VerificationState.VERIFIED,
        projection_support=ProjectionSupport.UNMODELED,
        description="Converts Spell Suppression Chance to Spell Dodge Chance.",
    ),
    "arrow_dancing": SpecialMechanicDefinition(
        mechanic_id="arrow_dancing",
        canonical_name="Arrow Dancing",
        aliases=["Arrow Dancing — Unscalable Value"],
        verification=VerificationState.VERIFIED,
        projection_support=ProjectionSupport.UNMODELED,
        description="Doubles Evasion Rating against Projectile Attacks, less Evasion against Melee.",
    ),
    "ghost_dance": SpecialMechanicDefinition(
        mechanic_id="ghost_dance",
        canonical_name="Ghost Dance",
        aliases=["Ghost Dance — Unscalable Value"],
        verification=VerificationState.VERIFIED,
        projection_support=ProjectionSupport.UNMODELED,
        description="Gain Ghost Shrouds periodically; recover Energy Shield on hit.",
    ),
    "wind_dancer": SpecialMechanicDefinition(
        mechanic_id="wind_dancer",
        canonical_name="Wind Dancer",
        aliases=["Wind Dancer — Unscalable Value"],
        verification=VerificationState.VERIFIED,
        projection_support=ProjectionSupport.UNMODELED,
        description="Less damage taken if you haven't been hit recently.",
    ),
}


def lookup_special_mechanic(text_or_mod: str | NormalizedModifier) -> SpecialMechanicDefinition:
    """Look up a special mechanic definition from raw text or a NormalizedModifier."""
    if isinstance(text_or_mod, NormalizedModifier):
        key = getattr(text_or_mod, "mechanic_id", None) or normalize_mechanic_key(text_or_mod.raw_text)
        raw_text = text_or_mod.raw_text
    else:
        key = normalize_mechanic_key(text_or_mod)
        raw_text = text_or_mod

    if key in KNOWN_SPECIAL_MECHANICS:
        return KNOWN_SPECIAL_MECHANICS[key]

    clean_name = RE_UNSCALABLE_VALUE_STRIP.sub("", raw_text.strip()).strip()
    return SpecialMechanicDefinition(
        mechanic_id=key,
        canonical_name=clean_name,
        aliases=[raw_text] if raw_text != clean_name else [],
        verification=VerificationState.UNKNOWN,
        projection_support=ProjectionSupport.UNMODELED,
        description="Unregistered special mechanic.",
    )


class MechanicSafetyAssessment(BaseModel):
    """Detailed safety evaluation of mechanic delta across item replacement."""

    model_config = ConfigDict(frozen=True)

    certainty: MechanicImpactCertainty
    displaced_mechanics: list[NormalizedModifier] = Field(default_factory=list)
    candidate_mechanics: list[NormalizedModifier] = Field(default_factory=list)
    removed_mechanics: list[NormalizedModifier] = Field(default_factory=list)
    added_mechanics: list[NormalizedModifier] = Field(default_factory=list)
    preserved_mechanics: list[NormalizedModifier] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    is_safe_for_equip: bool = True


def evaluate_mechanic_safety(
    displaced_modifiers: list[NormalizedModifier],
    candidate_modifiers: list[NormalizedModifier],
    slot: SlotType | None = None,
) -> MechanicSafetyAssessment:
    """Evaluates whether item replacement safely preserves or models all material build mechanics."""
    # Filter to build mechanics / special mechanics
    disp_mechs = [
        m for m in displaced_modifiers
        if m.modifier_type == NormalizedModifierType.SPECIAL_MECHANIC
        or m.scope.value == "BUILD_MECHANIC"
    ]
    cand_mechs = [
        m for m in candidate_modifiers
        if m.modifier_type == NormalizedModifierType.SPECIAL_MECHANIC
        or m.scope.value == "BUILD_MECHANIC"
    ]

    disp_by_id: dict[str, NormalizedModifier] = {}
    for m in disp_mechs:
        k = getattr(m, "mechanic_id", None) or normalize_mechanic_key(m.raw_text)
        disp_by_id[k] = m

    cand_by_id: dict[str, NormalizedModifier] = {}
    for m in cand_mechs:
        k = getattr(m, "mechanic_id", None) or normalize_mechanic_key(m.raw_text)
        cand_by_id[k] = m

    removed: list[NormalizedModifier] = [
        m for k, m in disp_by_id.items() if k not in cand_by_id
    ]
    added: list[NormalizedModifier] = [
        m for k, m in cand_by_id.items() if k not in disp_by_id
    ]
    preserved: list[NormalizedModifier] = [
        m for k, m in disp_by_id.items() if k in cand_by_id
    ]

    slot_label = slot.value if slot else "item"

    # Identify unmodeled removed / added
    unmodeled_removed: list[tuple[NormalizedModifier, SpecialMechanicDefinition]] = []
    for m in removed:
        defn = lookup_special_mechanic(m)
        if defn.projection_support == ProjectionSupport.UNMODELED:
            unmodeled_removed.append((m, defn))

    unmodeled_added: list[tuple[NormalizedModifier, SpecialMechanicDefinition]] = []
    for m in added:
        defn = lookup_special_mechanic(m)
        if defn.projection_support == ProjectionSupport.UNMODELED:
            unmodeled_added.append((m, defn))

    reasons: list[str] = []
    uncertainties: list[str] = []

    for m, defn in unmodeled_removed:
        msg = (
            f"Current {slot_label} grant {defn.canonical_name}. The defensive impact of losing this "
            "mechanic is not safely modeled, so this swap cannot be recommended with high confidence."
        )
        reasons.append(msg)
        uncertainties.append(msg)

    for m, defn in unmodeled_added:
        msg = (
            f"Candidate {slot_label} grant unmodeled special mechanic {defn.canonical_name}; "
            "character impact is not safely modeled."
        )
        reasons.append(msg)
        uncertainties.append(msg)

    if unmodeled_removed and unmodeled_added:
        certainty = MechanicImpactCertainty.UNMODELED_CHANGED
        is_safe = False
    elif unmodeled_removed:
        certainty = MechanicImpactCertainty.UNMODELED_REMOVED
        is_safe = False
    elif unmodeled_added:
        certainty = MechanicImpactCertainty.UNMODELED_ADDED
        is_safe = False
    elif preserved and not removed and not added:
        certainty = MechanicImpactCertainty.PRESERVED
        is_safe = True
    elif not disp_mechs and not cand_mechs:
        certainty = MechanicImpactCertainty.NO_MECHANIC_CHANGE
        is_safe = True
    else:
        certainty = MechanicImpactCertainty.MODELED_SAFE
        is_safe = True

    return MechanicSafetyAssessment(
        certainty=certainty,
        displaced_mechanics=disp_mechs,
        candidate_mechanics=cand_mechs,
        removed_mechanics=removed,
        added_mechanics=added,
        preserved_mechanics=preserved,
        reasons=reasons,
        uncertainties=uncertainties,
        is_safe_for_equip=is_safe,
    )
