"""RED-proof for the two class-level gate defects behind six false-green rounds.

These are NOT tests of the key-egress vulnerability. They pin the two mechanisms
that let six consecutive rounds report "all checks passed" for work that never
happened, and both are general — they would catch the same shape in any future
gate:

* ZERO WORK UNITS — a gate examined nothing and exited 0. Round 6's Semgrep gate
  scanned 0 files and printed "key-egress OK". Its own test asserted the buggy
  constant *as a requirement*, so fixing the gate broke the test. These tests
  therefore assert on COUNTS and RUNNER BEHAVIOUR, never on any gate's source
  text.
* SPLIT-BRAIN — the check LIST came from the installed module (the main checkout)
  while the check SCRIPTS were shelled CWD-relative from a worktree, so a gate
  added on a branch silently never ran.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.gate_contract import parse_work_units  # noqa: E402

from charon import gate_runner  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# The contract's own parsing
# --------------------------------------------------------------------------

def test_parse_work_units_reads_the_reported_count() -> None:
    assert parse_work_units("scanning...\nWORK-UNITS: 127\nOK") == 127


def test_parse_work_units_returns_none_when_the_gate_never_reported() -> None:
    """None and 0 must stay distinguishable. "examined nothing" and "did not say"
    are different diagnoses, and only the second can also mean "was never wired"."""
    assert parse_work_units("everything is fine!\n") is None
    assert parse_work_units("WORK-UNITS: 0\n") == 0


def test_parse_work_units_takes_the_last_report() -> None:
    assert parse_work_units("WORK-UNITS: 3\nWORK-UNITS: 99\n") == 99


# --------------------------------------------------------------------------
# Every declared gate actually emits a count, and clears its own minimum
# --------------------------------------------------------------------------

def _declared_gates() -> list[dict]:
    gates = json.loads((REPO_ROOT / "tools" / "gates.json").read_text())
    return [g for g in gates if isinstance(g, dict) and "min_work_units" in g]


def test_every_ci_step_tool_gate_declares_a_minimum() -> None:
    """The ratchet. A gate added later must not be able to opt out of the
    contract silently — that is precisely how the inert gate shipped green."""
    gates = json.loads((REPO_ROOT / "tools" / "gates.json").read_text())
    undeclared = [
        g.get("id")
        for g in gates
        if isinstance(g, dict)
        and g.get("ci_step")
        and any(p.startswith("tools/") for p in str(g.get("enforcer", "")).split())
        and "min_work_units" not in g
    ]
    assert not undeclared, f"gates missing min_work_units: {undeclared}"


def _registry_exit(mutate, monkeypatch, tmp_path) -> int:
    """Run the REAL registry checker against the REAL manifest, mutated.

    Mutating the real manifest rather than synthesising a one-gate one keeps the
    checker's other rules (domain registration, @covers reconciliation) satisfied,
    so a failure here can only be the work-unit contract.
    """
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from tools import check_gate_registry as cgr

    gates = json.loads((REPO_ROOT / "tools" / "gates.json").read_text())
    mutate(gates)
    manifest = tmp_path / "gates.json"
    manifest.write_text(json.dumps(gates))
    monkeypatch.setattr(cgr, "GATES_PATH", manifest)
    return cgr.validate()


def _find(gates: list[dict], gid: str) -> dict:
    return next(g for g in gates if g.get("id") == gid)


def test_registry_accepts_the_manifest_as_shipped(monkeypatch, tmp_path) -> None:
    """Control. Without this, the three tests below could be failing for reasons
    that have nothing to do with the work-unit contract."""
    assert _registry_exit(lambda gates: None, monkeypatch, tmp_path) == 0


def test_registry_rejects_a_ci_step_gate_that_declares_no_minimum(
        monkeypatch, tmp_path) -> None:
    """The ratchet, RED-proofed. Revert the check in check_gate_registry and this
    goes GREEN — at which point a future gate can ship with no work-unit contract
    at all, which is how an inert gate came to look identical to a clean one."""
    def drop(gates: list[dict]) -> None:
        del _find(gates, "security-scan")["min_work_units"]
    assert _registry_exit(drop, monkeypatch, tmp_path) == 1


def test_registry_rejects_min_work_units_zero_without_a_written_reason(
        monkeypatch, tmp_path) -> None:
    """A declared 0 must be a decision on the record, not an omission."""
    def zero(gates: list[dict]) -> None:
        _find(gates, "security-scan")["min_work_units"] = 0
    assert _registry_exit(zero, monkeypatch, tmp_path) == 1

    def zero_with_note(gates: list[dict]) -> None:
        g = _find(gates, "security-scan")
        g["min_work_units"] = 0
        g["work_units_note"] = "examines nothing countable"
    assert _registry_exit(zero_with_note, monkeypatch, tmp_path) == 0


@pytest.mark.parametrize(
    "gate",
    [pytest.param(g, id=str(g.get("id"))) for g in _declared_gates()
     if any(p.startswith("tools/") for p in str(g.get("enforcer", "")).split())],
)
def test_declared_gate_emits_a_count_at_or_above_its_minimum(gate: dict) -> None:
    """Runs the real script and reads the real count. Asserting on the emitted
    NUMBER (not on the script's source) is the whole point: a gate that stops
    scanning fails this, and a gate that is fixed does not."""
    script = next(p for p in str(gate["enforcer"]).split() if p.startswith("tools/"))
    args = [sys.executable, script]
    if script.endswith("check_decisions.py"):
        args.append("--check")
    proc = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True)
    observed = parse_work_units(proc.stdout)
    assert observed is not None, (
        f"{gate['id']} exited {proc.returncode} without emitting WORK-UNITS — "
        "an unreported count is indistinguishable from a mis-invoked gate")
    assert observed >= gate["min_work_units"], (
        f"{gate['id']} examined {observed}, below its declared "
        f"minimum {gate['min_work_units']}")


# --------------------------------------------------------------------------
# The runner FAILS CLOSED — the half that six rounds actually needed
# --------------------------------------------------------------------------

def test_runner_fails_a_gate_that_exits_zero_without_reporting(monkeypatch,
                                                              capsys) -> None:
    """The C1 shape exactly: exit 0, cheerful message, nothing examined."""
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(gate_runner, "CHECKS", [
        ([sys.executable, "-c", "print('tools/check_boundary.py OK')"], "fake"),
    ])
    monkeypatch.setattr(gate_runner, "_check_key", lambda cmd: "tools/check_boundary.py")
    monkeypatch.setattr(gate_runner, "_verify_gate_registry_wired", lambda: 0)
    assert gate_runner.run_gate() == 1
    assert "ZERO-WORK-UNITS" in capsys.readouterr().err


def test_runner_fails_a_gate_that_reports_fewer_units_than_declared(monkeypatch,
                                                                    capsys) -> None:
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(gate_runner, "CHECKS", [
        ([sys.executable, "-c", "print('WORK-UNITS: 0')"], "fake"),
    ])
    monkeypatch.setattr(gate_runner, "_check_key", lambda cmd: "tools/check_boundary.py")
    monkeypatch.setattr(gate_runner, "_verify_gate_registry_wired", lambda: 0)
    assert gate_runner.run_gate() == 1
    err = capsys.readouterr().err
    assert "ZERO-WORK-UNITS" in err and "examined" in err


def test_runner_accepts_a_gate_that_clears_its_minimum(monkeypatch) -> None:
    """The control. Without this, the two tests above would also pass against a
    runner that failed everything unconditionally."""
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(gate_runner, "CHECKS", [
        ([sys.executable, "-c", "print('WORK-UNITS: 99999')"], "fake"),
    ])
    monkeypatch.setattr(gate_runner, "_check_key", lambda cmd: "tools/check_boundary.py")
    monkeypatch.setattr(gate_runner, "_verify_gate_registry_wired", lambda: 0)
    assert gate_runner.run_gate() == 0


def test_pytest_work_units_come_from_the_collected_count() -> None:
    """A pytest run that collects nothing must not read as a pass."""
    assert gate_runner._observed_work_units("pytest", "1899 passed, 3 skipped") == 1899
    assert gate_runner._observed_work_units("pytest", "no tests ran in 0.01s") is None


# --------------------------------------------------------------------------
# Split-brain: the check list and the check scripts must be one checkout
# --------------------------------------------------------------------------

def test_run_gate_refuses_when_the_module_and_cwd_are_different_checkouts(
        monkeypatch, tmp_path, capsys) -> None:
    """Reverting `_verify_same_tree` makes this GREEN again, which is the exact
    state in which several rounds were declared locally green having never
    invoked the gate they were adding."""
    monkeypatch.chdir(tmp_path)
    assert gate_runner.run_gate() == 1
    assert "GATE-SPLIT-BRAIN" in capsys.readouterr().err


def test_gates_json_resolves_from_cwd_not_from_the_installed_module(
        monkeypatch, tmp_path) -> None:
    """Anchoring the manifest on __file__ is what made the check list and the
    check scripts come from two different commits."""
    monkeypatch.chdir(tmp_path)
    assert gate_runner._gates_json_path() == tmp_path.resolve() / "tools" / "gates.json"


def test_repo_local_runner_anchors_on_itself_not_on_the_caller(tmp_path) -> None:
    """`tools/run_gate.py` is the structural fix: a script at <root>/tools/ cannot
    resolve to a checkout other than <root>. Invoked from an unrelated directory
    it must still target its OWN repo root — the property `charon gate` lacks.
    Verified without running the gate itself: this asserts where the runner
    points, not what the gate concludes."""
    runner = REPO_ROOT / "tools" / "run_gate.py"
    assert runner.is_file()
    probe = (
        "import runpy, sys, pathlib;"
        f"sys.argv=['run_gate'];"
        f"mod=runpy.run_path({str(runner)!r}, run_name='not_main');"
        "print(mod['REPO_ROOT'])"
    )
    proc = subprocess.run([sys.executable, "-c", probe], cwd=tmp_path,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert Path(proc.stdout.strip()) == REPO_ROOT


def test_cli_gate_prefers_the_repo_local_runner(monkeypatch, tmp_path) -> None:
    """`charon gate` must re-exec the CWD-local runner when there is one, so the
    console script cannot run one checkout's check list against another's files."""
    from charon import cli

    (tmp_path / "tools").mkdir()
    local = tmp_path / "tools" / "run_gate.py"
    local.write_text("raise SystemExit(0)\n")
    monkeypatch.chdir(tmp_path)

    calls: list[list[str]] = []

    class _R:
        returncode = 0

    def _fake_run(args, **kwargs):  # noqa: ANN001, ANN003
        calls.append(args)
        return _R()

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)
    assert cli._cmd_gate(None) == 0
    assert calls and calls[0][1] == str(local)
