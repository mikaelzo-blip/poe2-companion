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
from companion.sensing.client_log import ClientLogTailer, ParsedLogEventType
from companion.sensing.process_presence import ProcessMonitor
from companion.sources.manifest import generate_manifest
from companion.sources.reporter import generate_anomaly_reports
from companion.sources.unpacker import unpack_source_archive
from companion.sources.validator import validate_single_snapshot, validate_snapshots_directory
from companion.state.history import JourneyHistoryLogger
from companion.state.reconciliation import reconcile_observation
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


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

    # journey subcommand group
    journey_parser = subparsers.add_parser("journey", help="Inspect historical progression journey")
    journey_sub = journey_parser.add_subparsers(dest="journey_action", required=True)

    jlist_p = journey_sub.add_parser("list", help="List recent journey history milestones")
    jlist_p.add_argument("--runtime", default="runtime", help="Runtime directory (default: runtime)")
    jlist_p.add_argument("--limit", type=int, default=20, help="Maximum number of history entries (default: 20)")
    jlist_p.add_argument("--json", action="store_true", help="Output history entries as JSON")

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
    elif args.subcommand == "journey":
        if args.journey_action == "list":
            return handle_journey_list(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
