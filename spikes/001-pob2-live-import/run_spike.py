"""Spike 001: PoB2 Live Import & Item Simulation Runner.

Executes the small PoC against the sibling MCP server at C:/Projects/path-of-building-2-mcp
without altering any companion production behavior.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Connect to sibling MCP server environment
MCP_SERVER_DIR = Path("C:/Projects/path-of-building-2-mcp/server")
if not MCP_SERVER_DIR.exists():
    raise SystemExit(f"ERROR: MCP server directory not found at {MCP_SERVER_DIR}")

sys.path.insert(0, str(MCP_SERVER_DIR))

from pob_mcp import poe_api, poe_oauth
from pob_mcp.engine import PobEngine
from pob_mcp.optimizer import simulate_item

DEFAULT_CANDIDATE_HELMET = """Item Class: Helmets
Rarity: Rare
Kraken Dome
Soldier Greathelm
--------
Armour: 45
--------
Requirements:
Level: 15
Str: 22
--------
Item Level: 19
--------
+20 to maximum Life
+7% to Lightning Resistance
1.2 Life Regenerated per second
"""


def main(character_name: str = "BOMSHAK", candidate_raw: str = DEFAULT_CANDIDATE_HELMET):
    print(f"=== PoB2 Live Import Spike (Character: {character_name}) ===")

    # 1. Fetch character from GGG API
    t0 = time.perf_counter()
    raw_json = poe_api.fetch_character_raw(character_name)
    fetch_latency = time.perf_counter() - t0
    print(f"[OK] Fetched character payload ({len(raw_json)} bytes) in {fetch_latency:.3f}s")

    # 2. Boot Engine
    boot_t0 = time.perf_counter()
    with PobEngine() as engine:
        boot_latency = time.perf_counter() - boot_t0
        print(f"[OK] PoB2 Engine booted in {boot_latency:.3f}s")

        # 3. Import character
        imp_t0 = time.perf_counter()
        imp_res = engine.call("import_character", json=raw_json)
        imp_latency = time.perf_counter() - imp_t0
        xml = imp_res.pop("xml", None)
        print(f"[OK] Character imported into PoB2 in {imp_latency:.3f}s (Class: {imp_res.get('className')}, Level: {imp_res.get('level')})")

        # 4. Read current equipped helmet
        current_helmet = engine.call("get_equipped", slot="Helmet")
        print("\n--- Current Equipped Helmet ---")
        if current_helmet.get("equipped"):
            print(f"Name: {current_helmet.get('name')}")
            print(f"Raw Text:\n{current_helmet.get('raw')}")
        else:
            print("Slot is empty.")

        # Read pre-simulation defenses & stats
        def_before = engine.call("get_defenses")
        stats_before = engine.call("calc_stats")

        # 5. First-call simulation
        sim1_t0 = time.perf_counter()
        _ = simulate_item(engine, xml, slot="Helmet", raw=candidate_raw)
        sim1_latency = time.perf_counter() - sim1_t0

        # 6. Warm-call simulation
        sim2_t0 = time.perf_counter()
        _ = simulate_item(engine, xml, slot="Helmet", raw=candidate_raw)
        sim2_latency = time.perf_counter() - sim2_t0

        # Detailed delta capture
        engine.call("import_build", xml=xml)
        engine.call("equip_item", slot="Helmet", raw=candidate_raw)
        def_after = engine.call("get_defenses")
        stats_after = engine.call("calc_stats")
        engine.call("import_build", xml=xml)

        life_delta = (def_after.get("Life") or 0) - (def_before.get("Life") or 0)
        armour_delta = (def_after.get("Armour") or 0) - (def_before.get("Armour") or 0)
        evasion_delta = (def_after.get("Evasion") or 0) - (def_before.get("Evasion") or 0)
        es_delta = (def_after.get("EnergyShield") or 0) - (def_before.get("EnergyShield") or 0)
        ehp_delta = (def_after.get("TotalEHP") or 0) - (def_before.get("TotalEHP") or 0)

        fire_delta = (stats_after["defense"].get("FireResist") or 0) - (stats_before["defense"].get("FireResist") or 0)
        cold_delta = (stats_after["defense"].get("ColdResist") or 0) - (stats_before["defense"].get("ColdResist") or 0)
        lightning_delta = (stats_after["defense"].get("LightningResist") or 0) - (stats_before["defense"].get("LightningResist") or 0)
        chaos_delta = (stats_after["defense"].get("ChaosResist") or 0) - (stats_before["defense"].get("ChaosResist") or 0)
        dps_delta = (stats_after["offense"].get("CombinedDPS") or 0) - (stats_before["offense"].get("CombinedDPS") or 0)

        print("\n" + "=" * 50)
        print("SIMULATION DELTAS:")
        print("=" * 50)
        print(f"Current Helmet:   {current_helmet.get('name') if current_helmet.get('equipped') else 'Empty'}")
        print(f"Candidate Helmet: Kraken Dome (Soldier Greathelm)")
        print(f"Life Delta:       {life_delta:+d} ({def_before.get('Life')} -> {def_after.get('Life')})")
        print(f"Fire Resist:      {fire_delta:+d}% ({stats_before['defense'].get('FireResist')}% -> {stats_after['defense'].get('FireResist')}%)")
        print(f"Cold Resist:      {cold_delta:+d}% ({stats_before['defense'].get('ColdResist')}% -> {stats_after['defense'].get('ColdResist')}%)")
        print(f"Lightning Resist: {lightning_delta:+d}% ({stats_before['defense'].get('LightningResist')}% -> {stats_after['defense'].get('LightningResist')}%)")
        print(f"Chaos Resist:     {chaos_delta:+d}% ({stats_before['defense'].get('ChaosResist')}% -> {stats_after['defense'].get('ChaosResist')}%)")
        print(f"Armour Delta:     {armour_delta:+d} ({def_before.get('Armour')} -> {def_after.get('Armour')})")
        print(f"Evasion Delta:    {evasion_delta:+d} ({def_before.get('Evasion')} -> {def_after.get('Evasion')})")
        print(f"Energy Shield:    {es_delta:+d} ({def_before.get('EnergyShield')} -> {def_after.get('EnergyShield')})")
        print(f"Total EHP Delta:  {ehp_delta:+.2f} ({def_before.get('TotalEHP'):.2f} -> {def_after.get('TotalEHP'):.2f})")
        print(f"DPS Delta:        {dps_delta:+.2f} ({stats_before['offense'].get('CombinedDPS')} -> {stats_after['offense'].get('CombinedDPS')})")
        print("=" * 50)

        print("\n--- Latency Breakdown ---")
        print(f"GGG API Fetch:      {fetch_latency:.3f}s")
        print(f"PoB2 Cold Boot:     {boot_latency:.3f}s")
        print(f"Character Import:   {imp_latency:.3f}s")
        print(f"First-call Sim:     {sim1_latency:.3f}s")
        print(f"Warm-call Sim:      {sim2_latency:.3f}s")


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "BOMSHAK"
    main(name)
