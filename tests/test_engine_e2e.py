"""End-to-end proof of the OPT-IN native work-engine (ADR-0010 / E6).

A toy unit plan flows the WHOLE pipeline on a real (sandbox) repo with a mock ACP
backend:

    intake → board → claim → scheduler → fenced ``coordinator.run`` → propose-default
    land → top-level end-product validation.

Binding properties proven here (not against a stub):
  - ``depends_on`` waves run in order; disjoint units run CONCURRENTLY through the
    fence (a ``threading.Barrier`` only two units can clear together);
  - each unit is driven through the SINGLE fenced ``coordinator.run`` — an ESCAPE
    backend comes back ``escaped``, a verdict ONLY the fence escape-scan produces
    (so the scheduler is never a second, unfenced dispatch path — D008);
  - each DONE unit is run through the propose-default land gate (PR/diff reported,
    never auto-merged — D3);
  - the D12 validator runs ONCE on the integrated end-product against the TOP-LEVEL
    product acceptance captured by intake (ADR-0008), never silently passing.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from charon import cli, intake
from charon.adapters.mock import MockBackend, MockMode

# A 3-unit plan: unit-a and unit-c are disjoint (wave 0, may run concurrently);
# unit-b depends on unit-a (wave 1). The product acceptance names all three files.
_PLAN_MD = """\
# Unit A
files: a.txt
accept: `test -f a.txt`

# Unit C
files: c.txt
accept: `test -f c.txt`

# Unit B
files: b.txt
accept: `test -f b.txt`
depends_on: unit-a

## Product acceptance
The product is done when `test -f a.txt` and `test -f b.txt` and `test -f c.txt`.
"""

_SOLO_MD = """\
# Unit A
files: a.txt
accept: `test -f a.txt`

## Product acceptance
Done when `test -f a.txt`.
"""


def _plan_file(tmp_path: Path, md: str) -> str:
    """Run intake on ``md`` and emit the JSON ticket-plan artifact run_work loads."""
    plan = intake.intake(md)
    assert plan.ready, plan.to_dict()  # a sane, loadable plan with top-level acceptance
    out = tmp_path / "plan.json"
    plan.write(out)
    return str(out)


# --------------------------------------------------------------- the happy path
def test_engine_e2e_happy_path(tmp_path: Path) -> None:
    """The full pipeline: intake plan → board → scheduler (fenced) → land →
    validate. All units complete; the validator passes on the integrated result."""
    plan = _plan_file(tmp_path, _PLAN_MD)
    out = cli.run_work(plan, state_dir=str(tmp_path / "state"), backend_name="mock")

    statuses = {u["unit_id"]: u["status"] for u in out["units"]}
    assert statuses == {
        "unit-a": "complete", "unit-b": "complete", "unit-c": "complete"
    }
    assert all(u["board_state"] == "done" for u in out["units"])
    assert out["rounds"] >= 2  # the dependent ran in a later wave than its dep

    # propose-default land per unit: each proposes, and its diff names its owned file.
    for u in out["units"]:
        land = u["land"]
        assert land is not None
        assert land["decision"] == "propose", land
        owned = f"{u['unit_id'][-1]}.txt"  # unit-a→a.txt, …
        assert owned in land["changed_files"]

    # the D12 validator ran ONCE on the integrated end-product and passed against the
    # top-level acceptance (all three files present in the assembled worktree).
    assert out["validation"]["passed"] is True
    assert sorted(out["validation"]["verified"]) == ["p0", "p1", "p2"]
    assert out["validation"]["fix_proposal"] == ""
    assert out["auto_land"] is False  # propose-default; never auto-merges


# ------------------------------------------------- disjoint units, concurrently
def test_engine_e2e_disjoint_units_run_concurrently(tmp_path: Path) -> None:
    """The two wave-0 disjoint units are inside the fence at the SAME time — proven
    by a barrier of 2 that only clears if both run concurrently. The dependent runs
    in a later wave, so it is never one of the two parties (no deadlock)."""
    plan = _plan_file(tmp_path, _PLAN_MD)
    barrier = threading.Barrier(2)
    arrivals: list[str] = []
    lock = threading.Lock()

    class BarrierBackend:
        """Delegates to a satisfying mock but, for the gated wave-0 units, blocks on
        a shared barrier inside ``dispatch`` (i.e. inside ``coordinator.run``) until
        BOTH have arrived — observable concurrency THROUGH the fence."""

        name = "mock"

        def __init__(self, inner: MockBackend, gated: bool) -> None:
            self._inner = inner
            self._gated = gated

        def dispatch(self, *a: object, **k: object):  # type: ignore[no-untyped-def]
            if self._gated:
                try:
                    barrier.wait(timeout=5)
                    with lock:
                        arrivals.append("in")
                except threading.BrokenBarrierError:
                    pass
            return self._inner.dispatch(*a, **k)  # type: ignore[arg-type]

        def health(self):  # type: ignore[no-untyped-def]
            return self._inner.health()

        def capabilities(self):  # type: ignore[no-untyped-def]
            return self._inner.capabilities()

        def kill(self) -> None:
            self._inner.kill()

    def factory(unit, checks):  # type: ignore[no-untyped-def]
        inner = MockBackend.satisfying(checks)
        return {"mock": BarrierBackend(inner, unit.id in ("unit-a", "unit-c"))}

    out = cli.run_work(
        plan, state_dir=str(tmp_path / "state"), backend_factory=factory,
        engine_overrides={"max_parallel": 3, "default_cap": 3},
    )

    assert len(arrivals) == 2  # barrier(2) cleared → both wave-0 units truly concurrent
    assert all(u["status"] == "complete" for u in out["units"])
    assert out["validation"]["passed"] is True


# ------------------------------------------ the unit goes THROUGH the fence (D008)
def test_engine_e2e_drives_the_fenced_coordinator_path(tmp_path: Path) -> None:
    """An ESCAPE backend yields ``escaped`` — a status ONLY the fence escape-scan in
    ``coordinator.run`` produces. Proves the scheduler drove the unit through the
    fenced path, not a raw dispatch. The escaped unit is BLOCKED and never landed;
    the validator still runs once and HOLDS (never silently passes)."""
    plan = _plan_file(tmp_path, _SOLO_MD)

    def factory(unit, checks):  # type: ignore[no-untyped-def]
        return {"mock": MockBackend(mode=MockMode.ESCAPE)}

    out = cli.run_work(
        plan, state_dir=str(tmp_path / "state"), backend_factory=factory,
    )

    u = out["units"][0]
    assert u["status"] == "escaped"        # only the fence escape-scan yields this
    assert u["board_state"] == "blocked"   # a rejection → BLOCKED, not advanced
    assert u["land"] is None               # a blocked unit is not landed

    assert out["validation"]["passed"] is False          # product not satisfied
    assert out["validation"]["fix_proposal"]             # a fix-unit is proposed
    assert "p0" in out["validation"]["remaining"]


# ---------------------------------------------------------------- the CLI surface
def test_work_cli_smoke(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """``charon work --units <plan>`` runs the pipeline end-to-end and exits 0 on a
    passing validation, printing the JSON report."""
    plan = _plan_file(tmp_path, _PLAN_MD)
    rc = cli.main([
        "work", "--units", plan, "--state-dir", str(tmp_path / "state"),
        "--backend", "mock",
    ])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["validation"]["passed"] is True
    assert {u["status"] for u in data["units"]} == {"complete"}


def test_work_cli_nonzero_when_validation_holds(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A units file with no top-level acceptance can still run, but the end-product
    validator HOLDS (no executable acceptance → human review), so the CLI exits
    non-zero — never reporting a silent pass."""
    units = tmp_path / "units.json"
    units.write_text(json.dumps([
        {"goal": "make a", "accept": ["test -f a.txt"], "owned_paths": ["a.txt"]},
    ]), encoding="utf-8")
    rc = cli.main([
        "work", "--units", str(units), "--state-dir", str(tmp_path / "state"),
        "--backend", "mock",
    ])
    data = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert data["units"][0]["status"] == "complete"   # the unit itself ran fine
    assert data["validation"]["passed"] is False       # but no top-level acceptance
    assert "no acceptance checks" in data["validation"]["note"]
