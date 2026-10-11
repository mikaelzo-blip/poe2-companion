"""Default breaker rules shipped for known guides, keyed by mobalytics slug."""
from __future__ import annotations

from companion.builds.guide import BreakerRule

KNOWN_RULES: dict[str, list[BreakerRule]] = {
    "fubgun-flameblast-oil-grenade": [
        BreakerRule(
            pattern=r"adds .*fire damage to attacks|gain .*as extra fire damage",
            from_level=52,
            exclude_slots=["Weapon 1", "Weapon 2"],
            reason="Fire damage ke Attack menyalakan Oil Grenade terlalu cepat (Fubgun, lvl 52+)",
        )
    ],
}


def default_rules_for(source_url: str | None) -> list[BreakerRule]:
    if not source_url:
        return []
    return list(KNOWN_RULES.get(source_url.rstrip("/").rsplit("/", 1)[-1], []))
