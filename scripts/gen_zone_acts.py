"""Regenerate companion/equipment/data/zone_acts.json from PoB2's WorldAreas.

Output: {"zones": {zone name: act}, "act_min_level": {act: lowest area level}}.

Usage: uv run python scripts/gen_zone_acts.py [path/to/fork]
Default fork path: ../path-of-building-2-mcp/fork (sibling checkout).
Hideouts, maps and names shared by areas of different acts are left out (act unknown).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "companion" / "equipment" / "data" / "zone_acts.json"
_AREA_RE = re.compile(r'^worldAreas\["[^"]+"\] = \{(.*?)^\}', re.M | re.S)


def _field(body: str, name: str) -> str | None:
    m = re.search(rf"^\t{name} = (.+?),$", body, re.M)
    return m.group(1) if m else None


def collect(fork: Path) -> dict[str, dict]:
    text = (fork / "src" / "Data" / "WorldAreas.lua").read_text(encoding="utf-8")
    areas = _AREA_RE.findall(text)
    if len(areas) != text.count("worldAreas[\""):
        raise SystemExit(f"parsed {len(areas)} of {text.count('worldAreas[')} areas; format changed?")
    acts: dict[str, set[int]] = {}
    levels: dict[int, list[int]] = {}
    for body in areas:
        name, act, level = _field(body, "baseName"), _field(body, "act"), _field(body, "level")
        if not name or not act or _field(body, "isHideout") == "true" or _field(body, "isMap") == "true":
            continue
        acts.setdefault(json.loads(name), set()).add(int(act))
        if level:
            levels.setdefault(int(act), []).append(int(level))
    zones = {name: next(iter(a)) for name, a in acts.items() if len(a) == 1}
    # An act starts at its lowest area level above the previous act's start (towns are 0, odd areas lower).
    act_min_level, prev = {}, 0
    for act in sorted(levels):
        prev = act_min_level[str(act)] = min((lv for lv in levels[act] if lv > prev), default=prev)
    return {"zones": zones, "act_min_level": act_min_level}


def main() -> None:
    fork = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "path-of-building-2-mcp" / "fork"
    data = collect(fork)
    if not data["zones"]:
        raise SystemExit(f"no world areas found under {fork}")
    OUT.write_text(json.dumps(data, indent=0, sort_keys=True), encoding="utf-8", newline="\r\n")
    print(f"wrote {len(data['zones'])} zones, act levels {data['act_min_level']} to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
