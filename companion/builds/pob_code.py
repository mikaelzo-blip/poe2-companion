"""Import a guide from a PoB2 share code or a pobb.in link."""

from __future__ import annotations

import base64
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from datetime import datetime, timezone

from pydantic import ValidationError

from companion.builds.guide import GuideProfile, GuideStage, StageItem, singular_item_class, weapon_classes_of
from companion.builds.stages import assign_level_ranges
from companion.equipment.parser import parse_item_text
from companion.equipment.pob_item_text import PobItemTextError, pob_item_to_clipboard

log = logging.getLogger(__name__)

_SLOTS = {
    "Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap", "Helmet", "Body Armour",
    "Gloves", "Boots", "Amulet", "Ring 1", "Ring 2", "Belt",
}
_POBB = re.compile(r"^https://pobb\.in/([A-Za-z0-9_-]+)(?:/raw)?/?$")


def decode_share_code(code: str) -> str:
    try:
        s = "".join(code.split())
        s += "=" * (-len(s) % 4)
        d = zlib.decompressobj()
        out = d.decompress(base64.urlsafe_b64decode(s), 20_000_000)
        if d.unconsumed_tail:
            raise ValueError("too large")
        return out.decode("utf-8")
    except Exception as exc:
        raise ValueError("Kode PoB2 tidak valid") from exc


def active_item_set_title(xml: str) -> str | None:
    try:
        root = ET.fromstring(xml)
    except (ET.ParseError, ValueError, TypeError):
        return None
    items = root if root.tag == "Items" else root.find("Items")
    if items is None:
        return None
    active_id = items.get("activeItemSet")
    if not active_id:
        return None
    for s in items.findall("ItemSet"):
        if s.get("id") == active_id:
            return s.get("title")
    return None


def fetch_pobb_code(url: str, opener=urllib.request.urlopen) -> str:
    m = _POBB.match(url.strip())
    if not m:
        raise ValueError("URL harus berbentuk https://pobb.in/<id>")
    with opener(f"https://pobb.in/{m[1]}/raw", timeout=15) as resp:
        return resp.read(5_000_000).decode("utf-8").strip()


def _item(slot: str, pob_text: str, warnings: list[str]) -> StageItem:
    text = pob_text.strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    fallback = StageItem(slot=slot, name=lines[1] if len(lines) > 1 else slot,
                         item_class="", raw_text=None)
    try:
        clip = pob_item_to_clipboard(text)
        cand = parse_item_text(clip)
    except ValueError as exc:  # PobItemTextError is a ValueError
        log.warning("Item PoB di slot %s tidak bisa dikonversi: %s", slot, exc)
        warnings.append(f"Item PoB di slot {slot} tidak bisa dikonversi: {exc}")
        return fallback
    klass = singular_item_class(
        next((ln[12:].strip() for ln in clip.splitlines() if ln.startswith("Item Class:")), ""))
    unique = cand.rarity.lower() == "unique"
    return StageItem(slot=slot, name=cand.name if unique else cand.base_type, item_class=klass,
                     is_unique=unique, mods=[m.raw_text for m in cand.modifiers], raw_text=clip)


def _main_skill(root: ET.Element, title: str, index: int) -> str | None:
    build, skills = root.find("Build"), root.find("Skills")
    if build is None or skills is None:
        return None
    sets = skills.findall("SkillSet")
    container = skills
    if sets:
        container = next((s for s in sets if s.get("title") == title), None)
        if container is None:
            container = sets[index] if index < len(sets) else sets[0] if len(sets) == 1 else None
        # mainSocketGroup indexes the active SkillSet only; other sets carry no main-skill marker.
        if container is None or (len(sets) > 1 and container.get("id") != skills.get("activeSkillSet")):
            return None
    try:
        idx = int(build.get("mainSocketGroup", "1")) - 1
        gem = container.findall("Skill")[idx].find("Gem")
    except (ValueError, IndexError):
        return None
    return gem.get("nameSpec") if gem is not None else None


def _parse_pob_xml(xml: str, name: str, warnings: list[str]) -> GuideProfile:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("XML PoB2 tidak valid") from exc
    items_el = root.find("Items")
    if items_el is None:
        raise ValueError("XML PoB2 tidak memiliki item")
    texts = {i.get("id"): (i.text or "") for i in items_el.findall("Item")}
    stages = []
    for n, s in enumerate(items_el.findall("ItemSet")):
        sid = s.get("id", "")
        items = {}
        for sl in s.findall("Slot"):
            slot, text = sl.get("name"), texts.get(sl.get("itemId"), "").strip()
            if slot in _SLOTS and text:
                items[slot] = _item(slot, text, warnings)
        stages.append(GuideStage(id=sid, title=s.get("title") or f"Set {sid}", items=items, main_skill=_main_skill(root, s.get("title") or "", n),
                                  weapon_classes=weapon_classes_of(items)))
    profile = GuideProfile(
        slug=re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "pob",
        name=name, imported_at=datetime.now(timezone.utc).isoformat(), stages=stages,
        has_pob=True, pob_stage_id=items_el.get("activeItemSet"),
    )
    return profile


def parse_pob_xml(xml: str, name: str, warnings: list[str] | None = None) -> GuideProfile:
    if warnings is None:
        warnings = []
    try:
        profile = _parse_pob_xml(xml, name, warnings)
    except ValidationError as exc:
        raise ValueError(f"XML PoB2 tidak valid: {exc.errors()[0]['msg']}") from exc
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"XML PoB2 tidak valid: {type(exc).__name__} {exc}") from exc
    return assign_level_ranges(profile)
