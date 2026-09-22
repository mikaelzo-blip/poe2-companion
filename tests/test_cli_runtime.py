"""Unit tests for companion runtime start and runtime status CLI subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from companion.cli import build_parser, handle_runtime_start, handle_runtime_status, main
from companion.runtime.status import RuntimeStatusSummary


def test_cli_parser_runtime_start_arguments() -> None:
    parser = build_parser()
    args = parser.parse_args([
        "runtime",
        "start",
        "--runtime", "my_runtime",
        "--log", "C:/Games/PoE2/Client.txt",
        "--char", "MyWitch",
        "--poll-interval", "2.5",
        "--backfill",
        "--verbose",
    ])

    assert args.subcommand == "runtime"
    assert args.runtime_action == "start"
    assert args.runtime == "my_runtime"
    assert args.log == "C:/Games/PoE2/Client.txt"
    assert args.char == "MyWitch"
    assert args.poll_interval == 2.5
    assert args.backfill is True
    assert args.verbose is True


def test_cli_parser_runtime_status_arguments() -> None:
    parser = build_parser()
    args = parser.parse_args([
        "runtime",
        "status",
        "--runtime", "my_runtime",
        "--json",
    ])

    assert args.subcommand == "runtime"
    assert args.runtime_action == "status"
    assert args.runtime == "my_runtime"
    assert args.json is True


def test_handle_runtime_status_human_and_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # 1. Human readable
    args_human = argparse.Namespace(runtime=str(runtime_dir), json=False)
    rc = handle_runtime_status(args_human)
    assert rc == 0
    out_human = capsys.readouterr().out
    assert "NOT RUNNING" in out_human

    # 2. JSON output
    args_json = argparse.Namespace(runtime=str(runtime_dir), json=True)
    rc_json = handle_runtime_status(args_json)
    assert rc_json == 0
    out_json = capsys.readouterr().out
    assert '"status": "NOT RUNNING"' in out_json


def test_handle_runtime_start_dispatches_orchestrator(tmp_path: Path) -> None:
    args = argparse.Namespace(
        runtime=str(tmp_path / "runtime"),
        log=None,
        char="TestWitch",
        poll_interval=1.0,
        backfill=False,
        verbose=False,
    )
    with patch("companion.cli.ContinuousRuntimeOrchestrator") as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        rc = handle_runtime_start(args)
        assert rc == 0
        mock_orch.run_forever.assert_called_once()
