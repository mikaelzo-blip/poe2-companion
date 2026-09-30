"""Command-line interface for PoE2 Hermes Companion (M0 through M5).

Provides modular standard-library argparse subcommands:
- companion sources unpack
- companion sources validate
- companion sources inspect
- companion state init
- companion state inspect
- companion objectives list
- companion objectives next
- companion evaluate
- companion session status
- companion session tail
- companion journey list
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from companion.notifications.manager import NotificationManager
from companion.notifications.schema import (
    NotificationCategory,
    NotificationPayload,
    NotificationSeverity,
)
from companion.notifications.sinks import ConsoleSink
from companion.observations.schema import (
    ObservationEvent,
    ObservationEventType,
    ObservationSource,
)
from companion.runtime.lease import (
    RUNTIME_WRITER_ACTIVE_CODE,
    WriterActiveError,
    guard_state_mutation,
)
from companion.runtime.models import RuntimeConfig
from companion.runtime.orchestrator import ContinuousRuntimeOrchestrator
from companion.runtime.status import inspect_runtime_status
from companion.objectives.formatter import format_objective, format_objective_list
from companion.objectives.runner import (
    run_objective_pipeline,
    save_current_objective_artifact,
)
from companion.recap.generator import (
    format_recap_json,
    format_recap_text,
    generate_session_recap,
)
from companion.sensing.client_log import ClientLogTailer, ParsedLogEventType
from companion.sensing.process_presence import ProcessMonitor
from companion.sources.manifest import generate_manifest
from companion.sources.reporter import generate_anomaly_reports
from companion.sources.unpacker import unpack_source_archive
from companion.sources.validator import validate_single_snapshot, validate_snapshots_directory
from companion.state.history import JourneyHistoryLogger
from companion.state.reconciliation import reconcile_observation
from companion.vision.budget import VisionBudgetConfig, VisionBudgetTracker
from companion.vision.classifier import classify_screen
from companion.vision.parser import evaluate_verification_state, parse_character_panel
from companion.vision.privacy import VisionPrivacyConfig, get_privacy_disclosure
from companion.vision.schema import ScreenType, VisionExtractionResult
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore
from companion.gear import (
    EquippedItem,
    GearAuditState,
    ItemSlot,
    compare_candidate_upgrade,
    compare_equipped_against_target,
    detect_mechanic_conflicts,
    evaluate_gear_staleness,
    generate_investment_advice,
    load_gear_audit_state,
    parse_item_tooltip,
    record_slot_audit,
)
from companion.intelligence import (
    evaluate_economy_priorities,
    evaluate_gear_rules,
    evaluate_story_progression,
    evaluate_survival_rules,
    evaluate_troubleshooting_rules,
    get_economy_deferred_notice,
    get_story_deferred_notice,
    get_story_quests,
)
from companion.api import (
    ApiCircuitBreaker,
    OAuthStatus,
    Poe2ApiClient,
    create_mock_character,
    get_oauth_status,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="companion",
        description="Hermes PoE2 Companion CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # sources subcommand group
    sources_parser = subparsers.add_parser("sources", help="Source build file management")
    sources_sub = sources_parser.add_subparsers(dest="sources_action", required=True)

    # sources unpack
    unpack_p = sources_sub.add_parser("unpack", help="Unpack source archive with ZIP slip protection")
    unpack_p.add_argument("--archive", "-a", required=True, help="Path to source .zip archive")
    unpack_p.add_argument(
        "--target", "-t", default="data/source/builds", help="Destination directory (default: data/source/builds)"
    )

    # sources validate
    val_p = sources_sub.add_parser("validate", help="Validate snapshots and generate manifest/reports")
    val_p.add_argument(
        "--builds", "-b", default="data/source/builds", help="Directory containing .build files"
    )
    val_p.add_argument(
        "--manifest", "-m", default="data/source/manifest.json", help="Path for canonical manifest.json"
    )
    val_p.add_argument(
        "--reports", "-r", default="data/reports", help="Directory for anomaly reports"
    )

    # sources inspect
    insp_src_p = sources_sub.add_parser("inspect", help="Inspect a specific build snapshot")
    insp_src_p.add_argument("--file", "-f", help="Path to .build file")
    insp_src_p.add_argument("--stage", "-s", help="Logical stage name (e.g. 'lvl 1-14')")
    insp_src_p.add_argument("--builds", "-b", default="data/source/builds", help="Builds directory")

    # state subcommand group
    state_parser = subparsers.add_parser("state", help="Character runtime state management")
    state_sub = state_parser.add_subparsers(dest="state_action", required=True)

    # state init
    init_p = state_sub.add_parser("init", help="Initialize a new character state")
    init_p.add_argument("--id", required=True, help="Character identifier (^[a-zA-Z0-9_-]{1,64}$)")
    init_p.add_argument("--name", required=True, help="Character name")
    init_p.add_argument("--class-name", default="Mercenary", help="Character class (default: Mercenary)")
    init_p.add_argument("--ascendancy", default="Gemling Legionnaire", help="Ascendancy (default: Gemling Legionnaire)")
    init_p.add_argument("--runtime", default="runtime", help="Runtime directory (default: runtime)")

    # state inspect
    insp_state_p = state_sub.add_parser("inspect", help="Inspect active or specific character state")
    insp_state_p.add_argument("--id", help="Character ID (defaults to active character)")
    insp_state_p.add_argument("--runtime", default="runtime", help="Runtime directory (default: runtime)")
    insp_state_p.add_argument("--json", action="store_true", help="Output full JSON state")

    # objectives subcommand group
    obj_parser = subparsers.add_parser("objectives", help="Objective engine inspection")
    obj_sub = obj_parser.add_subparsers(dest="objectives_action", required=True)

    # objectives list
    list_p = obj_sub.add_parser("list", help="List all generated objectives in deterministic priority order")
    list_p.add_argument("--id", help="Character ID (defaults to active character)")
    list_p.add_argument("--runtime", default="runtime", help="Runtime directory (default: runtime)")
    list_p.add_argument("--builds", default="data/source/builds", help="Builds directory (default: data/source/builds)")
    list_p.add_argument("--rules", help="Path to guide rules YAML")
    list_p.add_argument("--json", action="store_true", help="Output full JSON evaluation result")

    # objectives next
    next_p = obj_sub.add_parser("next", help="Display the single highest-priority actionable objective")
    next_p.add_argument("--id", help="Character ID (defaults to active character)")
    next_p.add_argument("--runtime", default="runtime", help="Runtime directory (default: runtime)")
    next_p.add_argument("--builds", default="data/source/builds", help="Builds directory (default: data/source/builds)")
    next_p.add_argument("--rules", help="Path to guide rules YAML")
    next_p.add_argument("--json", action="store_true", help="Output primary objective as JSON")

    # evaluate command
    eval_p = subparsers.add_parser("evaluate", help="Evaluate character state and emit CURRENT_OBJECTIVE.json")
    eval_p.add_argument("character_file", help="Path to character state JSON file")
    eval_p.add_argument("--runtime", default="runtime", help="Runtime directory (default: runtime)")
    eval_p.add_argument("--builds", default="data/source/builds", help="Builds directory (default: data/source/builds)")
    eval_p.add_argument("--rules", help="Path to guide rules YAML")
    eval_p.add_argument("--out", help="Path to write CURRENT_OBJECTIVE.json artifact")
    eval_p.add_argument("--json", action="store_true", help="Output primary objective as JSON")

    # session subcommand group
    session_parser = subparsers.add_parser("session", help="Live session monitoring and client log tailing")
    session_sub = session_parser.add_subparsers(dest="session_action", required=True)

    status_p = session_sub.add_parser("status", help="Display game process and active session status")
    status_p.add_argument("--id", help="Character ID (defaults to active character)")
    status_p.add_argument("--runtime", default="runtime", help="Runtime directory (default: runtime)")
    status_p.add_argument("--json", action="store_true", help="Output session status as JSON")

    tail_p = session_sub.add_parser("tail", help="Tail client log and reconcile live observations")
    tail_p.add_argument("--log", help="Path to Client.txt log file")
    tail_p.add_argument("--id", help="Character ID (defaults to active character)")
    tail_p.add_argument("--runtime", default="runtime", help="Runtime directory (default: runtime)")
    tail_p.add_argument("--once", action="store_true", help="Execute single poll cycle and exit")
    tail_p.add_argument("--json", action="store_true", help="Output processed observation events as JSON")

    recap_p = session_sub.add_parser("recap", help="Generate post-session summary recap from journey history")
    recap_p.add_argument("--runtime", default="runtime", help="Runtime directory (default: runtime)")
    recap_p.add_argument("--session-id", help="Optional session identifier")
    recap_p.add_argument("--json", action="store_true", help="Output session recap as JSON")

    # notify subcommand group
    notify_parser = subparsers.add_parser("notify", help="Notification delivery inspection and testing")
    notify_sub = notify_parser.add_subparsers(dest="notify_action", required=True)

    test_notify_p = notify_sub.add_parser("test", help="Test notification dispatch through policy")
    test_notify_p.add_argument("--title", default="Test Alert", help="Notification title")
    test_notify_p.add_argument("--message", default="Test notification message", help="Notification message body")
    test_notify_p.add_argument("--severity", default="INFO", help="Notification severity (CRITICAL, WARNING, INFO)")
    test_notify_p.add_argument("--category", default="OPTIMIZATION", help="Notification category")
    test_notify_p.add_argument("--zone", default="The Clear Fell Encampment", help="Simulated current zone")
    test_notify_p.add_argument("--json", action="store_true", help="Output dispatch result as JSON")

    # journey subcommand group
    journey_parser = subparsers.add_parser("journey", help="Inspect historical progression journey")
    journey_sub = journey_parser.add_subparsers(dest="journey_action", required=True)

    jlist_p = journey_sub.add_parser("list", help="List recent journey history milestones")
    jlist_p.add_argument("--runtime", default="runtime", help="Runtime directory (default: runtime)")
    jlist_p.add_argument("--limit", type=int, default=20, help="Maximum number of history entries (default: 20)")
    jlist_p.add_argument("--json", action="store_true", help="Output history entries as JSON")

    # vision subcommand group
    vision_parser = subparsers.add_parser("vision", help="Read-only visual screen sensing and panel parsing")
    vision_sub = vision_parser.add_subparsers(dest="vision_action", required=True)

    vstat_p = vision_sub.add_parser("status", help="Inspect vision sensor budget and privacy status")
    vstat_p.add_argument("--json", action="store_true", help="Output status as JSON")

    vpanel_p = vision_sub.add_parser("parse-panel", help="Parse character panel text into defensive stats")
    vpanel_p.add_argument("--file", help="Path to file containing character panel text")
    vpanel_p.add_argument("--text", help="Raw character panel text")
    vpanel_p.add_argument("--json", action="store_true", help="Output parsed stats as JSON")

    # gear subcommand group
    gear_parser = subparsers.add_parser("gear", help="Gear auto-analysis and audit")
    gear_sub = gear_parser.add_subparsers(dest="gear_action", required=True)

    gstat_p = gear_sub.add_parser("status", help="Inspect equipped gear audit status and conflicts")
    gstat_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    gstat_p.add_argument("--character-id", help="Character ID (defaults to active character or default)")
    gstat_p.add_argument("--json", action="store_true", help="Output status as JSON")

    gaudit_p = gear_sub.add_parser("audit", help="Audit or record an equipment slot")
    gaudit_p.add_argument("--slot", required=True, help="Equipment slot to audit (e.g. boots, helmet)")
    gaudit_p.add_argument("--file", help="Path to file containing tooltip text")
    gaudit_p.add_argument("--text", help="Raw tooltip text")
    gaudit_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    gaudit_p.add_argument("--character-id", help="Character ID")
    gaudit_p.add_argument("--json", action="store_true", help="Output result as JSON")

    gcomp_p = gear_sub.add_parser("compare", help="Compare equipped item or candidate upgrade")
    gcomp_p.add_argument("--slot", required=True, help="Equipment slot (e.g. boots, helmet)")
    gcomp_p.add_argument("--file", help="Path to candidate tooltip file")
    gcomp_p.add_argument("--text", help="Candidate raw tooltip text")
    gcomp_p.add_argument("--milestone", type=int, default=52, help="Upcoming progression milestone level")
    gcomp_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    gcomp_p.add_argument("--character-id", help="Character ID")
    gcomp_p.add_argument("--json", action="store_true", help="Output comparison as JSON")

    # Equipment Intelligence gear subparsers
    glive_p = gear_sub.add_parser("live", help="Start MVP live clipboard monitoring mode")
    glive_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    glive_p.add_argument("--stage", help="Build progression stage (e.g. 'lvl 15-32', 'lvl 52 swap'). If omitted, uses persisted runtime stage.")
    glive_p.add_argument("--character-id", help="Character ID")
    glive_p.add_argument("--weapon-set", help="Target weapon set (e.g. set_1, set_2)")
    glive_p.add_argument("--poll-interval", type=float, default=0.25, help="Clipboard polling interval in seconds")
    glive_p.add_argument("--json", action="store_true", help="Output recommendation as JSON")
    glive_p.add_argument("--bootstrap", action="store_true", help="Enable live bootstrap mode for unequipped slots")
    glive_p.add_argument("--pob-character", help="Character name for PoB2 live simulation (milestone default: BOMSHAK)")
    glive_p.add_argument("--no-pob", action="store_true", help="Disable PoB2 live equipment advisor")

    gclip_p = gear_sub.add_parser("inspect-clipboard", help="Inspect and evaluate item from clipboard")
    gclip_p.add_argument("--slot", help="Target equipment slot")
    gclip_p.add_argument("--weapon-set", help="Target weapon set (e.g. set_1, set_2)")
    gclip_p.add_argument("--stage", default="EARLY_ENDGAME", help="Build progression stage (PRE_SWAP, EARLY_ENDGAME, PINNACLE_ENDGAME)")
    gclip_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    gclip_p.add_argument("--character-id", help="Character ID")
    gclip_p.add_argument("--json", action="store_true", help="Output recommendation as JSON")

    geval_p = gear_sub.add_parser("evaluate", help="Evaluate candidate item from file")
    geval_p.add_argument("--file", required=True, help="Path to item text file")
    geval_p.add_argument("--slot", help="Target equipment slot")
    geval_p.add_argument("--weapon-set", help="Target weapon set (e.g. set_1, set_2)")
    geval_p.add_argument("--stage", default="EARLY_ENDGAME", help="Build progression stage")
    geval_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    geval_p.add_argument("--character-id", help="Character ID")
    geval_p.add_argument("--json", action="store_true", help="Output recommendation as JSON")

    gbase_p = gear_sub.add_parser("baseline", help="Manage character stat baseline")
    base_sub = gbase_p.add_subparsers(dest="baseline_action", required=True)

    bset_p = base_sub.add_parser("set", help="Set or record character stat baseline")
    bset_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    bset_p.add_argument("--character-id", help="Character ID")
    bset_p.add_argument("--life", type=int, help="Character maximum Life")
    bset_p.add_argument("--armour", type=int, help="Character total Armour")
    bset_p.add_argument("--evasion", type=int, help="Character total Evasion")
    bset_p.add_argument("--energy-shield", type=int, help="Character Energy Shield")
    bset_p.add_argument("--fire-res", type=int, help="Effective Fire Resistance")
    bset_p.add_argument("--fire-raw", type=int, help="Raw Uncapped Fire Resistance")
    bset_p.add_argument("--max-fire-res", type=int, help="Max Fire Resistance")
    bset_p.add_argument("--cold-res", type=int, help="Effective Cold Resistance")
    bset_p.add_argument("--cold-raw", type=int, help="Raw Uncapped Cold Resistance")
    bset_p.add_argument("--max-cold-res", type=int, help="Max Cold Resistance")
    bset_p.add_argument("--lightning-res", type=int, help="Effective Lightning Resistance")
    bset_p.add_argument("--lightning-raw", type=int, help="Raw Uncapped Lightning Resistance")
    bset_p.add_argument("--max-lightning-res", type=int, help="Max Lightning Resistance")
    bset_p.add_argument("--chaos-res", type=int, help="Effective Chaos Resistance")
    bset_p.add_argument("--chaos-raw", type=int, help="Raw Uncapped Chaos Resistance")
    bset_p.add_argument("--max-chaos-res", type=int, help="Max Chaos Resistance")
    bset_p.add_argument("--str", type=int, help="Character Strength")
    bset_p.add_argument("--dex", type=int, help="Character Dexterity")
    bset_p.add_argument("--int", type=int, help="Character Intelligence")
    bset_p.add_argument("--ms", type=int, help="Character Movement Speed %%")

    bshow_p = base_sub.add_parser("show", help="Show current character stat baseline")
    bshow_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    bshow_p.add_argument("--character-id", help="Character ID")

    bref_p = base_sub.add_parser("refresh", help="Refresh baseline anchoring to current revision")
    bref_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    bref_p.add_argument("--character-id", help="Character ID")
    bref_p.add_argument("--life", type=int, help="Character maximum Life")
    bref_p.add_argument("--armour", type=int, help="Character total Armour")
    bref_p.add_argument("--evasion", type=int, help="Character total Evasion")
    bref_p.add_argument("--energy-shield", type=int, help="Character Energy Shield")
    bref_p.add_argument("--fire-res", type=int, help="Effective Fire Resistance")
    bref_p.add_argument("--fire-raw", type=int, help="Raw Uncapped Fire Resistance")
    bref_p.add_argument("--max-fire-res", type=int, help="Max Fire Resistance")
    bref_p.add_argument("--cold-res", type=int, help="Effective Cold Resistance")
    bref_p.add_argument("--cold-raw", type=int, help="Raw Uncapped Cold Resistance")
    bref_p.add_argument("--max-cold-res", type=int, help="Max Cold Resistance")
    bref_p.add_argument("--lightning-res", type=int, help="Effective Lightning Resistance")
    bref_p.add_argument("--lightning-raw", type=int, help="Raw Uncapped Lightning Resistance")
    bref_p.add_argument("--max-lightning-res", type=int, help="Max Lightning Resistance")
    bref_p.add_argument("--chaos-res", type=int, help="Effective Chaos Resistance")
    bref_p.add_argument("--chaos-raw", type=int, help="Raw Uncapped Chaos Resistance")
    bref_p.add_argument("--max-chaos-res", type=int, help="Max Chaos Resistance")
    bref_p.add_argument("--str", type=int, help="Character Strength")
    bref_p.add_argument("--dex", type=int, help="Character Dexterity")
    bref_p.add_argument("--int", type=int, help="Character Intelligence")
    bref_p.add_argument("--ms", type=int, help="Character Movement Speed %%")

    gload_p = gear_sub.add_parser("loadout", help="Manage equipped gear loadout")
    loadout_sub = gload_p.add_subparsers(dest="loadout_action", required=True)

    lset_p = loadout_sub.add_parser("set-clipboard", help="Set loadout slot from clipboard or file")
    lset_p.add_argument("--slot", required=True, help="Slot name (e.g. boots, helmet, ring1)")
    lset_p.add_argument("--weapon-set", help="Weapon set (e.g. weapon_set_1, weapon_set_2)")
    lset_p.add_argument("--file", help="Path to item text file (optional fallback for clipboard)")
    lset_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    lset_p.add_argument("--character-id", help="Character ID")

    lfin_p = loadout_sub.add_parser("finalize", help="Finalize draft loadout and initialize revision 1")
    lfin_p.add_argument("--loadout-id", help="Optional loadout ID")
    lfin_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    lfin_p.add_argument("--character-id", help="Character ID")

    lshow_p = loadout_sub.add_parser("show", help="Show current equipped loadout")
    lshow_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    lshow_p.add_argument("--character-id", help="Character ID")

    lclr_p = loadout_sub.add_parser("clear", help="Clear equipped loadout slot")
    lclr_p.add_argument("--slot", required=True, help="Slot name")
    lclr_p.add_argument("--weapon-set", help="Weapon set")
    lclr_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    lclr_p.add_argument("--character-id", help="Character ID")

    lprom_p = loadout_sub.add_parser("promote-candidate", help="Promote candidate item into loadout")
    lprom_p.add_argument("--slot", required=True, help="Slot name")
    lprom_p.add_argument("--weapon-set", help="Weapon set")
    lprom_p.add_argument("--file", help="Path to candidate file (or uses clipboard)")
    lprom_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    lprom_p.add_argument("--character-id", help="Character ID")

    # Milestone 9: Intelligence
    intel_parser = subparsers.add_parser("intelligence", help="Expanded build intelligence and diagnostic advisory")
    intel_sub = intel_parser.add_subparsers(dest="intel_action", required=True)

    iaudit_p = intel_sub.add_parser("audit", help="Run comprehensive intelligence advisory audit")
    iaudit_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    iaudit_p.add_argument("--character-id", help="Character ID")
    iaudit_p.add_argument("--level", type=int, help="Override character level")
    iaudit_p.add_argument("--act", type=int, default=1, help="Override current story act")
    iaudit_p.add_argument("--json", action="store_true", help="Output advisories as JSON")

    istory_p = intel_sub.add_parser("story", help="View story quest checklist and permanent rewards")
    istory_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    istory_p.add_argument("--character-id", help="Character ID")
    istory_p.add_argument("--json", action="store_true", help="Output quest status as JSON")

    iecon_p = intel_sub.add_parser("economy", help="View gear upgrade prioritization and ROI guidance")
    iecon_p.add_argument("--level", type=int, default=50, help="Character level")
    iecon_p.add_argument("--resists-capped", action="store_true", help="Flag indicating elemental resists are capped")
    iecon_p.add_argument("--weapon-lagging", action="store_true", help="Flag indicating weapon DPS is lagging")
    iecon_p.add_argument("--json", action="store_true", help="Output priorities as JSON")

    # Milestone 10: Official API
    api_parser = subparsers.add_parser("api", help="Official PoE2 Character API synchronization and PoB2 integration")
    api_sub = api_parser.add_subparsers(dest="api_action", required=True)

    astat_p = api_sub.add_parser("status", help="Inspect official API OAuth status and circuit breaker")
    astat_p.add_argument("--json", action="store_true", help="Output status as JSON")

    async_p = api_sub.add_parser("sync", help="Synchronize character from official API or local mock")
    async_p.add_argument("--character-id", default="char_1", help="Character ID to synchronize")
    async_p.add_argument("--mock", action="store_true", help="Use deterministic mock adapter")
    async_p.add_argument("--json", action="store_true", help="Output synchronized character as JSON")

    # Continuous Runtime
    runtime_parser = subparsers.add_parser("runtime", help="Continuous foreground runtime and status")
    runtime_sub = runtime_parser.add_subparsers(dest="runtime_action", required=True)

    rstart_p = runtime_sub.add_parser("start", help="Start continuous foreground companion runtime")
    rstart_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    rstart_p.add_argument("--log", help="Path to Client.txt log file")
    rstart_p.add_argument("--char", help="Character ID or name override")
    rstart_p.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval in seconds")
    rstart_p.add_argument("--backfill", action="store_true", help="Catch up historical backlog without live notifications")
    rstart_p.add_argument("--verbose", action="store_true", help="Enable verbose diagnostic console logging")
    rstart_p.add_argument("--observe-dev", action="store_true", help="Enable subordinate development observation mode")
    rstart_p.add_argument("--observe-screens", action="store_true", help="Enable opt-in asynchronous screenshot evidence capture")
    rstart_p.add_argument("--observe-display", type=int, default=1, help="Monitor index to capture (default: 1)")

    rstat_p = runtime_sub.add_parser("status", help="Inspect local runtime process status and heartbeats")
    rstat_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    rstat_p.add_argument("--json", action="store_true", help="Output runtime status as JSON")

    # observe subcommand
    observe_p = subparsers.add_parser("observe", help="Development observation mode operations")
    observe_sub = observe_p.add_subparsers(dest="observe_action", required=True)

    # observe mark <note>
    omark_p = observe_sub.add_parser("mark", help="Record manual engineer or player marker")
    omark_p.add_argument("note", help="Observation note text")
    omark_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    omark_p.add_argument("--session-id", default=None, help="Target observation session ID (optional)")

    # observe status
    ostat_p = observe_sub.add_parser("status", help="Inspect observation session status")
    ostat_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    ostat_p.add_argument("--session-id", default=None, help="Target observation session ID (default: latest)")
    ostat_p.add_argument("--json", action="store_true", help="Output status as JSON")
    ostat_p.add_argument("--live", action="store_true", help="Display multi-tier live status")

    # observe live-status
    olive_stat_p = observe_sub.add_parser("live-status", help="Inspect multi-tier live observation and review status")
    olive_stat_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    olive_stat_p.add_argument("--session-id", default=None, help="Target observation session ID (default: latest)")
    olive_stat_p.add_argument("--json", action="store_true", help="Output status as JSON")

    # observe analyze-live
    oanalyze_p = observe_sub.add_parser("analyze-live", help="Execute deterministic local live analysis step")
    oanalyze_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    oanalyze_p.add_argument("--session-id", default=None, help="Target observation session ID (default: latest)")
    oanalyze_p.add_argument("--max-events", type=int, default=None, help="Maximum events to consume this step")
    oanalyze_p.add_argument("--json", action="store_true", help="Output step result as JSON")

    # observe summary
    osum_p = observe_sub.add_parser("summary", help="Inspect or generate session summary metrics")
    osum_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    osum_p.add_argument("--session-id", default=None, help="Target observation session ID (default: latest)")
    osum_p.add_argument("--json", action="store_true", help="Output summary as JSON")

    # observe review
    orev_p = observe_sub.add_parser("review", help="Generate DEVELOPMENT_OBSERVATION_REPORT.md")
    orev_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    orev_p.add_argument("--session-id", default=None, help="Target observation session ID (default: latest)")
    orev_p.add_argument("--output", default="DEVELOPMENT_OBSERVATION_REPORT.md", help="Output markdown path")

    # observe cleanup
    oclean_p = observe_sub.add_parser("cleanup", help="Enforce observation retention boundaries")
    oclean_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    oclean_p.add_argument("--prune", action="store_true", help="Perform pruning of old sessions")
    oclean_p.add_argument("--quota-bytes", type=int, default=500 * 1024 * 1024, help="Disk quota in bytes (default: 500MB)")
    oclean_p.add_argument("--keep-sessions", type=int, default=20, help="Maximum sessions to retain (default: 20)")

    # Top-level mark alias for observe mark
    mark_p = subparsers.add_parser("mark", help="Record manual engineer or player marker (alias for observe mark)")
    mark_p.add_argument("note", help="Observation note text")
    mark_p.add_argument("--runtime", default="runtime", help="Runtime state directory")
    mark_p.add_argument("--session-id", default=None, help="Target observation session ID (optional)")

    # Subcommand: dashboard
    dash_p = subparsers.add_parser("dashboard", help="Launch zero-backend browser dashboard for live companion suite")
    dash_p.add_argument("--port", type=int, default=8080, help="Local port for dashboard server (default: 8080)")
    dash_p.add_argument("--no-browser", action="store_true", help="Do not automatically open default web browser")

    return parser


def handle_sources_unpack(args: argparse.Namespace) -> int:
    try:
        snapshots = unpack_source_archive(args.archive, args.target)
        print(f"Successfully unpacked {len(snapshots)} snapshots into '{args.target}':")
        for s in snapshots:
            print(f"  - [{s.logical_stage}] {s.filename} ({s.byte_size} bytes, sha256={s.sha256[:12]}...)")
        return 0
    except Exception as e:
        sys.stderr.write(f"Unpack error: {e}\n")
        return 1


def handle_sources_validate(args: argparse.Namespace) -> int:
    try:
        report = validate_snapshots_directory(args.builds)
        generate_manifest(report, output_path=args.manifest)
        json_rep, md_rep = generate_anomaly_reports(report, output_dir=args.reports)

        print("Validation complete:")
        print(f"  Total snapshots: {report.total_snapshots}")
        print(f"  Passed: {report.passed_count}")
        print(f"  Anomalies: {report.anomalies_count}")
        print(f"  Failed: {report.failed_count}")
        print(f"  Manifest written to: {args.manifest}")
        print(f"  Reports written to: {json_rep} and {md_rep}")

        if report.cast_on_dodge_findings:
            print(f"  Cast on Dodge anomalies detected: {len(report.cast_on_dodge_findings)}")

        return 0 if report.failed_count == 0 else 1
    except Exception as e:
        sys.stderr.write(f"Validation error: {e}\n")
        return 1


def handle_sources_inspect(args: argparse.Namespace) -> int:
    try:
        target_file = None
        stage = args.stage

        if args.file:
            target_file = Path(args.file)
        elif stage:
            builds_dir = Path(args.builds)
            matching = [f for f in builds_dir.glob("*.build") if f.name.startswith(stage)]
            if matching:
                target_file = matching[0]
            else:
                sys.stderr.write(f"No build file found matching stage '{stage}' in '{args.builds}'\n")
                return 1
        else:
            sys.stderr.write("Please specify either --file or --stage to inspect.\n")
            return 1

        res = validate_single_snapshot(target_file, expected_stage=stage)
        print(f"Snapshot Inspection: {res.filename}")
        print(f"  Stage: {res.logical_stage}")
        print(f"  SHA-256: {res.sha256}")
        print(f"  Byte size: {res.byte_size}")
        print(f"  Status: {res.validation_status}")
        if res.normalized_build:
            norm = res.normalized_build
            print(f"  Passives: {len(norm.passives)} unique (id, weapon_set) entries")
            print(f"  Skills: {len(norm.skills)} active gems")
            print(f"  Inventory recommendations: {len(norm.inventory_slots)} slots")
        if res.anomalies:
            print("  Anomalies:")
            for a in res.anomalies:
                print(f"    - {a.category}: {a.symbol} ({a.details})")
        return 0
    except Exception as e:
        sys.stderr.write(f"Inspect error: {e}\n")
        return 1


def handle_state_init(args: argparse.Namespace) -> int:
    try:
        with guard_state_mutation(args.runtime):
            store = CharacterStateStore(args.runtime)
            char = CharacterState.create_initial(
                character_id=args.id,
                character_name=args.name,
                character_class=args.class_name,
                ascendancy=args.ascendancy,
            )
            saved_path = store.save_character(char)
            store.set_active_character(args.id)

            print(f"Initialized character '{args.id}' ({args.name}):")
            print(f"  State file: {saved_path}")
            print(f"  Set as active character in: {store.active_file}")
            return 0
    except WriterActiveError as e:
        sys.stderr.write(f"State init error: {e}\n")
        return 1
    except Exception as e:
        sys.stderr.write(f"State init error: {e}\n")
        return 1


def handle_state_inspect(args: argparse.Namespace) -> int:
    try:
        store = CharacterStateStore(args.runtime)
        char_id = args.id

        if not char_id:
            active_char = store.get_active_character()
            if active_char is None:
                sys.stderr.write("No active character found and no --id specified.\n")
                return 1
            char = active_char
        else:
            char = store.load_character(char_id)

        if args.json:
            print(json.dumps(char.model_dump(), indent=2))
        else:
            print(f"Character: {char.character_name} (ID: {char.character_id})")
            print(f"  Class / Ascendancy: {char.character_class} / {char.ascendancy}")
            print(f"  Level: {char.level.value} (verification: {char.level.verification_state.value})")
            print(f"  Zone: {char.current_zone.value if char.current_zone else 'Unknown'} (Act {char.current_act.value if char.current_act else 1})")
            print(f"  Deaths: {char.death_count.value if char.death_count else 0}")
            print(f"  Weapon set: {char.equipped_weapon_set.value if char.equipped_weapon_set else 1}")
            print(f"  Session Active: {char.session_active}")
        return 0
    except Exception as e:
        sys.stderr.write(f"State inspect error: {e}\n")
        return 1


def _load_character_for_objectives(args: argparse.Namespace) -> CharacterState | None:
    store = CharacterStateStore(args.runtime)
    if args.id:
        try:
            return store.load_character(args.id)
        except Exception as e:
            sys.stderr.write(f"Failed to load character '{args.id}': {e}\n")
            return None
    active = store.get_active_character()
    if active is None:
        sys.stderr.write("No active character found in store and no --id specified.\n")
    return active


def handle_objectives_list(args: argparse.Namespace) -> int:
    char = _load_character_for_objectives(args)
    if char is None:
        return 1

    try:
        eval_result = run_objective_pipeline(
            character_state=char,
            builds_dir=args.builds,
            rules_path=args.rules,
        )
        if args.json:
            print(json.dumps(eval_result.model_dump(), indent=2))
        else:
            print(format_objective_list(eval_result.all_objectives))
        return 0
    except Exception as e:
        sys.stderr.write(f"Objectives list error: {e}\n")
        return 1


def handle_objectives_next(args: argparse.Namespace) -> int:
    char = _load_character_for_objectives(args)
    if char is None:
        return 1

    try:
        eval_result = run_objective_pipeline(
            character_state=char,
            builds_dir=args.builds,
            rules_path=args.rules,
        )
        if args.json:
            if eval_result.primary_objective:
                print(json.dumps(eval_result.primary_objective.model_dump(), indent=2))
            else:
                print(json.dumps({"status": eval_result.status, "primary_objective": None}, indent=2))
        else:
            print(format_objective(eval_result.primary_objective))
        return 0
    except Exception as e:
        sys.stderr.write(f"Objectives next error: {e}\n")
        return 1


def handle_evaluate(args: argparse.Namespace) -> int:
    char_file = Path(args.character_file)
    if not char_file.is_file():
        sys.stderr.write(f"Character file not found: {args.character_file}\n")
        return 1

    try:
        char_dict = json.loads(char_file.read_text(encoding="utf-8"))
        char = CharacterState.model_validate(char_dict)
    except Exception as e:
        sys.stderr.write(f"Failed to parse character state from '{char_file}': {e}\n")
        return 1

    try:
        eval_result = run_objective_pipeline(
            character_state=char,
            builds_dir=args.builds,
            rules_path=args.rules,
        )
        out_path = args.out if args.out else Path(args.runtime) / "CURRENT_OBJECTIVE.json"
        save_current_objective_artifact(eval_result, out_path=out_path)

        if args.json:
            if eval_result.primary_objective:
                print(json.dumps(eval_result.primary_objective.model_dump(), indent=2))
            else:
                print(json.dumps({"status": eval_result.status, "primary_objective": None}, indent=2))
        else:
            print(format_objective(eval_result.primary_objective))
        return 0
    except Exception as e:
        sys.stderr.write(f"Evaluation error: {e}\n")
        return 1


def handle_session_status(args: argparse.Namespace) -> int:
    char = _load_character_for_objectives(args)
    if char is None:
        return 1

    monitor = ProcessMonitor()
    transition = monitor.poll()

    status_data = {
        "character_id": char.character_id,
        "character_name": char.character_name,
        "process_state": transition.current_state.value,
        "session_active": char.session_active,
        "current_zone": char.current_zone.value if char.current_zone else "Unknown",
        "level": char.level.value,
        "death_count": char.death_count.value if char.death_count else 0,
        "last_observed_at": char.last_observed_at,
    }

    if args.json:
        print(json.dumps(status_data, indent=2))
    else:
        print(f"Session Status: [{status_data['process_state']}] Active: {status_data['session_active']}")
        print(f"Character: {status_data['character_name']} ({status_data['character_id']}) Level: {status_data['level']}")
        print(f"Zone: {status_data['current_zone']} | Deaths: {status_data['death_count']} | Last Observed: {status_data['last_observed_at']}")
    return 0


def handle_session_tail(args: argparse.Namespace) -> int:
    runtime_dir = Path(args.runtime)
    try:
        with guard_state_mutation(runtime_dir):
            store = CharacterStateStore(runtime_dir)
            char = _load_character_for_objectives(args)
            if char is None:
                return 1

            log_path = Path(args.log) if args.log else Path("Client.txt")
            tailer = ClientLogTailer(log_path)
            logger = JourneyHistoryLogger(runtime_dir / "journey_history.jsonl")

            events = tailer.poll()
            reconciled_events: list[ObservationEvent] = []
            for ev in events:
                obs_type = {
                    ParsedLogEventType.ZONE_ENTER: ObservationEventType.ZONE_TRANSITION,
                    ParsedLogEventType.ZONE_GENERATE: ObservationEventType.ZONE_TRANSITION,
                    ParsedLogEventType.LEVEL_UP: ObservationEventType.LEVEL_UP,
                    ParsedLogEventType.DEATH: ObservationEventType.DEATH,
                }.get(ev.event_type, ObservationEventType.CUSTOM)

                obs_event = ObservationEvent.create(
                    event_type=obs_type,
                    source=ObservationSource.CLIENT_LOG,
                    character_id=char.character_id,
                    payload=ev.payload,
                    timestamp=ev.timestamp,
                )
                char = reconcile_observation(char, obs_event)
                logger.record_event(obs_event)
                reconciled_events.append(obs_event)

            store.save_character(char)

            if args.json:
                print(json.dumps([e.model_dump() for e in reconciled_events], indent=2, default=str))
            else:
                print(f"Tail poll processed {len(reconciled_events)} events. Character '{char.character_name}' updated.")
            return 0
    except WriterActiveError as e:
        sys.stderr.write(f"Session tail error: {e}\n")
        return 1
    except Exception as e:
        sys.stderr.write(f"Session tail error: {e}\n")
        return 1


def handle_session_recap(args: argparse.Namespace) -> int:
    runtime_dir = Path(args.runtime)
    logger = JourneyHistoryLogger(runtime_dir / "journey_history.jsonl")
    entries = logger.read_history()
    recap = generate_session_recap(entries, session_id=args.session_id)

    if args.json:
        print(format_recap_json(recap))
    else:
        print(format_recap_text(recap))
    return 0


def handle_notify_test(args: argparse.Namespace) -> int:
    try:
        sev = NotificationSeverity(args.severity.upper())
    except ValueError:
        sev = NotificationSeverity.INFO

    try:
        cat = NotificationCategory(args.category.upper())
    except ValueError:
        cat = NotificationCategory.OPTIMIZATION

    payload = NotificationPayload.create(
        title=args.title,
        message=args.message,
        severity=sev,
        category=cat,
    )
    manager = NotificationManager(sinks=[ConsoleSink(use_stderr=args.json)])
    res = manager.dispatch(payload, current_zone=args.zone)

    if args.json:
        print(json.dumps(res.model_dump(), indent=2))
    else:
        print(f"[{res.status.value}] Notification '{payload.title}' dispatched in zone '{args.zone}'.")
    return 0


def handle_journey_list(args: argparse.Namespace) -> int:
    runtime_dir = Path(args.runtime)
    logger = JourneyHistoryLogger(runtime_dir / "journey_history.jsonl")
    entries = logger.read_history(limit=args.limit)

    if args.json:
        print(json.dumps([e.model_dump() for e in entries], indent=2))
    else:
        if not entries:
            print("No journey history records found.")
        for entry in entries:
            print(f"[{entry.timestamp}] {entry.event_type.upper()}: {json.dumps(entry.payload)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "sources":
        if args.sources_action == "unpack":
            return handle_sources_unpack(args)
        elif args.sources_action == "validate":
            return handle_sources_validate(args)
        elif args.sources_action == "inspect":
            return handle_sources_inspect(args)
    elif args.subcommand == "state":
        if args.state_action == "init":
            return handle_state_init(args)
        elif args.state_action == "inspect":
            return handle_state_inspect(args)
    elif args.subcommand == "objectives":
        if args.objectives_action == "list":
            return handle_objectives_list(args)
        elif args.objectives_action == "next":
            return handle_objectives_next(args)
    elif args.subcommand == "evaluate":
        return handle_evaluate(args)
    elif args.subcommand == "session":
        if args.session_action == "status":
            return handle_session_status(args)
        elif args.session_action == "tail":
            return handle_session_tail(args)
        elif args.session_action == "recap":
            return handle_session_recap(args)
    elif args.subcommand == "notify":
        if args.notify_action == "test":
            return handle_notify_test(args)
    elif args.subcommand == "journey":
        if args.journey_action == "list":
            return handle_journey_list(args)
    elif args.subcommand == "vision":
        if args.vision_action == "status":
            return handle_vision_status(args)
        elif args.vision_action == "parse-panel":
            return handle_vision_parse_panel(args)
    elif args.subcommand == "gear":
        if args.gear_action == "status":
            return handle_gear_status(args)
        elif args.gear_action == "audit":
            return handle_gear_audit(args)
        elif args.gear_action == "compare":
            return handle_gear_compare(args)
        elif args.gear_action == "live":
            return handle_gear_live(args)
        elif args.gear_action == "inspect-clipboard":
            return handle_gear_inspect_clipboard(args)
        elif args.gear_action == "evaluate":
            return handle_gear_evaluate(args)
        elif args.gear_action == "baseline":
            return handle_gear_baseline(args)
        elif args.gear_action == "loadout":
            return handle_gear_loadout(args)
    elif args.subcommand == "intelligence":
        if args.intel_action == "audit":
            return handle_intelligence_audit(args)
        elif args.intel_action == "story":
            return handle_intelligence_story(args)
        elif args.intel_action == "economy":
            return handle_intelligence_economy(args)
    elif args.subcommand == "api":
        if args.api_action == "status":
            return handle_api_status(args)
        elif args.api_action == "sync":
            return handle_api_sync(args)
    elif args.subcommand == "runtime":
        if args.runtime_action == "start":
            return handle_runtime_start(args)
        elif args.runtime_action == "status":
            return handle_runtime_status(args)
    elif args.subcommand == "observe":
        if args.observe_action == "mark":
            return handle_observe_mark(args)
        elif args.observe_action == "status":
            if getattr(args, "live", False):
                return handle_observe_live_status(args)
            return handle_observe_status(args)
        elif args.observe_action == "live-status":
            return handle_observe_live_status(args)
        elif args.observe_action == "analyze-live":
            return handle_observe_analyze_live(args)
        elif args.observe_action == "summary":
            return handle_observe_summary(args)
        elif args.observe_action == "review":
            return handle_observe_review(args)
        elif args.observe_action == "cleanup":
            return handle_observe_cleanup(args)
    elif args.subcommand == "mark":
        return handle_observe_mark(args)
    elif args.subcommand == "dashboard":
        from companion.dashboard_server import serve_dashboard
        serve_dashboard(port=args.port, open_browser=not args.no_browser)
        return 0

    return 0


def handle_vision_status(args: argparse.Namespace) -> int:
    budget_cfg = VisionBudgetConfig()
    tracker = VisionBudgetTracker(budget_cfg)
    privacy_cfg = VisionPrivacyConfig()

    status_data = {
        "budget": {
            "enabled": budget_cfg.enabled,
            "max_calls_per_hour": budget_cfg.max_calls_per_hour,
            "min_seconds_between_captures": budget_cfg.min_seconds_between_captures,
            "calls_in_past_hour": tracker.calls_in_past_hour,
            "screenshot_cache_max_mb": budget_cfg.screenshot_cache_max_mb,
            "screenshot_cache_ttl_minutes": budget_cfg.screenshot_cache_ttl_minutes,
        },
        "privacy": {
            "mode": privacy_cfg.mode,
            "provider": privacy_cfg.provider,
            "disclosure": get_privacy_disclosure(privacy_cfg),
        },
    }

    if args.json:
        print(json.dumps(status_data, indent=2))
    else:
        print(f"Vision Sensor: [{privacy_cfg.mode.upper()}] Provider: {privacy_cfg.provider}")
        print(f"Budget: {status_data['budget']['calls_in_past_hour']}/{budget_cfg.max_calls_per_hour} calls/hr (Cooldown: {budget_cfg.min_seconds_between_captures}s)")
        print(f"Privacy: {status_data['privacy']['disclosure']}")
    return 0


def handle_vision_parse_panel(args: argparse.Namespace) -> int:
    text = ""
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: file '{args.file}' not found.", file=sys.stderr)
            return 1
        text = file_path.read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        print("Error: must provide --file or --text", file=sys.stderr)
        return 1

    screen_type, conf = classify_screen(text)
    stats = parse_character_panel(text) if screen_type == ScreenType.CHARACTER_PANEL else None
    stats_obj, ver_state = evaluate_verification_state([stats] if stats else [])

    res = VisionExtractionResult(
        screen_type=screen_type,
        stats=stats_obj,
        verification_state=ver_state,
        confidence=conf,
        raw_text=text[:200],
    )

    if args.json:
        print(json.dumps(res.model_dump(), indent=2))
    else:
        print(f"Screen Type: {res.screen_type.value} (Confidence: {res.confidence:.2f})")
        print(f"Verification State: {res.verification_state.value}")
        if res.stats:
            print(f"Stats: Life={res.stats.life}, Mana={res.stats.mana}, Fire={res.stats.fire_res}%, Cold={res.stats.cold_res}%, Lightning={res.stats.lightning_res}%, Chaos={res.stats.chaos_res}%")
    return 0


def _resolve_char_id(args: argparse.Namespace) -> str:
    if getattr(args, "character_id", None):
        return args.character_id
    store = CharacterStateStore(args.runtime)
    active = store.get_active_character()
    if active:
        return active.character_id
    return "default_char"


def handle_gear_status(args: argparse.Namespace) -> int:
    char_id = _resolve_char_id(args)
    state = load_gear_audit_state(args.runtime, char_id)

    char_attrs = None
    try:
        store = CharacterStateStore(args.runtime)
        char_state = store.load_character(char_id)
        if char_state and char_state.attributes:
            char_attrs = char_state.attributes
    except Exception:
        char_attrs = None

    all_conflicts = []
    slots_summary = {}

    for slot, item in state.slots.items():
        staleness = evaluate_gear_staleness(item)
        conflicts = detect_mechanic_conflicts(item, character_attributes=char_attrs)
        all_conflicts.extend([c.model_dump() for c in conflicts])
        slots_summary[slot.value] = {
            "name": item.name,
            "base_type": item.base_type,
            "verification": staleness.value,
            "item_hash": item.item_hash,
            "observed_at": item.observed_at,
        }

    data = {
        "character_id": char_id,
        "slots": slots_summary,
        "conflicts": all_conflicts,
        "updated_at": state.updated_at,
    }

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"Gear Status for Character '{char_id}':")
        print(f"  Audited slots: {len(slots_summary)}")
        for s_name, s_info in slots_summary.items():
            print(f"  - {s_name}: {s_info['name'] or s_info['base_type']} [{s_info['verification'].upper()}]")
        if all_conflicts:
            print(f"  Active conflicts: {len(all_conflicts)}")
            for c in all_conflicts:
                print(f"    * [{c['slot']}] {c['description']}")
    return 0


def handle_gear_audit(args: argparse.Namespace) -> int:
    char_id = _resolve_char_id(args)
    try:
        slot = ItemSlot(args.slot.lower())
    except ValueError:
        print(f"Error: unknown slot '{args.slot}'", file=sys.stderr)
        return 1

    text = ""
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"Error: file '{args.file}' not found.", file=sys.stderr)
            return 1
        text = p.read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        print("Error: must provide --file or --text for audit", file=sys.stderr)
        return 1

    item, ver_state, _ = record_slot_audit(args.runtime, char_id, slot, [text])
    if item is None:
        print("Audit failed: could not parse tooltip.", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(item.model_dump(), indent=2))
    else:
        print(f"Audited slot '{slot.value}':")
        print(f"  Item: {item.name or item.base_type} ({item.rarity.value})")
        print(f"  Verification: {item.verification.value}")
        print(f"  Item hash: {item.item_hash}")
    return 0


def handle_gear_compare(args: argparse.Namespace) -> int:
    char_id = _resolve_char_id(args)
    try:
        slot = ItemSlot(args.slot.lower())
    except ValueError:
        print(f"Error: unknown slot '{args.slot}'", file=sys.stderr)
        return 1

    text = ""
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"Error: file '{args.file}' not found.", file=sys.stderr)
            return 1
        text = p.read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        print("Error: must provide --file or --text for candidate", file=sys.stderr)
        return 1

    candidate = parse_item_tooltip(text, slot=slot)
    state = load_gear_audit_state(args.runtime, char_id)
    equipped = state.slots.get(slot, candidate)

    comp = compare_equipped_against_target(candidate, {})
    advice = generate_investment_advice(candidate, upcoming_milestone_level=args.milestone)
    upg = compare_candidate_upgrade(equipped, candidate)

    res = {
        "slot": slot.value,
        "candidate": candidate.model_dump(),
        "comparison": comp.model_dump(),
        "advice": advice.model_dump(),
        "upgrade_recommendation": upg.model_dump(),
    }

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"Gear Comparison for slot '{slot.value}':")
        print(f"  Candidate: {candidate.name or candidate.base_type}")
        print(f"  Upgrade verdict: {upg.verdict.value}")
        if upg.candidate_satisfied:
            print(f"  Candidate satisfied: {', '.join(upg.candidate_satisfied)}")
        if upg.candidate_missing:
            print(f"  Candidate missing: {', '.join(upg.candidate_missing)}")
        if upg.trade_offs:
            print(f"  Trade-offs: {upg.trade_offs}")
        print(f"  Investment advice: {advice.recommendation}")
    return 0


def handle_gear_live(args: argparse.Namespace) -> int:
    from companion.equipment.live_watcher import resolve_live_stage, run_live_watcher

    char_id = _resolve_char_id(args)
    try:
        stage = resolve_live_stage(
            stage_arg=getattr(args, "stage", None),
            runtime_dir=args.runtime,
            char_id=char_id,
        )
    except ValueError as err:
        sys.stderr.write(f"Error: {err}\n")
        return 1

    pob_enabled = not getattr(args, "no_pob", False)
    pob_char = getattr(args, "pob_character", None) or "BOMSHAK"

    return run_live_watcher(
        runtime_dir=args.runtime,
        character_id=char_id,
        stage=stage,
        poll_interval=getattr(args, "poll_interval", 0.25),
        as_json=getattr(args, "json", False),
        weapon_set=getattr(args, "weapon_set", None),
        bootstrap=getattr(args, "bootstrap", False),
        pob_character=pob_char,
        pob_enabled=pob_enabled,
    )


def handle_gear_inspect_clipboard(args: argparse.Namespace) -> int:
    from companion.equipment.clipboard import run_inspect_clipboard
    from companion.equipment.rules import BuildProgressionStage

    char_id = _resolve_char_id(args)
    stage = BuildProgressionStage(getattr(args, "stage", "EARLY_ENDGAME"))
    try:
        report, rec = run_inspect_clipboard(
            runtime_dir=args.runtime,
            character_id=char_id,
            slot_name=getattr(args, "slot", None),
            weapon_set_name=getattr(args, "weapon_set", None),
            stage=stage,
        )
        if getattr(args, "json", False):
            print(rec.model_dump_json(indent=2))
        else:
            print(report)
        return 0
    except Exception as exc:
        sys.stderr.write(f"Error inspecting clipboard: {exc}\n")
        return 1


def handle_gear_evaluate(args: argparse.Namespace) -> int:
    from companion.equipment.clipboard import run_evaluate_file
    from companion.equipment.rules import BuildProgressionStage

    char_id = _resolve_char_id(args)
    stage = BuildProgressionStage(getattr(args, "stage", "EARLY_ENDGAME"))
    try:
        report, rec = run_evaluate_file(
            runtime_dir=args.runtime,
            file_path=args.file,
            character_id=char_id,
            slot_name=getattr(args, "slot", None),
            weapon_set_name=getattr(args, "weapon_set", None),
            stage=stage,
        )
        if getattr(args, "json", False):
            print(rec.model_dump_json(indent=2))
        else:
            print(report)
        return 0
    except Exception as exc:
        sys.stderr.write(f"Error evaluating candidate file: {exc}\n")
        return 1


def handle_gear_baseline(args: argparse.Namespace) -> int:
    from companion.equipment.baseline_cli import (
        run_baseline_refresh,
        run_baseline_set,
        run_baseline_show,
    )

    char_id = _resolve_char_id(args)
    if args.baseline_action == "set":
        base = run_baseline_set(
            runtime_dir=args.runtime,
            character_id=char_id,
            life=getattr(args, "life", None),
            armour=getattr(args, "armour", None),
            evasion=getattr(args, "evasion", None),
            energy_shield=getattr(args, "energy_shield", None),
            fire_res=getattr(args, "fire_res", None),
            fire_raw=getattr(args, "fire_raw", None),
            max_fire_res=getattr(args, "max_fire_res", None),
            cold_res=getattr(args, "cold_res", None),
            cold_raw=getattr(args, "cold_raw", None),
            max_cold_res=getattr(args, "max_cold_res", None),
            lightning_res=getattr(args, "lightning_res", None),
            lightning_raw=getattr(args, "lightning_raw", None),
            max_lightning_res=getattr(args, "max_lightning_res", None),
            chaos_res=getattr(args, "chaos_res", None),
            chaos_raw=getattr(args, "chaos_raw", None),
            max_chaos_res=getattr(args, "max_chaos_res", None),
            strength=getattr(args, "str", None),
            dexterity=getattr(args, "dex", None),
            intelligence=getattr(args, "int", None),
            movement_speed=getattr(args, "ms", None),
        )
        print(run_baseline_show(runtime_dir=args.runtime, character_id=char_id))
        return 0
    elif args.baseline_action == "refresh":
        base = run_baseline_refresh(
            runtime_dir=args.runtime,
            character_id=char_id,
            life=getattr(args, "life", None),
            armour=getattr(args, "armour", None),
            evasion=getattr(args, "evasion", None),
            energy_shield=getattr(args, "energy_shield", None),
            fire_res=getattr(args, "fire_res", None),
            fire_raw=getattr(args, "fire_raw", None),
            max_fire_res=getattr(args, "max_fire_res", None),
            cold_res=getattr(args, "cold_res", None),
            cold_raw=getattr(args, "cold_raw", None),
            max_cold_res=getattr(args, "max_cold_res", None),
            lightning_res=getattr(args, "lightning_res", None),
            lightning_raw=getattr(args, "lightning_raw", None),
            max_lightning_res=getattr(args, "max_lightning_res", None),
            chaos_res=getattr(args, "chaos_res", None),
            chaos_raw=getattr(args, "chaos_raw", None),
            max_chaos_res=getattr(args, "max_chaos_res", None),
            strength=getattr(args, "str", None),
            dexterity=getattr(args, "dex", None),
            intelligence=getattr(args, "int", None),
            movement_speed=getattr(args, "ms", None),
        )
        print(run_baseline_show(runtime_dir=args.runtime, character_id=char_id))
        return 0
    elif args.baseline_action == "show":
        print(run_baseline_show(runtime_dir=args.runtime, character_id=char_id))
        return 0
    return 1


def handle_gear_loadout(args: argparse.Namespace) -> int:
    from companion.equipment.clipboard import read_item_input
    from companion.equipment.loadout_cli import (
        run_loadout_clear,
        run_loadout_finalize,
        run_loadout_promote_candidate,
        run_loadout_set_item,
        run_loadout_show,
    )
    from companion.equipment.parser import InvalidItemClipboardError

    char_id = _resolve_char_id(args)

    if args.loadout_action == "set-clipboard":
        raw_text = read_item_input(getattr(args, "file", None))
        try:
            l = run_loadout_set_item(
                runtime_dir=args.runtime,
                character_id=char_id,
                slot_name=args.slot,
                item_text=raw_text,
                weapon_set_name=getattr(args, "weapon_set", None),
            )
            trans = getattr(l, "last_transition", None)
            if trans and trans.is_finalized:
                if trans.is_changed:
                    print(
                        f"Slot '{args.slot}' updated.\n"
                        f"Loadout revision: {trans.previous_revision} -> {trans.new_revision}.\n"
                        f"Existing baseline is now stale and requires re-baseline."
                    )
                else:
                    print(
                        f"Slot '{args.slot}' unchanged.\n"
                        f"Loadout revision remains {trans.new_revision}."
                    )
            else:
                print(f"Slot '{args.slot}' updated in loadout draft for character '{char_id}'.")
            return 0
        except (InvalidItemClipboardError, ValueError) as exc:
            sys.stderr.write(f"Error setting loadout slot: {exc}\n")
            return 1
    elif args.loadout_action == "finalize":
        l = run_loadout_finalize(
            runtime_dir=args.runtime,
            character_id=char_id,
            loadout_id=getattr(args, "loadout_id", None),
        )
        print(f"Loadout finalized with revision {l.revision} ({len(l.known_slots)} known slots, {len(l.unknown_slots)} unknown slots).")
        return 0
    elif args.loadout_action == "show":
        print(run_loadout_show(runtime_dir=args.runtime, character_id=char_id))
        return 0
    elif args.loadout_action == "clear":
        l = run_loadout_clear(
            runtime_dir=args.runtime,
            character_id=char_id,
            slot_name=args.slot,
            weapon_set_name=getattr(args, "weapon_set", None),
        )
        trans = getattr(l, "last_transition", None)
        if trans and trans.is_finalized:
            if trans.is_changed:
                print(
                    f"Slot '{args.slot}' cleared.\n"
                    f"Loadout revision: {trans.previous_revision} -> {trans.new_revision}.\n"
                    f"Existing baseline is now stale and requires re-baseline."
                )
            else:
                print(
                    f"Slot '{args.slot}' unchanged.\n"
                    f"Loadout revision remains {trans.new_revision}."
                )
        else:
            print(f"Slot '{args.slot}' cleared from loadout.")
        return 0
    elif args.loadout_action == "promote-candidate":
        raw_text = read_item_input(getattr(args, "file", None))
        try:
            new_loadout, _ = run_loadout_promote_candidate(
                runtime_dir=args.runtime,
                character_id=char_id,
                slot_name=args.slot,
                candidate_text=raw_text,
                weapon_set_name=getattr(args, "weapon_set", None),
            )
            trans = getattr(new_loadout, "last_transition", None)
            if trans and trans.is_finalized:
                if trans.is_changed:
                    print(
                        f"Slot '{args.slot}' updated.\n"
                        f"Loadout revision: {trans.previous_revision} -> {trans.new_revision}.\n"
                        f"Existing baseline is now stale and requires re-baseline."
                    )
                else:
                    print(
                        f"Slot '{args.slot}' unchanged.\n"
                        f"Loadout revision remains {trans.new_revision}."
                    )
            else:
                print(f"Slot '{args.slot}' updated in loadout draft for character '{char_id}'.")
            return 0
        except (InvalidItemClipboardError, ValueError) as exc:
            sys.stderr.write(f"Error promoting candidate: {exc}\n")
            return 1
    return 1


def handle_intelligence_story(args: argparse.Namespace) -> int:
    notice = get_story_deferred_notice()
    if args.json:
        print(json.dumps(notice, indent=2))
    else:
        print("PoE2 Permanent Reward Story Quests: [DEFERRED]")
        print(f"  Notice: {notice['message']}")
    return 0


def handle_intelligence_economy(args: argparse.Namespace) -> int:
    notice = get_economy_deferred_notice()
    if args.json:
        print(json.dumps(notice, indent=2))
    else:
        print(f"Upgrade Prioritization & Economy Guidance (Level {args.level}): [DEFERRED]")
        print(f"  Notice: {notice['message']}")
    return 0


def handle_intelligence_audit(args: argparse.Namespace) -> int:
    char_id = _resolve_char_id(args)
    level = args.level or 1
    act = args.act or 1

    store = CharacterStateStore(args.runtime)
    if args.level is None and char_id in store.list_characters():
        try:
            char_state = store.load_character(char_id)
            level = char_state.level
        except Exception:
            pass

    gear_state = load_gear_audit_state(args.runtime, char_id)

    # 1. Survival rules
    survival_adv = evaluate_survival_rules(panel_stats=None, character_level=level, current_act=act)

    # 2. Gear rules
    gear_adv = evaluate_gear_rules(gear_state=gear_state, character_level=level)

    # 3. Troubleshooting rules
    char_attrs = {"str": 50, "dex": 50, "int": 50}
    trouble_adv = evaluate_troubleshooting_rules(
        character_attributes=char_attrs,
        required_attributes={"str": 50, "dex": 50, "int": 50},
        current_mana=500,
        unreserved_mana=150,
        main_skill_cost=20,
    )

    # 4. Story rules
    story_adv = evaluate_story_progression(current_act=act)

    all_advisories = survival_adv + gear_adv + trouble_adv + story_adv

    if args.json:
        data = {
            "character_id": char_id,
            "level": level,
            "act": act,
            "advisories": [a.model_dump() for a in all_advisories],
        }
        print(json.dumps(data, indent=2))
    else:
        print(f"Expanded Intelligence Audit for Character '{char_id}' (Level {level}, Act {act}):")
        print(f"  Total advisories: {len(all_advisories)}")
        for a in all_advisories:
            print(f"  [{a.severity.value}] [{a.category.value}] {a.title}: {a.description}")
            print(f"    -> {a.recommendation}")
    return 0


def handle_api_status(args: argparse.Namespace) -> int:
    status = get_oauth_status()
    client = Poe2ApiClient()
    cb = client.circuit_breaker
    live_ready = status == OAuthStatus.CONFIGURED and client.is_live_configured()
    data = {
        "oauth_status": status.value,
        "circuit_breaker": cb.to_dict(),
        "live_credentials_available": live_ready,
        "status_note": (
            "Ready for OAuth synchronization."
            if live_ready
            else "Live API synchronization requires POE2_CLIENT_ID, POE2_ACCESS_TOKEN, and POE2_API_URL. Offline/mock contracts fully functional."
        ),
    }
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print("PoE2 Official Character API Status:")
        print(f"  OAuth Status: {status.value}")
        print(f"  Circuit Breaker: {cb.state.value}")
        print(f"  Note: {data['status_note']}")
    return 0


def handle_api_sync(args: argparse.Namespace) -> int:
    char_id = args.character_id
    mock_data = create_mock_character(character_id=char_id, level=70) if args.mock else None
    client = Poe2ApiClient(mock_data=mock_data)

    char, status_msg = client.sync_character(char_id)
    if char is None:
        if args.json:
            print(json.dumps({"status": status_msg, "character": None}, indent=2))
        else:
            print(f"Sync failed: {status_msg}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"status": status_msg, "character": char.model_dump()}, indent=2))
    else:
        print(f"Synchronized Character '{char.name}' (Level {char.level} {char.class_name}):")
        print(f"  Allocated Passives: {len(char.passives)}")
        print(f"  Equipment Items: {len(char.equipment)}")
        print(f"  Spirit Capacity: {char.quest_stats.spirit_capacity}")
    return 0


def handle_runtime_start(args: argparse.Namespace) -> int:
    try:
        cfg = RuntimeConfig(
            runtime_dir=Path(args.runtime),
            client_log_path=Path(args.log) if args.log else None,
            character_id=args.char,
            poll_interval=args.poll_interval,
            backfill=args.backfill,
            verbose=args.verbose,
            observe_dev=getattr(args, "observe_dev", False),
            observe_screens=getattr(args, "observe_screens", False),
            observe_display=getattr(args, "observe_display", 1),
        )
        orchestrator = ContinuousRuntimeOrchestrator(cfg)
        orchestrator.run_forever()
        return 0
    except Exception as e:
        sys.stderr.write(f"Runtime error: {e}\n")
        return 1


def handle_runtime_status(args: argparse.Namespace) -> int:
    summary = inspect_runtime_status(args.runtime)
    if args.json:
        print(summary.model_dump_json(indent=2))
    else:
        print(f"Companion Runtime Status: [{summary.status}]")
        if summary.runtime_pid:
            print(f"  PID: {summary.runtime_pid}")
        if summary.lifecycle_state:
            print(f"  Lifecycle: {summary.lifecycle_state.value}")
        print(f"  Game Presence: {'Running' if summary.game_process_running else 'Not Running'}")
        if summary.active_character_id:
            print(f"  Active Character: {summary.active_character_id}")
        if summary.last_heartbeat:
            age_str = f" ({summary.heartbeat_age_seconds:.1f}s ago)" if summary.heartbeat_age_seconds is not None else ""
            print(f"  Last Heartbeat: {summary.last_heartbeat}{age_str}")
        print(f"  Writer Lock Held: {summary.writer_lock_held}")
        if summary.message:
            print(f"  Message: {summary.message}")
    return 0


def _find_session_dir(runtime_dir: Path, session_id: str | None = None) -> Path | None:
    obs_dir = runtime_dir / "observations"
    if not obs_dir.exists():
        return None
    if session_id:
        sdir = obs_dir / session_id
        return sdir if sdir.exists() else None
    sessions = [d for d in obs_dir.iterdir() if d.is_dir() and d.name != "marker_inbox"]
    if not sessions:
        return None
    sessions.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return sessions[0]


def handle_observe_mark(args: argparse.Namespace) -> int:
    from companion.observe.markers import write_marker, is_session_active
    runtime_dir = Path(args.runtime)
    inbox_dir = runtime_dir / "observations" / "marker_inbox"
    marker_path, marker_id = write_marker(args.note, inbox_dir, session_id=args.session_id)
    if not is_session_active(runtime_dir):
        print(f"Warning: No active observation session found; marker saved unattached to {marker_path.name}")
    else:
        print(f"Marker recorded: {marker_id}")
    return 0


def handle_observe_status(args: argparse.Namespace) -> int:
    from companion.observe.manifest import ManifestManager
    runtime_dir = Path(args.runtime)
    sdir = _find_session_dir(runtime_dir, args.session_id)
    if not sdir:
        sys.stderr.write("No observation session found\n")
        return 1

    manifest_mgr = ManifestManager(sdir / "session_manifest.json")
    manifest = manifest_mgr.load()
    if not manifest:
        sys.stderr.write("Session manifest not found or unreadable\n")
        return 1

    if args.json:
        print(manifest.model_dump_json(indent=2))
    else:
        print(f"Observation Session: {manifest.session_id} [{manifest.status.value}]")
        print(f"  Started: {manifest.started_at}")
        if manifest.ended_at:
            print(f"  Ended: {manifest.ended_at}")
        print(f"  High Watermark: {manifest.sequence_high_watermark}")
        print(f"  Persisted Events: {manifest.persisted_event_count}")
        print(f"  Dropped Events: {manifest.dropped_event_count} (High Priority: {manifest.dropped_high_priority_count})")
        print(f"  Health State: {manifest.health_state.value}")
    return 0


def handle_observe_analyze_live(args: argparse.Namespace) -> int:
    from companion.observe.analyst import LocalLiveAnalyst
    runtime_dir = Path(args.runtime)
    sdir = _find_session_dir(runtime_dir, args.session_id)
    if not sdir:
        sys.stderr.write("No observation session found\n")
        return 1

    session_id = sdir.name
    analyst = LocalLiveAnalyst(session_dir=sdir, session_id=session_id)
    signals = analyst.step()

    if getattr(args, "json", False):
        out = {
            "session_id": session_id,
            "contiguous_frontier": analyst.reader.contiguous_frontier,
            "read_ahead_saturated": analyst.reader.read_ahead_saturated,
            "signals_derived": len(signals),
            "signals": [s.model_dump() for s in signals],
        }
        print(json.dumps(out, indent=2))
    else:
        print(f"Analysis step complete for session {session_id}. Frontier: {analyst.reader.contiguous_frontier}. Derived {len(signals)} local signals.")
    return 0


def handle_observe_live_status(args: argparse.Namespace) -> int:
    from companion.observe.cursor import ReviewCursorManager, compute_reader_lag, compute_review_lag
    from companion.observe.journal import ReviewJournalManager
    from companion.observe.manifest import ManifestManager
    from companion.observe.reader import IncrementalStreamReader

    runtime_dir = Path(args.runtime)
    sdir = _find_session_dir(runtime_dir, args.session_id)
    if not sdir:
        sys.stderr.write("No observation session found\n")
        return 1

    session_id = sdir.name
    manifest_mgr = ManifestManager(sdir / "session_manifest.json")
    manifest = manifest_mgr.load()
    if not manifest:
        sys.stderr.write("Session manifest not found or unreadable\n")
        return 1

    reader = IncrementalStreamReader(session_dir=sdir, session_id=session_id)
    review_cursor_mgr = ReviewCursorManager(
        cursor_path=sdir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )
    journal_mgr = ReviewJournalManager(session_dir=sdir, session_id=session_id)

    obs_latest = manifest.sequence_high_watermark
    reader_frontier = reader.contiguous_frontier
    review_frontier = review_cursor_mgr.review_contiguous_frontier

    reader_lag = compute_reader_lag(obs_latest, reader_frontier)
    review_lag = compute_review_lag(reader_frontier, review_frontier)

    # Check Hermes review heartbeat
    status_file = sdir / "live_analysis" / "hermes_review_status.json"
    hermes_active = False
    heartbeat_str = "never"
    if status_file.exists():
        try:
            status_data = json.loads(status_file.read_text(encoding="utf-8"))
            last_hb_str = status_data.get("last_heartbeat")
            state_val = status_data.get("state", "OFFLINE")
            if last_hb_str and state_val == "ACTIVE":
                last_hb = datetime.fromisoformat(last_hb_str)
                now = datetime.now(timezone.utc)
                diff_s = (now - last_hb).total_seconds()
                if diff_s <= 30.0:
                    hermes_active = True
                    heartbeat_str = f"{int(max(0, diff_s))}s ago"
                else:
                    heartbeat_str = f"stale ({int(diff_s)}s ago)"
            else:
                heartbeat_str = state_val
        except Exception:
            pass

    hermes_status_label = "ACTIVE" if hermes_active else "OFFLINE / INACTIVE / STALE"

    signals_count = 0
    signals_file = sdir / "live_analysis" / "local_signals.jsonl"
    if signals_file.exists():
        try:
            with open(signals_file, "r", encoding="utf-8") as f:
                signals_count = sum(1 for line in f if line.strip())
        except Exception:
            pass

    findings = journal_mgr.get_findings()
    completed_batches_count = len(review_cursor_mgr.completed_review_batches)
    pending_batches_count = len(review_cursor_mgr.pending_review_batches)
    pending_markers_count = len(reader.pending_marker_ids)

    if getattr(args, "json", False):
        out = {
            "session_id": session_id,
            "observation": {
                "status": manifest.status.value,
                "observer_health": manifest.health_state.value,
                "latest_sequence": obs_latest,
                "persisted_events": manifest.persisted_event_count,
                "dropped_events": manifest.dropped_event_count,
            },
            "local_analysis": {
                "reader_contiguous_sequence": reader_frontier,
                "reader_lag": reader_lag,
                "read_ahead_saturated": reader.read_ahead_saturated,
                "factual_signals_count": signals_count,
            },
            "hermes_review": {
                "status": hermes_status_label,
                "heartbeat": heartbeat_str,
                "reviewed_contiguous_sequence": review_frontier,
                "review_lag": review_lag,
                "review_batches_completed": completed_batches_count,
                "review_batches_pending": pending_batches_count,
                "findings_count": len(findings),
                "pending_markers_count": pending_markers_count,
            },
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"Observation Session: {session_id}")
    print("[OBSERVATION]")
    print(f"  Status: {manifest.status.value}")
    print(f"  Observer Health: {manifest.health_state.value}")
    print(f"  Latest Sequence: {obs_latest}")
    print()
    print("[LOCAL ANALYSIS]")
    print(f"  Reader Contiguous Sequence: {reader_frontier} (Reader Lag: {reader_lag} events)")
    sat_label = "SATURATED (ANALYST_READ_AHEAD_SATURATED)" if reader.read_ahead_saturated else "HEALTHY"
    print(f"  Reader Saturation: {sat_label}")
    print(f"  Factual Signals: {signals_count} active")
    print()
    print("[HERMES REVIEW]")
    print(f"  Status: {hermes_status_label} (Heartbeat: {heartbeat_str})")
    print(f"  Reviewed Contiguous Sequence: {review_frontier} (Review Lag: {review_lag} events)")
    print(f"  Review Batches: {completed_batches_count} completed, {pending_batches_count} pending")
    print(f"  Active Findings: {len(findings)} candidate(s)")
    for f in findings[:5]:
        print(f"    - [{f.status.value}] {f.title}")
    print(f"  Pending Markers: {pending_markers_count} unreviewed")
    return 0


def handle_observe_summary(args: argparse.Namespace) -> int:
    from companion.observe.summary import SessionSummaryGenerator
    runtime_dir = Path(args.runtime)
    sdir = _find_session_dir(runtime_dir, args.session_id)
    if not sdir:
        sys.stderr.write("No observation session found\n")
        return 1

    gen = SessionSummaryGenerator(sdir)
    summary = gen.generate()
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        summary_md = sdir / "session_summary.md"
        if summary_md.exists():
            print(summary_md.read_text(encoding="utf-8"))
        else:
            print(json.dumps(summary, indent=2))
    return 0


def handle_observe_review(args: argparse.Namespace) -> int:
    from companion.observe.review import generate_development_observation_report
    runtime_dir = Path(args.runtime)
    sdir = _find_session_dir(runtime_dir, args.session_id)
    if not sdir:
        sys.stderr.write("No observation session found\n")
        return 1

    out_path = Path(args.output)
    res_path = generate_development_observation_report(sdir, out_path)
    print(f"Observation review report generated at: {res_path}")
    return 0


def handle_observe_cleanup(args: argparse.Namespace) -> int:
    from companion.observe.retention import RetentionManager
    runtime_dir = Path(args.runtime)
    obs_dir = runtime_dir / "observations"
    if not obs_dir.exists():
        print("No observation directory found.")
        return 0

    mgr = RetentionManager(
        obs_dir,
        max_sessions=args.keep_sessions,
        quota_bytes=args.quota_bytes,
    )
    evicted = mgr.clean_storage()
    if getattr(args, "json", False):
        print(json.dumps({"evicted_sessions": evicted}, indent=2))
    else:
        print(f"Observation Cleanup {'(Executed)' if args.prune else '(Dry Run)'}:")
        print(f"  Sessions Evicted: {len(evicted)}")
        for e in evicted:
            print(f"  - Evicted {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
