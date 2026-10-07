"""Tests for Dashboard launcher and CLI subcommand."""

from __future__ import annotations

from unittest.mock import patch, MagicMock
from companion.cli import build_parser, main
from companion.dashboard_server import DashboardRequestHandler, ThreadingDashboardServer


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


def test_dashboard_send_json_handles_connection_aborted() -> None:
    handler = DashboardRequestHandler.__new__(DashboardRequestHandler)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()
    handler.wfile.write.side_effect = ConnectionAbortedError(10053, "Aborted")
    handler.close_connection = False

    # Must not raise
    handler.send_json({"test": 123})
    assert handler.close_connection is True


def test_threading_dashboard_server_suppresses_connection_error(capsys) -> None:
    server = ThreadingDashboardServer.__new__(ThreadingDashboardServer)
    try:
        raise ConnectionAbortedError(10053, "Aborted")
    except ConnectionAbortedError:
        # Pass mock request and client address
        server.handle_error(MagicMock(), ("127.0.0.1", 12345))

    captured = capsys.readouterr()
    assert "Exception occurred during processing of request" not in captured.err
