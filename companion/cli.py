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
    all_conflicts = []
    slots_summary = {}

    for slot, item in state.slots.items():
        staleness = evaluate_gear_staleness(item)
        conflicts = detect_mechanic_conflicts(item)
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


if __name__ == "__main__":
    sys.exit(main())
