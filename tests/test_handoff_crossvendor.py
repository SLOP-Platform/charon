"""Cross-vendor handoff — mock contract proofs + live ACP integration proof.

Mock proofs (re-shaped per REVIEW-LOG 2026-06-24, OOB2-2 / OOB2-8 / BR2-4):
- the handoff loop excludes the FULL exhausted set, never re-picks a dead backend;
- progress truth lives in the ledger+disk, so a LYING backend's claim does not
  survive a vendor switch (the real H3 content, not two well-behaved mocks
  agreeing);
- a killed coordinator rehydrates without replaying committed work (H5);
- exhaustion (H4) routes to a *different* vendor, which finishes from the ledger.

Live ACP proofs (REVIEW-LOG 2026-06-26 — feat/live-acp-handoff):
- test_live_acp_crossvendor_handoff: two AcpBackend instances backed by Python
  stdlib stubs (no keys, no network) prove the same contract through real
  subprocess ACP dispatch. Stub A signals H4 exhaustion via session/update
  rate_limited; stub B completes. Closes the OOB2-1 honesty gap honestly.
- test_live_doctor_probe_handoff: probe_handoff() confirmed green with stubs.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from charon import coordinator, gitutil, handoff
from charon.acceptance import AcceptanceCheck
from charon.adapters.acp import AcpBackend
from charon.adapters.mock import MockBackend, MockMode
from charon.doctor import probe_handoff
from charon.fence import Fence
from charon.ledger import Ledger
from charon.router import StaticRouter
from charon.types import Autonomy, WorkUnit


def _unit() -> WorkUnit:
    return WorkUnit(task_id="t1", goal="goal")


def _two_file_checks() -> list[AcceptanceCheck]:
    return [
        AcceptanceCheck("a0", "test -f file1.txt"),
        AcceptanceCheck("a1", "test -f file2.txt"),
    ]


# --------------------------------------------------------------- BR2-4 fix
def test_exclude_accumulation_never_repicks_exhausted() -> None:
    """3 backends, 2 already exhausted → the router returns the third and never
    a repeat. Pre-fix, choose_next_backend excluded only the latest one."""
    router = StaticRouter(backends=["alpha", "beta", "gamma"])
    route = handoff.choose_next_backend(router, "codegen", exclude={"alpha", "beta"})
    assert route.backend == "gamma"


def test_all_excluded_raises_clean() -> None:
    router = StaticRouter(backends=["alpha", "beta"])
    try:
        handoff.choose_next_backend(router, "codegen", exclude={"alpha", "beta"})
    except RuntimeError as exc:
        assert "no backend" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError when every backend excluded")


# ------------------------------------------------------------ H4 + completion
def test_crossvendor_handoff_completes_and_records_both(
    state_dir: Path, git_repo: Path
) -> None:
    """Vendor A makes partial progress then exhausts (H4); the loop re-routes to
    vendor B (H6), which finishes. provider_history shows both, in order."""
    checks = _two_file_checks()
    # A: creates file1 on its one dispatch, then self-reports exhausted.
    mock_a = MockBackend(name="mock-a", creates=["file1.txt"], exhaust_after=1)
    # B: a different vendor; creates the remaining file.
    mock_b = MockBackend(name="mock-b", creates=["file2.txt"])
    led = Ledger.create(state_dir, "t1", "goal", checks, str(git_repo),
                        gitutil.head(git_repo))
    backends = {"mock-a": mock_a, "mock-b": mock_b}
    router = StaticRouter(backends=["mock-a", "mock-b"])

    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router)

    assert res.status == "complete"
    assert res.remaining == []
    assert led.provider_history == ["mock-a", "mock-b"]  # H4/H6: handed off
    assert (git_repo / "file1.txt").exists()
    assert (git_repo / "file2.txt").exists()
    assert led.lkg_ref != led.base_ref  # advanced only at full verification (INV-2)


def test_h5_no_progress_replay_across_handoff(
    state_dir: Path, git_repo: Path
) -> None:
    """H5: vendor B does only the remaining delta — it never re-creates the file
    vendor A already committed. We prove it by making B's create list disjoint
    and checking A's file is the SAME content A wrote (not overwritten)."""
    checks = _two_file_checks()
    mock_a = MockBackend(name="mock-a", creates=["file1.txt"], exhaust_after=1)
    mock_b = MockBackend(name="mock-b", creates=["file2.txt"])
    led = Ledger.create(state_dir, "t1", "goal", checks, str(git_repo),
                        gitutil.head(git_repo))
    backends = {"mock-a": mock_a, "mock-b": mock_b}
    router = StaticRouter(backends=["mock-a", "mock-b"])

    coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router)

    # A's committed artifact survives the handoff and still carries A's mark.
    assert (git_repo / "file1.txt").read_text() == "created by mock-a\n"
    assert (git_repo / "file2.txt").read_text() == "created by mock-b\n"
    # And B was dispatched exactly once (the remaining delta), not re-doing A.
    assert mock_b._dispatches == 1


def test_h3_rehydration_is_provider_independent_after_handoff(
    state_dir: Path, git_repo: Path
) -> None:
    """H3: after A's checkpoint, `remaining` derived from the ledger+disk is the
    same set no matter which backend (or a fresh reload) computes it — because
    acceptance is executable (INV-6), not a vendor's opinion."""
    checks = _two_file_checks()
    mock_a = MockBackend(name="mock-a", creates=["file1.txt"], exhaust_after=1)
    led = Ledger.create(state_dir, "t1", "goal", checks, str(git_repo),
                        gitutil.head(git_repo))
    backends = {"mock-a": mock_a}  # only A; it exhausts with no target -> stops
    router = StaticRouter(backends=["mock-a"])
    coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router)

    # file1 done, file2 not. Any reader derives {a1}.
    from_a = handoff.rehydrate_remaining(led)
    reloaded = Ledger.load(state_dir, "t1")  # "vendor B" opening the ledger fresh
    from_b = handoff.rehydrate_remaining(reloaded)
    assert from_a == from_b == {"a1"}


# --------------------------------------------------- OOB2-8 adversarial handoff
def test_lying_vendor_claim_does_not_survive_handoff(
    state_dir: Path, git_repo: Path
) -> None:
    """A LIES (claims PROGRESSED + a commit, satisfies nothing) then exhausts.
    The ledger derives progress from disk, so the lie is invisible to vendor B:
    B rehydrates and still sees everything remaining, and must actually do it.
    The forged claim never advances lkg past an unverified commit (INV-2)."""
    checks = _two_file_checks()
    mock_a = MockBackend(name="mock-a", mode=MockMode.LIE, exhaust_after=1)
    mock_b = MockBackend(name="mock-b", creates=["file1.txt", "file2.txt"])
    led = Ledger.create(state_dir, "t1", "goal", checks, str(git_repo),
                        gitutil.head(git_repo))
    backends = {"mock-a": mock_a, "mock-b": mock_b}
    router = StaticRouter(backends=["mock-a", "mock-b"])

    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router,
                         max_checkpoints=8)

    # A's checkpoint recorded NOTHING verified despite its bogus success claim.
    a_checkpoint = led.checkpoints()[0]
    assert a_checkpoint.provider == "mock-a"
    assert a_checkpoint.verified == []  # the lie did not register as progress
    assert sorted(a_checkpoint.remaining) == ["a0", "a1"]
    # The run still completes — but only because B did the real work.
    assert res.status == "complete"
    assert led.provider_history[0] == "mock-a"
    assert "mock-b" in led.provider_history


# ========================================================= live ACP proof
# These tests run real ACP subprocess clients (AcpBackend) backed by Python
# stdlib stubs — no API keys, no network. The stubs speak the ACP protocol
# over stdio and create files in the shared worktree, exercising the same code
# paths a real Claude Code / Codex agent would hit.

def _write_stubs(tmp_path: Path) -> tuple[Path, Path]:
    """Write two self-contained ACP stub scripts to tmp_path.

    Stub A: creates handoff-a.txt then emits session/update {rate_limited:true}
    before returning success — the H4 exhaustion signal absorbed by health().
    Stub B: creates handoff-b.txt and returns success.
    Both stubs respect the cwd supplied in session/new params.
    """
    stub_a = tmp_path / "stub_a.py"
    stub_a.write_text(textwrap.dedent("""\
        import json, os, sys
        def respond(obj):
            sys.stdout.buffer.write(json.dumps(obj).encode() + b"\\n")
            sys.stdout.buffer.flush()
        cwd = os.getcwd()
        for raw in sys.stdin.buffer:
            raw = raw.strip()
            if not raw: continue
            try: req = json.loads(raw)
            except Exception: continue
            m, rid = req.get("method", ""), req.get("id")
            if m == "initialize":
                respond({"jsonrpc": "2.0", "id": rid,
                         "result": {"protocolVersion": 1, "capabilities": {}}})
            elif m == "session/new":
                cwd = req.get("params", {}).get("cwd", cwd)
                respond({"jsonrpc": "2.0", "id": rid, "result": {"sessionId": "a-1"}})
            elif m == "session/prompt":
                open(os.path.join(cwd, "handoff-a.txt"), "w").write("by stub-a\\n")
                respond({"jsonrpc": "2.0", "method": "session/update",
                         "params": {"usage": {"rate_limited": True}}})
                respond({"jsonrpc": "2.0", "id": rid, "result": {"done": True}})
                break
    """))

    stub_b = tmp_path / "stub_b.py"
    stub_b.write_text(textwrap.dedent("""\
        import json, os, sys
        def respond(obj):
            sys.stdout.buffer.write(json.dumps(obj).encode() + b"\\n")
            sys.stdout.buffer.flush()
        cwd = os.getcwd()
        for raw in sys.stdin.buffer:
            raw = raw.strip()
            if not raw: continue
            try: req = json.loads(raw)
            except Exception: continue
            m, rid = req.get("method", ""), req.get("id")
            if m == "initialize":
                respond({"jsonrpc": "2.0", "id": rid,
                         "result": {"protocolVersion": 1, "capabilities": {}}})
            elif m == "session/new":
                cwd = req.get("params", {}).get("cwd", cwd)
                respond({"jsonrpc": "2.0", "id": rid, "result": {"sessionId": "b-1"}})
            elif m == "session/prompt":
                open(os.path.join(cwd, "handoff-b.txt"), "w").write("by stub-b\\n")
                respond({"jsonrpc": "2.0", "id": rid, "result": {"done": True}})
                break
    """))

    return stub_a, stub_b


def test_live_acp_crossvendor_handoff(
    state_dir: Path, git_repo: Path, tmp_path: Path
) -> None:
    """Live ACP cross-vendor handoff: real AcpBackend subprocess dispatch, no mocks.

    Stub A creates handoff-a.txt and signals H4 exhaustion via session/update
    rate_limited (absorbed by health()). Coordinator routes to stub B, which
    creates handoff-b.txt. Asserts the full handoff contract:
    - res.status == "complete"
    - provider_history records both vendors in order
    - both acceptance checks pass on disk
    - lkg_ref advances (INV-2: only after full verification)
    """
    stub_a_path, stub_b_path = _write_stubs(tmp_path)
    checks = [
        AcceptanceCheck("ha", "test -f handoff-a.txt"),
        AcceptanceCheck("hb", "test -f handoff-b.txt"),
    ]
    unit = WorkUnit(task_id="live-handoff", goal="create handoff-a.txt and handoff-b.txt")
    led = Ledger.create(state_dir, "live-handoff", unit.goal, checks,
                        str(git_repo), gitutil.head(git_repo))

    backend_a = AcpBackend(command=[sys.executable, str(stub_a_path)], name="stub-a")
    backend_b = AcpBackend(command=[sys.executable, str(stub_b_path)], name="stub-b")

    res = coordinator.run(
        unit,
        {"stub-a": backend_a, "stub-b": backend_b},
        led,
        Fence(Autonomy.L1),
        StaticRouter(backends=["stub-a", "stub-b"]),
    )

    assert res.status == "complete"
    assert led.provider_history == ["stub-a", "stub-b"]
    assert (git_repo / "handoff-a.txt").exists()
    assert (git_repo / "handoff-b.txt").exists()
    assert led.lkg_ref != led.base_ref


def test_live_doctor_probe_handoff(tmp_path: Path) -> None:
    """probe_handoff() returns ok when driven by real ACP subprocess stubs."""
    stub_a_path, stub_b_path = _write_stubs(tmp_path)
    rep = probe_handoff(
        [sys.executable, str(stub_a_path)],
        [sys.executable, str(stub_b_path)],
    )
    assert rep.a_dispatched, rep.notes
    assert rep.b_dispatched, rep.notes
    assert rep.handoff_completes, rep.notes
    assert rep.ok
