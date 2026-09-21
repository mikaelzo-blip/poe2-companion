"""Command-line interface for PoE2 Hermes Companion (M0 & M1).

Provides modular standard-library argparse subcommands:
- companion sources unpack
- companion sources validate
- companion sources inspect
- companion state init
- companion state inspect
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from companion.sources.manifest import generate_manifest
from companion.sources.models_raw import RawBuild
from companion.sources.models_normalized import normalize_build
from companion.sources.reporter import generate_anomaly_reports
from companion.sources.unpacker import EXPECTED_STAGES, unpack_source_archive
from companion.sources.validator import validate_single_snapshot, validate_snapshots_directory
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="companion",
        description="Hermes PoE2 Companion CLI (M0/M1 Foundation)",
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
            print(f"  Zone: {char.current_zone.value} (Act {char.current_act.value})")
            print(f"  Deaths: {char.death_count.value}")
            print(f"  Weapon set: {char.equipped_weapon_set.value}")
            print(f"  Progression stage: {char.build_progression.get('active_stage')}")
            print(f"  Target build: {char.build_progression.get('target_build')}")
        return 0
    except Exception as e:
        sys.stderr.write(f"State inspect error: {e}\n")
        return 1


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

    return 0


if __name__ == "__main__":
    sys.exit(main())
