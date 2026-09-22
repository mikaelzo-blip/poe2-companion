"""Deterministic mock adapter for offline and test-driven official API contracts."""

from __future__ import annotations

from companion.api.schema import OfficialCharacterData, OfficialItem, OfficialQuestStats


def create_mock_character(
    character_id: str = "char_mock_1",
    level: int = 70,
    game_version: str = "0.1.0",
    tree_revision: str = "tree-1",
) -> OfficialCharacterData:
    """Generate a reproducible official character data fixture."""
    items = [
        OfficialItem(
            slot="helmet",
            name="Iron Mask",
            type_line="Iron Mask",
            rarity="Rare",
            ilvl=level - 5,
            requirements={"level": level - 10, "int": 60},
            explicit_mods=["+45 to Maximum Life", "+25% to Fire Resistance"],
            sockets=2,
        ),
        OfficialItem(
            slot="boots",
            name="Titan Greaves",
            type_line="Titan Greaves",
            rarity="Rare",
            ilvl=level - 2,
            requirements={"level": level - 5, "str": 70},
            explicit_mods=["+50 to Maximum Life", "+30% to Cold Resistance", "+20% Movement Speed"],
            sockets=2,
        ),
        OfficialItem(
            slot="weapon",
            name="Reaver Axe",
            type_line="Reaver Axe",
            rarity="Rare",
            ilvl=level,
            requirements={"level": level, "str": 85},
            explicit_mods=["120% Increased Physical Damage", "+15 to 28 Physical Damage"],
            sockets=3,
        ),
    ]

    passives = [
        "node_life_1",
        "node_life_2",
        "node_resists_1",
        "node_axe_dmg_1",
        "node_axe_dmg_2",
        "node_str_1",
        "node_spirit_1",
    ]

    quests = OfficialQuestStats(
        permanent_passives=3,
        bandit_choice="Alira",
        spirit_capacity=100,
    )

    return OfficialCharacterData(
        character_id=character_id,
        name=f"Exile_{character_id}",
        class_name="Mercenary",
        level=level,
        league="Standard",
        game_version=game_version,
        passive_tree_revision=tree_revision,
        passives=passives,
        equipment=items,
        quest_stats=quests,
    )
