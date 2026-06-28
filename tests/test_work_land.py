"""WORK-LAND-PR — close the work loop (open a PR behind a flag) + wire the real
reviewer into the work path.

Two behaviors are pinned here:
  (a) ``run_work(..., open_pr=True)`` turns each PROPOSED unit into a DRAFT PR
      (branch + push + ``gh pr create --draft``) and NEVER merges; with the flag
      OFF the work path stays read-only (no push, no PR) — exactly as before.
  (b) the work path threads the REAL ``GatewayReviewer`` (not the demo
      ``MockReviewer``) into the fenced runner.
"""
from __future__ import annotations

import json
from pathlib import Path

from charon import cli, land
from charon.land import GateOutcome


# ----------------------------------------------------------------- propose_pr seam
class _DummyLedger:
    task_id = "unit-x"
    goal = "do the x work"
    target_repo = "/tmp/repo-x"
    lkg_ref = "deadbeefcafef00d"
    base_ref = "0000baseref0000"


def _propose_outcome() -> GateOutcome:
    return GateOutcome(
        task_id="unit-x", goal="do the x work", decision="propose",
        base_ref="0000baseref0000", tip_ref="deadbeefcafef00d",
        changed_files=["src/x.py"],
    )


def test_propose_pr_branches_pushes_and_opens_draft_pr_never_merges() -> None:
    """A PROPOSE verdict → branch at the tip, push, then a DRAFT PR. The ONLY git
    writes are the branch + push (no merge anywhere), and the PR is a draft."""
    git_calls: list[tuple] = []
    pr_argv: list[list[str]] = []

    def git_spy(repo: str, *args: str) -> str:
        git_calls.append((repo, *args))
        return ""

    def pr_spy(argv: list[str]) -> str:
        pr_argv.append(argv)
        return "https://example.test/pull/7"

    url = land.propose_pr(
        _DummyLedger(), _propose_outcome(),
        git_runner=git_spy, pr_runner=pr_spy,
    )

    assert url == "https://example.test/pull/7"
    # branch at the blessed tip, then publish it — in that order.
    assert git_calls[0] == (
        "/tmp/repo-x", "branch", "-f", "charon/land/unit-x", "deadbeefcafef00d"
    )
    assert git_calls[1] == (
        "/tmp/repo-x", "push", "-u", "origin", "charon/land/unit-x"
    )
    # the PR command is a DRAFT create — never a merge.
    assert len(pr_argv) == 1
    argv = pr_argv[0]
    assert argv[:3] == ["gh", "pr", "create"]
    assert "--draft" in argv
    assert "merge" not in argv
    # propose-default: no git mutation ever issues a merge/push-to-base.
    assert not any("merge" in str(c) for c in git_calls)


def test_propose_pr_refuses_a_held_unit() -> None:
    """A held unit must never reach a PR (fail-closed)."""
    held = GateOutcome(
        task_id="unit-x", goal="g", decision="hold", holds=["nope"],
        tip_ref="abc",
    )
    called = False

    def git_spy(repo: str, *args: str) -> str:
        nonlocal called
        called = True
        return ""

    try:
        land.propose_pr(_DummyLedger(), held, git_runner=git_spy,
                        pr_runner=lambda a: "x")
    except land.LandError:
        pass
    else:  # pragma: no cover - the call must raise
        raise AssertionError("expected LandError for a held unit")
    assert called is False  # no branch/push attempted for a held unit


# --------------------------------------------------------------- run_work flag
def _units_file(tmp_path: Path) -> str:
    units = tmp_path / "units.json"
    units.write_text(json.dumps([
        {"goal": "make a", "accept": ["test -f a.txt"], "owned_paths": ["a.txt"]},
    ]), encoding="utf-8")
    return str(units)


def test_run_work_open_pr_flag_on_proposes_each_unit(tmp_path: Path) -> None:
    """With ``open_pr=True`` a PROPOSED unit is handed to the PR seam and its URL
    is reported; the unit never merges (the seam is the only PR path)."""
    proposed: list[str] = []

    def pr_spy(ledger, outcome, *, base="master", repo_slug=None):  # type: ignore[no-untyped-def]
        assert outcome.decision == "propose"
        proposed.append(ledger.task_id)
        return f"https://example.test/pull/{ledger.task_id}"

    out = cli.run_work(
        _units_file(tmp_path), state_dir=str(tmp_path / "state"),
        backend_name="mock", open_pr=True, pr_opener=pr_spy,
    )

    assert out["open_pr"] is True
    done = [u for u in out["units"] if u["land"]
            and u["land"]["decision"] == "propose"]
    assert done, out["units"]
    assert proposed == [u["unit_id"] for u in done]
    for u in done:
        assert u["pr"] == f"https://example.test/pull/{u['unit_id']}"


def test_run_work_flag_off_stays_read_only(tmp_path: Path) -> None:
    """Default (flag OFF): the PR seam is NEVER invoked and no ``pr`` is set —
    the work path is read-only, exactly as before."""
    called: list[str] = []

    def pr_spy(*a, **k):  # type: ignore[no-untyped-def]
        called.append("x")
        return "nope"

    out = cli.run_work(
        _units_file(tmp_path), state_dir=str(tmp_path / "state"),
        backend_name="mock", pr_opener=pr_spy,  # open_pr defaults to False
    )

    assert out["open_pr"] is False
    assert called == []  # never opened a PR
    assert all(u["pr"] is None for u in out["units"])


# ----------------------------------------------------------------- real reviewer
def test_work_runner_threads_the_gateway_reviewer() -> None:
    """The work path wires the REAL ``GatewayReviewer`` into the fenced runner —
    not the demo ``MockReviewer``."""
    from charon.adapters.review import GatewayReviewer
    from charon.adapters.review_mock import MockReviewer

    runner = cli.build_work_runner(
        "/tmp/state", lambda unit, checks: {}, "L1",
    )
    assert isinstance(runner.reviewer, GatewayReviewer)
    assert not isinstance(runner.reviewer, MockReviewer)


def test_build_work_runner_preserves_autonomy_and_reviewer(tmp_path: Path) -> None:
    """``build_work_runner`` (the builder ``run_work`` calls) threads a real
    ``GatewayReviewer`` and carries the requested autonomy through to the fenced
    runner — so the reviewer reaches ``coordinator.run`` at L2+."""
    from charon.adapters.review import GatewayReviewer

    runner = cli.build_work_runner("/tmp/state", lambda u, c: {}, "L2")
    assert isinstance(runner.reviewer, GatewayReviewer)
    assert runner.autonomy == "L2"
