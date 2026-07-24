"""RED-proof for the gate-reentrancy guard.

THE CLASS: *a gate runs the test suite* AND *the test suite runs every gate*
=> unbounded recursion. Both halves are already true in this repo
(``tests/test_gate_contract.py`` spawns every declared ``tools/`` gate;
``charon.gate_runner.run_gate`` spawns every gate including ``pytest``), so the
cycle closes the moment any gate invokes pytest — a coverage, diff-coverage or
mutation gate would do exactly that. The guard is therefore preventive: it stops
a cycle that is one plausible gate away, not one that is running today.

HOW THESE TESTS ARE BOUNDED — this is a test *about* runaway recursion, so it
must be structurally incapable of causing one:

* No test here ever invokes the real pytest suite. The "suite" and the "gate" in
  the recursion tests are two ~12-line stdlib scripts written into ``tmp_path``.
* Those scripts carry their OWN hard depth cap (``_DEPTH_CAP``). With the guard
  fully removed the chain still stops after a handful of processes and prints
  ``DEPTH-CAP-REACHED``; it cannot fork-bomb the machine under any failure mode.
* The chain is strictly sequential — every parent blocks on its single child —
  so the process count is bounded by depth, never by branching.
* Every ``subprocess.run`` here passes an explicit finite ``timeout=``, so a
  hung child is killed rather than accumulated.
* Entry processes are launched with the marker STRIPPED from the environment, so
  these tests behave identically whether run bare or from inside ``charon gate``
  (which marks its pytest step).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.gate_contract import (  # noqa: E402
    GATE_ACTIVE_ENV,
    SUPPRESSED_PREFIX,
    child_env_marked_active,
    gate_run_is_nested,
    nested_suite_suppressed,
    suppress_nested_suite,
)

import test_gate_contract  # noqa: E402  (the pytest-side origin of the marker)
from charon import gate_runner  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"

#: Hard structural bound on the probe recursion. The probe scripts refuse to go
#: deeper than this REGARDLESS of the guard, which is what makes a revert-proof
#: run of these tests safe: worst case is _DEPTH_CAP nested processes.
_DEPTH_CAP = 3
#: Finite wall-clock bound on every probe process.
_PROBE_TIMEOUT = 60

_GATE_SCRIPT = '''\
import subprocess, sys
sys.path.insert(0, {tools!r})
from gate_contract import gate_run_is_nested, suppress_nested_suite

DEPTH = int(sys.argv[1])
print("GATE depth=" + str(DEPTH) + " nested=" + str(gate_run_is_nested()), flush=True)
if gate_run_is_nested():
    suppress_nested_suite("probe-gate")
    raise SystemExit(0)
if DEPTH >= {cap}:
    print("DEPTH-CAP-REACHED", flush=True)
    raise SystemExit(0)
proc = subprocess.run([sys.executable, {suite!r}, str(DEPTH + 1)],
                      capture_output=True, text=True, timeout={timeout})
sys.stdout.write(proc.stdout)
raise SystemExit(proc.returncode)
'''

_SUITE_SCRIPT = '''\
import subprocess, sys
sys.path.insert(0, {tools!r})
from gate_contract import child_env_marked_active

DEPTH = int(sys.argv[1])
print("SUITE depth=" + str(DEPTH), flush=True)
proc = subprocess.run([sys.executable, {gate!r}, str(DEPTH)],
                      capture_output=True, text=True, timeout={timeout},
                      env=child_env_marked_active())
sys.stdout.write(proc.stdout)
raise SystemExit(proc.returncode)
'''


def _unmarked_env() -> dict[str, str]:
    """The ambient environment with the marker removed.

    Entry points into the probe must start UNNESTED even when this suite is
    itself running as ``charon gate``'s pytest step (which marks it).
    """
    return {k: v for k, v in os.environ.items() if k != GATE_ACTIVE_ENV}


def _write_probe_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Write the two-script stand-in for the gate<->suite cycle."""
    gate = tmp_path / "probe_gate.py"
    suite = tmp_path / "probe_suite.py"
    gate.write_text(_GATE_SCRIPT.format(
        tools=str(TOOLS_DIR), suite=str(suite), cap=_DEPTH_CAP,
        timeout=_PROBE_TIMEOUT))
    suite.write_text(_SUITE_SCRIPT.format(
        tools=str(TOOLS_DIR), gate=str(gate), timeout=_PROBE_TIMEOUT))
    return gate, suite


def _run_probe(entry: Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run([sys.executable, str(entry), "0"], capture_output=True,
                          text=True, timeout=_PROBE_TIMEOUT, env=_unmarked_env())
    assert proc.returncode == 0, f"probe failed: {proc.stderr}"
    return proc


def _lines_starting(stdout: str, prefix: str) -> list[str]:
    return [ln for ln in stdout.splitlines() if ln.startswith(prefix)]


# --------------------------------------------------------------------------
# The marker itself
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "nested"),
    [("1", True), ("yes", True), ("0", True), ("", False), ("   ", False)],
    ids=["one", "yes", "zero-is-still-set", "empty", "whitespace"],
)
def test_marker_values_that_do_and_do_not_read_as_nested(value: str,
                                                         nested: bool) -> None:
    """Presence, not truthiness, is the signal — a marker is only ever set by a
    run that really is in flight. Blank reads as unset so a stray
    ``export CHARON_GATE_ACTIVE=`` cannot half-arm the guard."""
    assert gate_run_is_nested({GATE_ACTIVE_ENV: value}) is nested


def test_an_environment_without_the_marker_is_not_nested() -> None:
    """The control: without this, every assertion above would also hold for a
    guard that reported "nested" unconditionally."""
    assert gate_run_is_nested({}) is False


def test_child_env_marks_the_child_without_mutating_the_parent() -> None:
    """The marker travels DOWN a spawn chain only. Mutating os.environ would
    mark siblings that never spawned anything."""
    before = os.environ.get(GATE_ACTIVE_ENV)
    child = child_env_marked_active({"PATH": "/nonexistent"})
    assert child[GATE_ACTIVE_ENV] == "1"
    assert child["PATH"] == "/nonexistent"
    assert os.environ.get(GATE_ACTIVE_ENV) == before


def test_suppression_is_loud_and_greppable(capsys: pytest.CaptureFixture[str]) -> None:
    """A silent skip IS a fake-green. Suppression must name the gate, the guard
    and where the contract lives, on stdout where the gate's output is read."""
    suppress_nested_suite("probe-gate")
    out = capsys.readouterr().out
    assert SUPPRESSED_PREFIX in out
    assert "probe-gate" in out and GATE_ACTIVE_ENV in out
    assert "tools/gate_contract.py" in out
    assert nested_suite_suppressed(out)


def test_ordinary_gate_output_is_not_read_as_suppression() -> None:
    """The control for the parser: a gate that really did nothing must not be
    able to look suppressed."""
    assert nested_suite_suppressed("WORK-UNITS: 0\nall clear\n") is False


# --------------------------------------------------------------------------
# The two places the marker originates
# --------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, stdout: str) -> None:
        self.returncode = 0
        self.stdout = stdout
        self.stderr = ""


def _record_runs(monkeypatch, outputs: dict[str, str]) -> list[tuple[list[str], dict | None]]:
    """Replace gate_runner's subprocess.run with a recorder. NO child process is
    started, so this half of the proof cannot recurse at all."""
    seen: list[tuple[list[str], dict | None]] = []

    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        seen.append((list(cmd), kwargs.get("env")))
        return _FakeResult(outputs.get(cmd[-1], "WORK-UNITS: 99999"))

    monkeypatch.setattr(gate_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(gate_runner, "_verify_gate_registry_wired", lambda: 0)
    return seen


_PYTEST_CHECK = (["python3", "-m", "pytest", "-q"], "pytest")
_TOOL_CHECK = (["python3", "tools/check_boundary.py", "src"], "host-boundary")


def test_run_gate_marks_the_test_suite_spawn_and_only_that(monkeypatch) -> None:
    """The runner-side origin. Reverting the marking here reopens the cycle from
    the ``charon gate`` entry point; marking EVERY check instead would let a
    stray marker hollow out a suite-running gate at the top level."""
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.delenv(GATE_ACTIVE_ENV, raising=False)
    monkeypatch.setattr(gate_runner, "CHECKS", [_PYTEST_CHECK, _TOOL_CHECK])
    seen = _record_runs(monkeypatch, {"-q": "1500 passed"})

    assert gate_runner.run_gate() == 0
    assert len(seen) == 2, f"expected both checks to run, saw {seen}"
    envs = {tuple(cmd): env for cmd, env in seen}
    suite_env = envs[tuple(_PYTEST_CHECK[0])]
    assert suite_env is not None and suite_env[GATE_ACTIVE_ENV] == "1"
    tool_env = envs[tuple(_TOOL_CHECK[0])]
    assert tool_env is None or GATE_ACTIVE_ENV not in tool_env


def test_the_suite_spawns_declared_gates_marked_as_nested(monkeypatch) -> None:
    """The pytest-side origin: tests/test_gate_contract.py runs every declared
    gate, so the gates it spawns must see that a suite is already in flight.
    Verified by EXECUTION — one short-lived child, no suite, explicit timeout."""
    monkeypatch.delenv(GATE_ACTIVE_ENV, raising=False)
    env = test_gate_contract.gate_subprocess_env()
    assert env[GATE_ACTIVE_ENV] == "1"
    probe = (f"import sys; sys.path.insert(0, {str(TOOLS_DIR)!r});"
             "from gate_contract import gate_run_is_nested;"
             "print(gate_run_is_nested())")
    proc = subprocess.run([sys.executable, "-c", probe], env=env, timeout=30,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "True"


def test_the_runner_and_the_contract_name_the_same_marker() -> None:
    """gate_runner duplicates the name rather than importing tools/ (src must not
    depend on the repo's tooling). Duplication rots silently; this pins it."""
    from tools import gate_contract

    assert gate_runner.GATE_ACTIVE_ENV == gate_contract.GATE_ACTIVE_ENV


# --------------------------------------------------------------------------
# The guard is not a "disable the gates" switch
# --------------------------------------------------------------------------

def test_a_stray_marker_does_not_skip_any_check(monkeypatch) -> None:
    """A guard that made a marked environment skip gates would be a bigger
    fake-green than the recursion it prevents: one exported variable in CI would
    turn the whole gate suite into a silent pass."""
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv(GATE_ACTIVE_ENV, "1")
    monkeypatch.setattr(gate_runner, "CHECKS", [_PYTEST_CHECK, _TOOL_CHECK])
    seen = _record_runs(monkeypatch, {"-q": "1500 passed"})

    assert gate_runner.run_gate() == 0
    assert [cmd for cmd, _ in seen] == [_PYTEST_CHECK[0], _TOOL_CHECK[0]]


def test_a_stray_marker_does_not_make_a_failing_check_pass(monkeypatch) -> None:
    """Same property from the other side: under the marker, a RED check is still
    RED. Suppression is never a pass."""
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv(GATE_ACTIVE_ENV, "1")
    monkeypatch.setattr(gate_runner, "CHECKS", [_TOOL_CHECK])
    monkeypatch.setattr(gate_runner, "_verify_gate_registry_wired", lambda: 0)

    def failing_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        result = _FakeResult("")
        result.returncode = 7
        return result

    monkeypatch.setattr(gate_runner.subprocess, "run", failing_run)
    assert gate_runner.run_gate() == 7


# --------------------------------------------------------------------------
# The cycle itself, executed under a hard depth cap
# --------------------------------------------------------------------------

def test_a_gate_outside_a_gate_run_really_does_spawn_a_suite(tmp_path: Path) -> None:
    """The control that keeps the test below honest: the probe gate genuinely
    tries to run a suite when it is NOT nested. Without this, "no recursion"
    could just mean "the probe never does anything"."""
    gate, _suite = _write_probe_pair(tmp_path)
    proc = _run_probe(gate)

    gates = _lines_starting(proc.stdout, "GATE depth=")
    suites = _lines_starting(proc.stdout, "SUITE depth=")
    assert gates, f"probe gate never ran: {proc.stdout!r}"
    assert gates[0] == "GATE depth=0 nested=False"
    assert suites == ["SUITE depth=1"], f"expected exactly one spawned suite: {suites}"


def test_the_guard_stops_the_cycle_at_the_first_nested_suite(tmp_path: Path) -> None:
    """Enter at the SUITE, as pytest does. It spawns the gate marked as nested;
    the gate must then decline to spawn a second suite and say so.

    Revert the guard and this fails: the gate spawns another suite, which spawns
    another gate, until the probe's own _DEPTH_CAP stops it — several SUITE
    lines instead of one."""
    _gate, suite = _write_probe_pair(tmp_path)
    proc = _run_probe(suite)

    gates = _lines_starting(proc.stdout, "GATE depth=")
    suites = _lines_starting(proc.stdout, "SUITE depth=")
    assert gates and suites, f"probe produced nothing: {proc.stdout!r}"
    assert suites == ["SUITE depth=0"], (
        f"the gate<->suite cycle re-entered: {suites} (cap {_DEPTH_CAP})")
    assert gates == ["GATE depth=0 nested=True"]
    assert nested_suite_suppressed(proc.stdout)
    assert "DEPTH-CAP-REACHED" not in proc.stdout, (
        "the probe was stopped by its own safety cap, not by the guard")
