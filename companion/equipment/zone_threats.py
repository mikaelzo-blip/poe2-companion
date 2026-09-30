"""PoE2 Zone and Encounter Threat Matrix.

Maps game zone identifiers (e.g. 'G2_1', 'The Crypt') to environmental threats,
lethal boss mechanics, and tactical survival baselines.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ZoneThreatProfile(BaseModel):
    """Encapsulates the survival and threat profile of a specific zone/encounter."""

    zone_id: str
    friendly_name: str
    act: int
    lethal_damage_types: list[str] = Field(default_factory=list)
    recommended_res: dict[str, int] = Field(default_factory=dict)
    upcoming_boss: str = ""
    survival_notes: str = ""

    def is_resistance_drop_dangerous(
        self,
        fire_delta: int = 0,
        cold_delta: int = 0,
        lightning_delta: int = 0,
        chaos_delta: int = 0,
    ) -> tuple[bool, str]:
        """Determine if a proposed resistance change drops a lethal zone resistance."""
        threat_lowers = [t.lower() for t in self.lethal_damage_types]
        warnings: list[str] = []

        if "fire" in threat_lowers and fire_delta <= -5:
            warnings.append(
                f"Penurunan Fire Resistance ({fire_delta}%) sangat berbahaya di {self.friendly_name} "
                f"karena ancaman proyektil/serangan api tinggi."
            )
        if "cold" in threat_lowers and cold_delta <= -5:
            warnings.append(
                f"Penurunan Cold Resistance ({cold_delta}%) berbahaya di {self.friendly_name} "
                f"karena freeze/chill dan cold hit mematikan."
            )
        if "lightning" in threat_lowers and lightning_delta <= -5:
            warnings.append(
                f"Penurunan Lightning Resistance ({lightning_delta}%) berbahaya di {self.friendly_name} "
                f"karena burst shock & lightning spikes."
            )
        if "chaos" in threat_lowers and chaos_delta <= -5:
            warnings.append(
                f"Penurunan Chaos Resistance ({chaos_delta}%) berbahaya di {self.friendly_name}."
            )

        if warnings:
            return True, " ".join(warnings)
        return False, ""


# Verified PoE2 Zone and Area Threat Catalog
ZONE_CATALOG: dict[str, dict[str, Any]] = {
    # Act 1 Zones
    "G1_1": {
        "friendly_name": "The Riverbank (Act 1)",
        "act": 1,
        "lethal_damage_types": ["Physical", "Cold"],
        "recommended_res": {"cold": 15, "fire": 10, "lightning": 10},
        "upcoming_boss": "Gallows / Riverbank Beasts",
        "survival_notes": "Awal campaign: Physical hit dominan, sedikit Cold damage.",
    },
    "G1_11": {
        "friendly_name": "Clear Fell / The Crypt (Act 1)",
        "act": 1,
        "lethal_damage_types": ["Physical", "Cold"],
        "recommended_res": {"cold": 25, "lightning": 15, "fire": 15},
        "upcoming_boss": "The Executioner / Devourer",
        "survival_notes": "Crypt didominasi Physical stun dan Cold spells mayat hidup.",
    },
    "clear fell": {
        "friendly_name": "Clear Fell (Act 1)",
        "act": 1,
        "lethal_damage_types": ["Physical", "Cold"],
        "recommended_res": {"cold": 20, "fire": 15, "lightning": 15},
        "upcoming_boss": "The Clear Fell Horrors",
        "survival_notes": "Hutan berkabut: waspadai sergapan fisik dan burst dingin.",
    },
    "the crypt": {
        "friendly_name": "The Crypt (Act 1)",
        "act": 1,
        "lethal_damage_types": ["Physical", "Cold"],
        "recommended_res": {"cold": 25, "fire": 15, "lightning": 15},
        "upcoming_boss": "The Executioner",
        "survival_notes": "Sarang undead: Cold damage dan Physical smash tinggi.",
    },
    "omen ridge": {
        "friendly_name": "Omen Ridge (Act 1)",
        "act": 1,
        "lethal_damage_types": ["Lightning", "Physical"],
        "recommended_res": {"lightning": 25, "fire": 15, "cold": 15},
        "upcoming_boss": "Storm Harpy / Ridge Alpha",
        "survival_notes": "Tebing berbadai: sambaran Lightning dan sergapan udara.",
    },
    # Act 2 Zones (Vastiri Desert & Surroundings)
    "G2_1": {
        "friendly_name": "Vastiri Outskirts / Caravan (Act 2)",
        "act": 2,
        "lethal_damage_types": ["Fire", "Physical"],
        "recommended_res": {"fire": 35, "lightning": 25, "cold": 20},
        "upcoming_boss": "The Dreadnought / Jamanra / Vastiri Bandits",
        "survival_notes": "Padang pasir Vastiri dipenuhi bandit api, proyektil beruntun, dan rolling boulder fisik. Kehilangan Fire Resistance sangat mematikan di sini.",
    },
    "vastiri outskirts": {
        "friendly_name": "Vastiri Outskirts (Act 2)",
        "act": 2,
        "lethal_damage_types": ["Fire", "Physical"],
        "recommended_res": {"fire": 35, "lightning": 25, "cold": 20},
        "upcoming_boss": "The Dreadnought / Vastiri Trappers",
        "survival_notes": "Waspadai panah api beruntun dan rolling boulder pasir.",
    },
    "G2_2": {
        "friendly_name": "The Traitor's Passage (Act 2)",
        "act": 2,
        "lethal_damage_types": ["Fire", "Physical", "Lightning"],
        "recommended_res": {"fire": 40, "lightning": 30, "cold": 20},
        "upcoming_boss": "Vastiri Ambushers",
        "survival_notes": "Lorong sempit: rentan burst api terkonsentrasi.",
    },
    "G2_5": {
        "friendly_name": "The Dreadnought Approach (Act 2)",
        "act": 2,
        "lethal_damage_types": ["Fire", "Physical"],
        "recommended_res": {"fire": 45, "lightning": 30, "cold": 20},
        "upcoming_boss": "The Dreadnought Core Engine",
        "survival_notes": "Area mesin Dreadnought: semburan api uap dan mortar raksasa.",
    },
}


class ZoneThreatMatrix:
    """Registry and query resolver for zone threats."""

    def __init__(self, catalog: dict[str, dict[str, Any]] | None = None) -> None:
        self._catalog = catalog or ZONE_CATALOG

    def get_profile(
        self,
        zone_id: str | None,
        character_level: int | None = None,
    ) -> ZoneThreatProfile:
        """Resolve a ZoneThreatProfile from zone id or name, with fallback to level/act heuristic."""
        if zone_id:
            clean_id = zone_id.strip()
            # Direct match (case-sensitive or lowercase)
            if clean_id in self._catalog:
                data = self._catalog[clean_id]
                return ZoneThreatProfile(zone_id=clean_id, **data)
            clean_lower = clean_id.lower()
            if clean_lower in self._catalog:
                data = self._catalog[clean_lower]
                return ZoneThreatProfile(zone_id=clean_id, **data)

            # Prefix matches e.g. G2_* -> Act 2, G1_* -> Act 1
            if clean_id.upper().startswith("G2_") or clean_id.upper().startswith("G2"):
                return ZoneThreatProfile(
                    zone_id=clean_id,
                    friendly_name=f"Vastiri Desert Area {clean_id} (Act 2)",
                    act=2,
                    lethal_damage_types=["Fire", "Physical"],
                    recommended_res={"fire": 35, "lightning": 25, "cold": 20},
                    upcoming_boss="Act 2 Bosses / The Dreadnought",
                    survival_notes="Act 2 Vastiri: ancaman api dan proyektil fisik tinggi.",
                )
            if clean_id.upper().startswith("G1_") or clean_id.upper().startswith("G1"):
                return ZoneThreatProfile(
                    zone_id=clean_id,
                    friendly_name=f"Ogham Lands {clean_id} (Act 1)",
                    act=1,
                    lethal_damage_types=["Physical", "Cold"],
                    recommended_res={"cold": 20, "fire": 15, "lightning": 15},
                    upcoming_boss="Act 1 Encounters",
                    survival_notes="Act 1: ancaman serangan fisik dan dingin.",
                )

        # Fallback heuristic based on character level
        lvl = character_level or 1
        if lvl < 15:
            return ZoneThreatProfile(
                zone_id=zone_id or "Act1_General",
                friendly_name="Act 1 Campaign Area",
                act=1,
                lethal_damage_types=["Physical", "Cold"],
                recommended_res={"cold": 20, "lightning": 15, "fire": 15},
                upcoming_boss="Act 1 Progression Bosses",
                survival_notes="Level 1-14: prioritaskan kestabilan Life dasar dan mitigasi fisik.",
            )
        elif lvl < 33:
            return ZoneThreatProfile(
                zone_id=zone_id or "Act2_General",
                friendly_name="Act 2 Vastiri Desert Area",
                act=2,
                lethal_damage_types=["Fire", "Physical"],
                recommended_res={"fire": 35, "lightning": 25, "cold": 20},
                upcoming_boss="Act 2 Encounters (The Dreadnought / Jamanra)",
                survival_notes="Level 15-32 (Act 2): Fire Resistance sangat esensial menghindari one-shot dari proyektil dan burst api.",
            )
        elif lvl < 52:
            return ZoneThreatProfile(
                zone_id=zone_id or "Act3_General",
                friendly_name="Act 3 Campaign Area",
                act=3,
                lethal_damage_types=["Lightning", "Chaos", "Physical"],
                recommended_res={"lightning": 50, "fire": 45, "cold": 40},
                upcoming_boss="Act 3 Guardians",
                survival_notes="Level 33-51: ancaman Lightning burst dan Chaos damage mulai muncul.",
            )
        else:
            return ZoneThreatProfile(
                zone_id=zone_id or "Late_Campaign",
                friendly_name="Late Campaign / Endgame",
                act=4,
                lethal_damage_types=["Fire", "Cold", "Lightning", "Chaos"],
                recommended_res={"fire": 75, "cold": 75, "lightning": 75},
                upcoming_boss="Endgame Bosses",
                survival_notes="Semua elemental resistance wajib mencapai cap 75%.",
            )


_GLOBAL_ZONE_MATRIX = ZoneThreatMatrix()


def get_zone_threat_profile(
    zone_id: str | None,
    character_level: int | None = None,
) -> ZoneThreatProfile:
    """Convenience accessor for global zone threat matrix."""
    return _GLOBAL_ZONE_MATRIX.get_profile(zone_id, character_level=character_level)
