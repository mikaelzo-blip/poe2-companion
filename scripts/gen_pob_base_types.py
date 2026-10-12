"""Regenerate companion/equipment/data/pob_base_types.json from PoB2's itemBases.

Usage: uv run python scripts/gen_pob_base_types.py [path/to/fork]
Default fork path: ../path-of-building-2-mcp/fork (sibling checkout).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "companion" / "equipment" / "data" / "pob_base_types.json"
# itemBases["Name"] = { ... type = "Item Type", ... } -- type is the first field PoB writes
_BASE_RE = re.compile(r'^itemBases\["((?:[^"\\]|\\.)*)"\]\s*=\s*\{\s*type\s*=\s*"([^"]+)"', re.M)


def collect(fork: Path) -> dict[str, str]:
    bases: dict[str, str] = {}
    for lua in sorted((fork / "src" / "Data" / "Bases").glob("*.lua")):
        text = lua.read_text(encoding="utf-8")
        found = _BASE_RE.findall(text)
        if len(found) != text.count("itemBases["):
            raise SystemExit(f"{lua.name}: parsed {len(found)} of {text.count('itemBases[')} bases; format changed?")
        for name, typ in found:
            name = name.replace('\\"', '"')
            # PoB repeats some hidden bases (same name, later wins in Lua); only a type clash is suspicious
            if bases.get(name, typ) != typ:
                raise SystemExit(f"{lua.name}: {name!r} is both {bases[name]!r} and {typ!r}")
            bases[name] = typ
    return bases


def main() -> None:
    fork = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "path-of-building-2-mcp" / "fork"
    bases = collect(fork)
    if not bases:
        raise SystemExit(f"no itemBases found under {fork}")
    OUT.write_text(json.dumps(bases, indent=0, sort_keys=True), encoding="utf-8", newline="\r\n")
    print(f"wrote {len(bases)} bases to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
