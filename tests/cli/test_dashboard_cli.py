"""Tests for Dashboard launcher and CLI subcommand."""

from __future__ import annotations

from unittest.mock import patch
from companion.cli import build_parser, main


def test_dashboard_cli_parser_registered() -> None:
    parser = build_parser()
    args = parser.parse_args(["dashboard", "--port", "9090", "--no-browser"])
    assert args.subcommand == "dashboard"
    assert args.port == 9090
    assert args.no_browser is True


def test_dashboard_cli_execution() -> None:
    with patch("companion.dashboard_server.serve_dashboard") as mock_serve:
        exit_code = main(["dashboard", "--port", "8888", "--no-browser"])
        assert exit_code == 0
        mock_serve.assert_called_once_with(port=8888, open_browser=False)
