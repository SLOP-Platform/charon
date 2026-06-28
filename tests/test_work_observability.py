"""WORK-OBSERVABILITY — make a `charon work` run visible while it runs.

Two sub-goals are pinned here:
  (1) LIVE per-unit progress: as the scheduler drains, it emits human-readable
      lifecycle lines (claimed / started / checkpoint N (verified …) / done|
      blocked|retry) to an opt-in sink the CLI routes to STDERR — stdout stays
      the final machine-readable JSON. The sink is gated: ON for a TTY, OFF when
      stdout is redirected or `--quiet`.
  (2) AGGREGATE run view: `charon runs` rolls up a WHOLE multi-unit run's
      statuses from the durable `.charon` state (board + per-unit ledgers), which
      the per-unit `charon ledger <id>` cannot give.

No secret/token strings ever appear in any emitted line.
"""
from __future__ import annotations

import json
from pathlib import Path

from charon import cli
from charon.acceptance import AcceptanceCheck
from charon.coordinator import RunResult
from charon.engine.board import BLOCKED, DONE, READY, Board, Unit
from charon.engine.scheduler import Scheduler
from charon.ledger import Checkpoint, Ledger


# --------------------------------------------------------------------- helpers
def _board(tmp_path: Path, units: list[Unit]) -> Board:
    b = Board.create(tmp_path / "board.json")
    for u in units:
        b.add(u)
    return b


def _claims(tmp_path: Path) -> Path:
    d = tmp_path / "claims"
    d.mkdir(exist_ok=True)
    return d


def _wt_factory(tmp_path: Path):
    def make(unit: Unit) -> str:
        p = tmp_path / "wt" / unit.id
        p.mkdir(parents=True, exist_ok=True)
        return str(p)

    return make


class _FixedRunner:
    """A fake FencedRunner that returns a fixed RunResult — lets the scheduler's
    progress emission be asserted with no live agent."""

    def __init__(self, status: str = "complete", *, checkpoints: int = 2,
                 verified: list[str] | None = None) -> None:
        self._res = RunResult(
            status=status, checkpoints=checkpoints,
            verified=verified if verified is not None else ["a0", "a1"],
        )

    def __call__(self, unit: Unit, worktree: str, *, cost_gate) -> RunResult:
        return self._res


# --------------------------------------------------- (1) live scheduler progress
def test_scheduler_emits_lifecycle_lines_to_sink(tmp_path: Path) -> None:
    """A drained unit emits claimed → started → checkpoint N (verified …) → done,
    in that order, to the injected progress sink."""
    lines: list[str] = []
    board = _board(tmp_path, [Unit(id="u1", tier="opus", owns=["a.py"],
                                   goal="g", accept=["true"])])
    sched = Scheduler(
        board, _claims(tmp_path), _FixedRunner("complete", checkpoints=3,
                                               verified=["a0", "a1"]),
        worktree_factory=_wt_factory(tmp_path), progress=lines.append,
    )
    sched.drain()

    assert lines == [
        "u1: claimed",
        "u1: started",
        "u1: checkpoint 3 (verified a0, a1)",
        "u1: done",
    ]


def test_scheduler_silent_without_sink(tmp_path: Path) -> None:
    """No sink wired (the `--quiet` / redirected-stdout path) → no emission, and
    the drain still completes normally."""
    board = _board(tmp_path, [Unit(id="u1", tier="opus", owns=["a.py"],
                                   goal="g", accept=["true"])])
    sched = Scheduler(
        board, _claims(tmp_path), _FixedRunner("complete"),
        worktree_factory=_wt_factory(tmp_path),  # progress defaults to None
    )
    res = sched.drain()  # must not raise
    assert board.get("u1").state == DONE
    assert [r.status for r in res.results] == ["complete"]


def test_scheduler_blocked_unit_emits_blocked(tmp_path: Path) -> None:
    """A terminal non-complete status emits the matching disposition word."""
    lines: list[str] = []
    board = _board(tmp_path, [Unit(id="u1", tier="opus", owns=["a.py"],
                                   goal="g", accept=["true"])])
    sched = Scheduler(
        board, _claims(tmp_path), _FixedRunner("escaped", checkpoints=1,
                                               verified=[]),
        worktree_factory=_wt_factory(tmp_path), progress=lines.append,
    )
    sched.drain()

    assert "u1: blocked" in lines
    assert "u1: checkpoint 1 (verified none)" in lines


def test_scheduler_no_checkpoint_line_when_zero(tmp_path: Path) -> None:
    """A run with zero checkpoints (e.g. an error before any dispatch) emits no
    checkpoint line — just the terminal disposition."""
    lines: list[str] = []
    board = _board(tmp_path, [Unit(id="u1", tier="opus", owns=["a.py"],
                                   goal="g", accept=["true"])])
    sched = Scheduler(
        board, _claims(tmp_path), _FixedRunner("error", checkpoints=0,
                                               verified=[]),
        worktree_factory=_wt_factory(tmp_path), progress=lines.append,
    )
    sched.drain()

    assert not any("checkpoint" in ln for ln in lines)
    assert "u1: retry" in lines  # "error" is retryable


def test_no_secret_strings_in_emitted_lines(tmp_path: Path) -> None:
    """Emitted lines are built from ids + check ids + status words only — never
    the note, env, or a credential."""
    lines: list[str] = []
    board = _board(tmp_path, [Unit(id="u1", tier="opus", owns=["a.py"],
                                   goal="g", accept=["true"])])
    sched = Scheduler(
        board, _claims(tmp_path), _FixedRunner("complete"),
        worktree_factory=_wt_factory(tmp_path), progress=lines.append,
    )
    sched.drain()

    blob = "\n".join(lines)
    for bad in ("sk-", "Bearer ", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "token"):
        assert bad not in blob


# --------------------------------------------------------- (1) the gating policy
def test_progress_enabled_explicit_flag_wins() -> None:
    # --progress forces ON even when stdout is piped; --quiet forces OFF on a TTY.
    assert cli._progress_enabled(True, stdout_isatty=False) is True
    assert cli._progress_enabled(False, stdout_isatty=True) is False


def test_progress_enabled_auto_follows_tty() -> None:
    # neither flag → ON for a TTY, OFF when stdout is redirected/piped.
    assert cli._progress_enabled(None, stdout_isatty=True) is True
    assert cli._progress_enabled(None, stdout_isatty=False) is False


def test_progress_sink_writes_to_stderr_only(capsys) -> None:
    """The sink writes `[work] …` to STDERR, leaving stdout clean for the JSON."""
    sink = cli._progress_sink()
    sink("u1: claimed")
    cap = capsys.readouterr()
    assert cap.out == ""  # stdout stays machine-readable
    assert "[work] u1: claimed" in cap.err


# -------------------------------------------------- (1) end-to-end through run_work
def test_run_work_streams_progress_and_keeps_json(tmp_path: Path) -> None:
    """`run_work` with a progress sink emits the lifecycle lines (incl. the land
    decision) AND still returns the unchanged final report dict."""
    lines: list[str] = []
    units = tmp_path / "units.json"
    units.write_text(json.dumps([
        {"goal": "make a", "accept": ["test -f a.txt"], "owned_paths": ["a.txt"]},
    ]), encoding="utf-8")

    out = cli.run_work(
        str(units), state_dir=str(tmp_path / "state"),
        backend_name="mock", progress=lines.append,
    )

    # stdout report is the same machine-readable shape (a dict with the run keys).
    assert set(out) >= {"units", "validation", "rounds", "board_path"}
    # the live view shows the unit moving through its lifecycle + a land verdict.
    blob = "\n".join(lines)
    assert any(ln.endswith(": claimed") for ln in lines)
    assert any(ln.endswith(": started") for ln in lines)
    assert any(ln.endswith(": done") for ln in lines)
    assert "land:" in blob


def test_run_work_silent_when_no_progress(tmp_path: Path) -> None:
    """Default (no sink): run_work returns the same report and emits nothing."""
    units = tmp_path / "units.json"
    units.write_text(json.dumps([
        {"goal": "make a", "accept": ["test -f a.txt"], "owned_paths": ["a.txt"]},
    ]), encoding="utf-8")

    out = cli.run_work(
        str(units), state_dir=str(tmp_path / "state"), backend_name="mock",
    )
    assert "units" in out and "validation" in out


# ------------------------------------------------------ (2) aggregate run view
def _seed_run(tmp_path: Path) -> Path:
    """Build a durable multi-unit run (board + per-unit ledgers) in `.charon`."""
    sdir = tmp_path / "state"
    sdir.mkdir()
    board = Board.create(sdir / "work-board.json")
    board.add(Unit(id="alpha", tier="opus", owns=["a.py"], goal="g-a",
                   accept=["true"]))
    board.add(Unit(id="beta", tier="haiku", owns=["b.py"],
                   depends_on=["alpha"], goal="g-b", accept=["true"]))
    board.add(Unit(id="gamma", tier="opus", owns=["c.py"], goal="g-c",
                   accept=["true"]))
    board.mark_claimed("alpha")
    board.mark_done("alpha")
    board.mark_claimed("gamma")
    board.mark_blocked("gamma")
    # beta is left READY (its dep is done but it never ran) — no ledger for it.

    led = Ledger.create(sdir, "alpha", "g-a",
                        [AcceptanceCheck(id="a0", cmd="true")], str(tmp_path),
                        "base000")
    led.append_checkpoint(Checkpoint(seq=1, provider="mock", commit="c0",
                                     verified=[], remaining=["a0"]))
    led.append_checkpoint(Checkpoint(seq=2, provider="mock", commit="c1",
                                     verified=["a0"], remaining=[]))
    Ledger.create(sdir, "gamma", "g-c",
                  [AcceptanceCheck(id="a0", cmd="true")], str(tmp_path), "base000")
    return sdir


def test_run_status_rolls_up_whole_run(tmp_path: Path) -> None:
    """`run_status` summarises EVERY unit's board state + durable ledger view."""
    sdir = _seed_run(tmp_path)
    out = cli.run_status(state_dir=str(sdir))

    by_id = {u["unit_id"]: u for u in out["units"]}
    assert set(by_id) == {"alpha", "beta", "gamma"}
    assert by_id["alpha"]["state"] == DONE
    assert by_id["gamma"]["state"] == BLOCKED
    assert by_id["beta"]["state"] == READY
    # the rolled-up verdict comes from the LAST durable checkpoint (no re-run).
    assert by_id["alpha"]["checkpoints"] == 2
    assert by_id["alpha"]["verified"] == ["a0"]
    assert by_id["alpha"]["remaining"] == []
    # a unit that never ran still appears, with empty ledger fields.
    assert by_id["beta"]["checkpoints"] == 0
    assert by_id["beta"]["depends_on"] == ["alpha"]
    # totals roll up the board states.
    assert out["totals"] == {DONE: 1, BLOCKED: 1, READY: 1}


def test_run_status_no_run_is_loud(tmp_path: Path) -> None:
    """No board on disk → a clear error, not a crash."""
    try:
        cli.run_status(state_dir=str(tmp_path / "empty"))
    except FileNotFoundError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected FileNotFoundError when no run exists")


def test_runs_command_prints_json(tmp_path: Path, capsys) -> None:
    """`charon runs` prints the rollup as JSON to stdout and exits 0."""
    sdir = _seed_run(tmp_path)
    parser = cli.build_parser()
    args = parser.parse_args(["runs", "--state-dir", str(sdir)])
    rc = args.func(args)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert {u["unit_id"] for u in out["units"]} == {"alpha", "beta", "gamma"}
