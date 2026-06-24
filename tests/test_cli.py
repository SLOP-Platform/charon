from __future__ import annotations

import json
from pathlib import Path

from charon.cli import main


def test_version(capsys) -> None:
    rc = main(["version"])
    out = capsys.readouterr().out.strip()
    assert rc == 0 and out  # prints something


def test_run_mock_end_to_end(tmp_path: Path, capsys) -> None:
    state = tmp_path / "state"
    rc = main([
        "run", "--goal", "make hello", "--accept", "test -f hello.txt",
        "--backend", "mock", "--autonomy", "L1", "--state-dir", str(state),
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "complete"
    assert out["remaining"] == []
    task_id = out["task_id"]

    # ledger subcommand reflects the derived state
    rc2 = main(["ledger", task_id, "--state-dir", str(state)])
    led = json.loads(capsys.readouterr().out)
    assert rc2 == 0
    assert led["task_id"] == task_id
    assert led["verified"] == ["a0"]


def test_run_requires_accept(tmp_path: Path) -> None:
    # argparse should reject a run with no --accept
    try:
        main(["run", "--goal", "x"])
    except SystemExit as e:
        assert e.code != 0


def test_doctor_no_backend_reports_unvalidated(capsys) -> None:
    rc = main(["doctor"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1  # honest: not ok without a real agent
    assert out["spawned"] is False
    assert any("UNVALIDATED" in n or "MockBackend" in n for n in out["notes"])
