from __future__ import annotations

import json
from pathlib import Path

import charon.cli as cli_mod
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


def test_doctor_no_backend_exit0_unconfigured(capsys) -> None:
    rc = main(["doctor"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0  # unconfigured → not a failure
    assert out["status"] == "no backend configured"
    assert out["spawned"] is False  # detailed fields still present


def test_work_mock_banner(tmp_path: Path, capsys, monkeypatch) -> None:
    """Mock backend prints a banner to stderr and exits 0 even when units hold."""
    _fake_result = {
        "board_path": str(tmp_path / "board.json"),
        "rounds": 1,
        "budget_capped": False,
        "auto_land": False,
        "product_acceptance": "",
        "integration_worktree": str(tmp_path / "integ"),
        "units": [
            {
                "unit_id": "u1",
                "status": "not-run",
                "disposition": "n/a",
                "board_state": "hold",
                "note": "no committed changes between base and tip — nothing to land",
                "land": None,
            }
        ],
        "validation": {"passed": False, "note": "no acceptance command"},
    }
    monkeypatch.setattr(cli_mod, "run_work", lambda *a, **kw: _fake_result)

    units_file = tmp_path / "units.json"
    units_file.write_text(
        '[{"goal":"x","accept":["true"],"tier":"low","owned_paths":[]}]'
    )
    rc = main(["work", "--units", str(units_file)])
    captured = capsys.readouterr()
    # Honest exit code preserved: a mock run whose validation holds still exits non-zero
    # (never report a silent pass — see test_engine_e2e). The banner, not the exit code,
    # is what resolves the fresh-user "looks broken" confusion.
    assert rc == 1
    assert "mock backend" in captured.err
    assert "--backend acp" in captured.err
