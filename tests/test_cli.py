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


# ----------------------------------------------------------------- intake (INTAKE1)
_INTAKE_MD = """\
# Product acceptance
The whole thing works.

## Build the thing
id: TICKET-42
owns: `src/charon/thing.py`
accept: `pytest -q tests/test_thing.py`

## Vague idea
Make it nicer somehow.
"""


def test_intake_import_writes_plan_and_prints_markdown(tmp_path: Path, capsys) -> None:
    src = tmp_path / "backlog.md"
    src.write_text(_INTAKE_MD)
    plan_path = tmp_path / "plan.json"
    rc = main(["intake", "import", str(src), "--out", str(plan_path)])
    captured = capsys.readouterr()
    assert rc == 0
    # the human-readable markdown goes to stdout for review
    assert "Ticket plan" in captured.out
    # the plan JSON artifact is written and loadable
    assert plan_path.is_file()
    data = json.loads(plan_path.read_text())
    assert data["schema"] == "charon-intake-plan/1"
    # external id preserved through the CLI; the enriched item is runnable
    ids = [u["id"] for u in data["units"]]
    assert "ticket-42" in ids
    # the vague item never becomes a silent unit
    assert any("vague" in r["goal"].lower() or r["kind"] for r in data["review_items"]) \
        or any("vague" in i["message"].lower() for i in data["issues"])


def test_intake_import_default_out_path(tmp_path: Path, capsys) -> None:
    src = tmp_path / "backlog.md"
    src.write_text(_INTAKE_MD)
    rc = main(["intake", "import", str(src)])
    assert rc == 0
    assert (tmp_path / "backlog.plan.json").is_file()


def test_work_empty_plan_surfaces_review_reasons(tmp_path: Path, capsys) -> None:
    # CLIFF 2: a plan with only review_items must explain WHY nothing is runnable.
    plan = {
        "schema": "charon-intake-plan/1",
        "ready": False,
        "product_acceptance": "ok",
        "units": [],
        "review_items": [
            {"id": "ticket-9", "goal": "Do X", "kind": "missing-acceptance",
             "reason": "no executable acceptance check", "owned_paths": [],
             "tier": "sonnet", "propose_only": True},
        ],
        "issues": [],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    rc = main(["work", "--units", str(plan_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no loadable units" not in err  # not the dead-end message
    assert "ticket-9" in err and "accept" in err


# ------------------------------------------------- P5: outbound probe browser-UA


def test_probe_key_sends_shared_browser_ua() -> None:
    """P5: `charon` key probe must carry the shared browser-like UA so a Cloudflare-
    fronted provider (error 1010 → 403) does not wrongly report a valid key INVALID."""
    from unittest.mock import patch

    from charon.netutil import BROWSER_UA

    seen: list[str] = []

    class _Resp:
        status = 200

        def read(self, *_a):
            return b"{}"

    def _fake_open(req, timeout=None):
        seen.append(req.get_header("User-agent"))
        return _Resp()

    class Preset:
        base_url = "https://api.groq.com/openai/v1"

    # Every outbound send now goes through the shared key-egress choke point, so
    # that is the seam to patch (build_opener is banned outside netutil).
    with patch("charon.netutil.open_keyed", side_effect=_fake_open):
        cli_mod._do_probe(Preset.base_url, "sk-x")

    assert seen
    assert all(ua == BROWSER_UA for ua in seen)
    assert all(ua != "charon-proxy/0.1" for ua in seen)
    assert all(not (ua or "").lower().startswith("python-urllib") for ua in seen)


def test_provider_test_sends_shared_browser_ua() -> None:
    """P5: `charon providers test` base-resolve probe (GET /models, no creds) must
    carry the shared browser-like UA so a CF-fronted base is not wrongly failed."""
    from unittest.mock import patch

    from charon.netutil import BROWSER_UA

    seen: list[str] = []

    class _Resp:
        status = 200

        def read(self, *_a):
            return b"{}"

    def _fake_open(req, timeout=None):
        seen.append(req.get_header("User-agent"))
        return _Resp()

    with patch("charon.netutil.open_keyed", side_effect=_fake_open):
        cli_mod._provider_test("groq", "https://api.groq.com/openai/v1")

    assert seen
    assert all(ua == BROWSER_UA for ua in seen)
    assert all(ua != "charon-proxy/0.1" for ua in seen)
    assert all(not (ua or "").lower().startswith("python-urllib") for ua in seen)
