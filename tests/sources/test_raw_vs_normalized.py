"""Unit tests for raw vs normalized build models."""

import pytest
from companion.sources.interval import IntervalKind
from companion.sources.models_normalized import (
    WeaponSetContext,
    is_cast_on_dodge_id,
    map_weapon_set_context,
    normalize_build,
)
from companion.sources.models_raw import (
    RawBuild,
    RawInventorySlot,
    RawPassiveEntry,
    RawSkillEntry,
    RawSupportSkill,
)


def test_raw_models_preserve_extra_fields() -> None:
    raw_data = {
        "name": "Test Build",
        "author": "Fubgun",
        "custom_top_level_field": "preserved_value",
        "passives": [
            {"id": "node_1", "extra_passive_attr": 42},
        ],
        "skills": [
            {
                "id": "skill_1",
                "extra_skill_attr": True,
                "support_skills": [
                    {"id": "sup_1", "extra_sup_attr": "ok"}
                ],
            }
        ],
        "inventory_slots": [
            {
                "inventory_id": "Boots",
                "slot_x": 0,
                "slot_y": 0,
                "extra_gear_attr": {"tier": 1},
                "additional_text": "Movement speed 30%",
            }
        ],
    }

    raw = RawBuild.model_validate(raw_data)
    assert raw.name == "Test Build"
    assert raw.model_extra["custom_top_level_field"] == "preserved_value"
    assert raw.passives[0].model_extra["extra_passive_attr"] == 42
    assert raw.skills[0].model_extra["extra_skill_attr"] is True
    assert raw.skills[0].support_skills[0].model_extra["extra_sup_attr"] == "ok"
    assert raw.inventory_slots[0].model_extra["extra_gear_attr"] == {"tier": 1}
    assert raw.inventory_slots[0].additional_text == "Movement speed 30%"


def test_weapon_set_context_mapping() -> None:
    ctx, warn = map_weapon_set_context(None)
    assert ctx == WeaponSetContext.DEFAULT_OR_SHARED
    assert warn is None

    ctx, warn = map_weapon_set_context(1)
    assert ctx == WeaponSetContext.SPECIALISATION_1
    assert warn is None

    ctx, warn = map_weapon_set_context(2)
    assert ctx == WeaponSetContext.SPECIALISATION_2
    assert warn is None

    ctx, warn = map_weapon_set_context(0)
    assert ctx == WeaponSetContext.UNKNOWN_RESERVED
    assert warn is not None

    ctx, warn = map_weapon_set_context(99)
    assert ctx == WeaponSetContext.OTHER
    assert warn is not None


def test_passive_deduplication_preserves_weapon_set_contexts() -> None:
    """Same passive_id in different weapon sets must NOT be collapsed."""
    raw = RawBuild(
        name="Weapon Set Test",
        passives=[
            RawPassiveEntry(id="passive_A", weapon_set=1),
            RawPassiveEntry(id="passive_A", weapon_set=2),
            RawPassiveEntry(id="passive_A", weapon_set=1),  # Duplicate within weapon set 1
            RawPassiveEntry(id="passive_B", weapon_set=None),
        ],
    )

    norm = normalize_build(raw, logical_stage="lvl 52 Swap")
    assert len(norm.passives) == 3

    p_a_ws1 = [p for p in norm.passives if p.passive_id == "passive_A" and p.weapon_set_context == WeaponSetContext.SPECIALISATION_1][0]
    p_a_ws2 = [p for p in norm.passives if p.passive_id == "passive_A" and p.weapon_set_context == WeaponSetContext.SPECIALISATION_2][0]
    p_b = [p for p in norm.passives if p.passive_id == "passive_B"][0]

    assert p_a_ws1.occurrences == 2
    assert p_a_ws1.original_indices == [0, 2]

    assert p_a_ws2.occurrences == 1
    assert p_a_ws2.original_indices == [1]

    assert p_b.weapon_set_context == WeaponSetContext.DEFAULT_OR_SHARED
    assert p_b.occurrences == 1
    assert p_b.original_indices == [3]


def test_cast_on_dodge_detection() -> None:
    assert is_cast_on_dodge_id("Cast on Dodge")
    assert is_cast_on_dodge_id("cast_on_dodge")
    assert is_cast_on_dodge_id("CAST ON DODGE ")
    assert not is_cast_on_dodge_id("Flameblast")

    raw = RawBuild(
        name="Meta Gem Test",
        skills=[
            RawSkillEntry(
                id="Cast on Dodge",
                level_interval=[58, 100],
                support_skills=[
                    RawSupportSkill(id="Cast on Dodge", level_interval=None),
                    RawSupportSkill(id="Faster Casting", level_interval=[1, 14]),
                ],
            )
        ],
    )

    norm = normalize_build(raw, logical_stage="Endgame")
    assert norm.skills[0].is_cast_on_dodge is True
    assert norm.skills[0].support_skills[0].is_cast_on_dodge is True
    assert norm.skills[0].support_skills[1].is_cast_on_dodge is False
    assert norm.skills[0].level_interval.kind == IntervalKind.RANGE
    assert norm.skills[0].support_skills[0].level_interval.kind == IntervalKind.UNRESTRICTED
