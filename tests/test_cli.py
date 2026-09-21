"""Unit tests for companion CLI subcommands."""

import io
import json
from pathlib import Path
import zipfile
import pytest

from companion.cli import main
from companion.sources.unpacker import EXPECTED_STAGES


def _create_mock_zip(files: dict[str, bytes]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def test_cli_sources_workflow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # 1. Prepare mock archive
    build_payload = json.dumps({
        "name": "Test",
        "author": "Fubgun",
        "passives": [{"id": "p1"}],
        "skills": [],
        "inventory_slots": [],
    }).encode("utf-8")

    files = {f"{stage} - Fubgun.build": build_payload for stage in EXPECTED_STAGES}
    zip_path = tmp_path / "mock.zip"
    zip_path.write_bytes(_create_mock_zip(files).getvalue())

    builds_dir = tmp_path / "builds"
    manifest_path = tmp_path / "manifest.json"
    reports_dir = tmp_path / "reports"

    # 2. Run unpack
    ret_unpack = main(["sources", "unpack", "--archive", str(zip_path), "--target", str(builds_dir)])
    assert ret_unpack == 0
    captured = capsys.readouterr()
    assert "Successfully unpacked 9 snapshots" in captured.out

    # 3. Run validate
    ret_val = main([
        "sources", "validate",
        "--builds", str(builds_dir),
        "--manifest", str(manifest_path),
        "--reports", str(reports_dir),
    ])
    assert ret_val == 0
    captured = capsys.readouterr()
    assert "Validation complete:" in captured.out
    assert manifest_path.is_file()

    # 4. Run inspect
    sample_file = list(builds_dir.glob("*.build"))[0]
    ret_insp = main(["sources", "inspect", "--file", str(sample_file)])
    assert ret_insp == 0
    captured = capsys.readouterr()
    assert "Snapshot Inspection:" in captured.out


def test_cli_state_workflow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir = tmp_path / "runtime"

    # 1. State init
    ret_init = main([
        "state", "init",
        "--id", "char_cli_test",
        "--name", "CliHero",
        "--runtime", str(runtime_dir),
    ])
    assert ret_init == 0
    captured = capsys.readouterr()
    assert "Initialized character 'char_cli_test'" in captured.out

    # 2. State inspect active
    ret_insp = main(["state", "inspect", "--runtime", str(runtime_dir)])
    assert ret_insp == 0
    captured = capsys.readouterr()
    assert "Character: CliHero (ID: char_cli_test)" in captured.out

    # 3. State inspect with --json
    ret_json = main(["state", "inspect", "--id", "char_cli_test", "--runtime", str(runtime_dir), "--json"])
    assert ret_json == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["character_id"] == "char_cli_test"
