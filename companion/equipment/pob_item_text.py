"""Convert PoB2's internal item text (Item.lua ``BuildRaw``, as returned by the engine's
``get_equipped`` and stored in PoB XML ``<Item>``) into in-game clipboard text that
``parse_item_text`` accepts."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from companion.equipment.api_adapter import ITEM_CLASS_PLURAL

SEP = "\n--------\n"
_PREFIX = re.compile(r"^(?:\{([^}]*)\})+")
_TAG = re.compile(r"\{([^}]*)\}")
_RANGE = re.compile(r"\((-?[\d.]+)-(-?[\d.]+)\)")
_SUFFIX = {"rune": " (rune)", "enchant": " (enchant)", "fractured": " (fractured)", "desecrated": " (desecrated)"}
_DEFENSES = {"Armour": "Armour", "Evasion": "Evasion Rating", "Energy Shield": "Energy Shield", "Ward": "Ward"}
# Header metadata lines BuildRaw can emit before "Implicits:" that this conversion ignores.
_META = re.compile(
    r"^(Unique ID|League|Unreleased|Crafted|Prefix|Suffix|Catalyst|CatalystQuality|Cluster Jewel [\w ]+|"
    r"Talisman Tier|Variant|Selected [\w ]*Variant[\w ]*|Has Alt Variant[\w ]*|Allow Duplicate Variants|"
    r"Charm Slots|Spirit|Sockets|Rune|Radius|Limited to|Requires Class)\b[: ]"
)


class PobItemTextError(ValueError):
    """The PoB item text could not be converted to clipboard text."""


@lru_cache(maxsize=1)
def _base_types() -> dict[str, str]:
    # Generated from the PoB fork's Data/Bases/*.lua (itemBases[name].type).
    return json.loads((Path(__file__).parent / "data" / "pob_base_types.json").read_text(encoding="utf-8"))


def _item_class(base: str) -> str:
    bases = _base_types()
    label = bases.get(base)
    if label is None:  # magic/normal names wrap the base: "Smouldering Iron Ring of the Starfish"
        hits = [b for b in bases if b in base]
        if not hits:
            raise PobItemTextError(f"unknown item base: {base!r}")
        label = bases[max(hits, key=len)]
    return ITEM_CLASS_PLURAL.get(label, label + "s")


def _num(x: float) -> str:
    return str(int(round(x))) if abs(x - round(x)) < 0.005 else f"{x:.2f}".rstrip("0").rstrip(".")


def _mod(line: str) -> tuple[str, str]:
    """Strip ``{...}`` prefixes; return (text with ranges resolved, clipboard annotation suffix)."""
    tags: list[str] = []
    m = _PREFIX.match(line)
    if m:
        tags = _TAG.findall(m.group(0))
        line = line[m.end():]
    rng = next((float(t[6:]) for t in tags if t.startswith("range:")), None)
    if rng is not None:
        line = _RANGE.sub(lambda r: _num(float(r[1]) + (float(r[2]) - float(r[1])) * rng), line)
    return line, next((_SUFFIX[t] for t in tags if t in _SUFFIX), "")


def pob_item_to_clipboard(raw: str) -> str:
    """Return in-game clipboard text for a PoB internal item text; raises PobItemTextError."""
    lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("Rarity:"):
        raise PobItemTextError("not PoB item text (missing leading 'Rarity:' line)")
    rarity = lines[0].split(":", 1)[1].strip().title()
    two_names = rarity in ("Rare", "Unique", "Relic")
    names = lines[1:3] if two_names else lines[1:2]
    if len(names) != (2 if two_names else 1):
        raise PobItemTextError("missing item name/base lines")
    base = names[-1]

    defenses: list[str] = []
    ilvl = quality = level = None
    implicits = None
    mods: list[str] = []
    for line in lines[1 + len(names):]:
        if implicits is not None:
            mods.append(line)
        elif (m := re.match(r"^Implicits:\s*(\d+)$", line)):
            implicits = int(m.group(1))
        elif (m := re.match(r"^(Armour|Evasion|Energy Shield|Ward):\s*(\d+)", line)):
            defenses.append(f"{_DEFENSES[m.group(1)]}: {m.group(2)}")
        elif (m := re.match(r"^Item Level:\s*(\d+)", line)):
            ilvl = m.group(1)
        elif (m := re.match(r"^Quality:\s*(\d+)", line)):
            quality = m.group(1) if int(m.group(1)) else None
        elif (m := re.match(r"^LevelReq:\s*(\d+)", line)):
            level = m.group(1)
        elif not _META.match(line):
            raise PobItemTextError(f"unrecognised header line: {line!r}")
    if implicits is None:
        raise PobItemTextError("missing 'Implicits:' line")

    status = [m for m in mods if m in ("Corrupted", "Twice Corrupted", "Mirrored", "Sanctified")]
    mods = [m for m in mods if m not in status]
    imp, exp = [], []
    for idx, line in enumerate(mods):
        text, suffix = _mod(line)
        if idx < implicits:
            imp.append(text + (suffix or " (implicit)"))
        else:
            exp.append(text + suffix)

    blocks = [[f"Item Class: {_item_class(base)}", f"Rarity: {rarity}", *names]]
    props = defenses + ([f"Quality: +{quality}%"] if quality else [])
    if props:
        blocks.append(props)
    if level:
        blocks.append(["Requirements:", f"Level: {level}"])
    if ilvl:
        blocks.append([f"Item Level: {ilvl}"])
    blocks += [b for b in (imp, exp, status) if b]
    return SEP.join("\n".join(b) for b in blocks) + "\n"
