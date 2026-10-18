"""Mobalytics guide JSON (poe2-companion-guide/1) -> GuideProfile."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError

from companion.builds.guide import (
    GemNote, GuideProfile, GuideStage, PassiveNotable, QuestReward, StageItem, weapon_classes_of,
)
from companion.builds.stages import assign_level_ranges
from companion.equipment.api_adapter import ITEM_CLASS_PLURAL

FORMAT = "poe2-companion-guide/1"

MOBA_SLOT_MAP: dict[str, str] = {
    "helmet": "Helmet", "body": "Body Armour", "gloves": "Gloves", "boots": "Boots",
    "amulet": "Amulet", "belt": "Belt", "leftRing": "Ring 1", "rightRing": "Ring 2",
    "mainHand.set1": "Weapon 1", "offHand.set1": "Weapon 2",
    "mainHand.set2": "Weapon 1 Swap", "offHand.set2": "Weapon 2 Swap",
}

ITEM_CLASS_SLUG_LABELS: dict[str, str] = {
    "amulet": "Amulet", "belt": "Belt", "body-armour": "Body Armour", "boots": "Boots",
    "crossbow": "Crossbow", "focus": "Focus", "gloves": "Gloves", "helmet": "Helmet",
    "ring": "Ring", "sceptre": "Sceptre", "staff": "Staff", "talisman": "Talisman",
    "wand": "Wand",
}

_PHYS = ("Minimum Physical Damage", "Maximum Physical Damage")


def _raw_text(slot: str, name: str, label: str, stats: list, mods: list[str]) -> str:
    d = {k: v for k, v in stats}
    lines = []
    if all(k in d for k in _PHYS):
        lines.append(f"Physical Damage: {d[_PHYS[0]]}-{d[_PHYS[1]]}")
    lines += [f"{k}: {v}" for k, v in stats if k not in _PHYS]
    plural = ITEM_CLASS_PLURAL.get(label, label)
    blocks = [f"Item Class: {plural}\nRarity: Rare\nGuide {slot}\n{name}"]
    if lines:
        blocks.append("\n".join(lines))
    if mods:
        blocks.append("\n".join(mods))
    return "\n--------\n".join(blocks)


def _http_url(url: object) -> str | None:
    """Only http(s) links are kept; the dashboard renders source_url as a link."""
    return url if isinstance(url, str) and url.lower().startswith(("https://", "http://")) else None


def _parse(data: dict) -> tuple[GuideProfile, str | None, list[str]]:
    if data.get("format") != FORMAT:
        raise ValueError(f"Format panduan tidak dikenal (harus {FORMAT}).")
    variants = data.get("variants") or []
    if not variants:
        raise ValueError("Panduan tidak memiliki varian.")
    warnings: list[str] = []
    stages: list[GuideStage] = []
    for v in variants:
        items: dict[str, StageItem] = {}
        for key, it in (v.get("items") or {}).items():
            if not it:
                continue
            slot = MOBA_SLOT_MAP.get(key)
            if slot is None:
                warnings.append(f"Slot tidak dikenal dilewati: {key}")
                continue
            if not it.get("name"):
                warnings.append(f"Item tanpa nama dilewati: {key}")
                continue
            slug = it.get("item_class") or ""
            label = ITEM_CLASS_SLUG_LABELS.get(slug)
            if label is None:
                label = slug.replace("-", " ").title()
                warnings.append(f"Kelas item tidak dikenal: {slug}")
            stats = [tuple(s) for s in it.get("stats") or []]
            mods = [m["text"] for m in it.get("mods") or [] if m.get("text")]
            unique = bool(it.get("is_unique"))
            items[slot] = StageItem(
                slot=slot, name=it["name"], item_class=label, is_unique=unique,
                base_stats={k: v for k, v in stats}, mods=mods,
                must_have=[m["text"] for m in it.get("mods") or [] if m.get("text") and m.get("must_have")],
                raw_text=None if unique else _raw_text(slot, it["name"], label, stats, mods),
            )
        skills = v.get("skills") or []
        stages.append(GuideStage(
            id=str(v["id"]), title=v.get("title") or str(v["id"]), items=items,
            main_skill=skills[0]["name"] if skills else None,
            weapon_classes=weapon_classes_of(items),
            notables=[PassiveNotable(name=str(n["name"]), kind=str(n.get("kind") or "NOTABLE"))
                      for n in v.get("notables") or [] if n.get("name")],
        ))
    pob = data.get("pob_code") or None
    profile = GuideProfile(
        slug=data["slug"], name=data["name"], source_url=_http_url(data.get("source_url")),
        imported_at=datetime.now(timezone.utc).isoformat(), stages=stages,
        has_pob=pob is not None, pob_stage_id=stages[-1].id,
        gem_notes=[GemNote(title=str(n.get("title") or ""), steps=[str(t) for t in n.get("steps") or []])
                   for n in data.get("gem_notes") or []],
        vendor_regex=data.get("vendor_regex") or None,
        quest_rewards=[QuestReward(act=str(q.get("act") or "Lainnya"), area=str(q.get("area") or ""),
                                   quest=str(q["quest"]), reward=str(q.get("reward") or ""))
                       for q in data.get("quest_rewards") or [] if q.get("quest")],
        tree_hints=[str(t) for t in data.get("tree_hints") or [] if t],
    )
    return profile, pob, warnings


def parse_mobalytics_guide(data: dict) -> tuple[GuideProfile, str | None, list[str]]:
    try:
        profile, pob, warnings = _parse(data)
    except ValidationError as exc:
        raise ValueError(f"Struktur guide tidak valid: {exc.errors()[0]['msg']}") from exc
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Struktur guide tidak valid: {type(exc).__name__} {exc}") from exc
    return assign_level_ranges(profile), pob, warnings
