#!/usr/bin/env python3
"""FAIL-ON-REVERT test for STAGE-DEMUX — the phase/trust demux in grader-daemon.py.

STAGE-DEMUX (2026-07-16) splits the OVERLOADED ``stage`` field. Pre-demux:
``grader-daemon.py:_append_capture_row`` hardcoded the literal ``"active"`` into
column 16 of every live row, and ``_handle_capture`` never read
``req["stage"]`` -- so no code path could emit
``source=live/stage=provisional``. The trust axis was inert in production
(45/45 live rows were ``active``; zero ``provisional`` ever). This test
exercises the three invariants the fix MUST hold:

  (1) PROVISIONAL TRUST SURVIVES.  A capture the caller marked
      ``trust_stage=provisional`` (legacy ``stage=provisional`` also
      accepted) AND supplied a real ``actual_verdict`` lands
      ``stage=provisional`` in column 16 of the ledger -- and is therefore
      EXCLUDED from the active grade/budget. Reverting the daemon change
      (back to the hardcoded literal) makes this test RED.

  (2) ACTIVE TRUST STILL SURVIVES.  A capture with ``trust_stage=active``
      AND a real verdict lands ``stage=active``. This proves the fix is a
      demux, not an inverted hardcode.

  (3) PHASE PROTOCOL UNCHANGED.  A capture with NO verdict (i.e. a
      PROVISIONAL phase of the two-phase spool protocol) is still HELD
      -- no row is appended, regardless of the requested trust stage.
      This proves the demux did not break the two-phase spool protocol.

Pre-demux the wider pytest suite was GREEN with a trust axis that had
never once fired across 45/45 rows (cf.
``fleet/tests/test_capture_pipeline.py:160-165``, which asserts a
FALSE-SUCCESS row lands ``active`` -- that test enshrined the hardcode
and is updated in this same PR with justification). The only bar that
distinguishes the demux from the bug is the assertion in test (1):
provisional + real verdict MUST survive to column 16.

Usage:
  python3 fleet/benchmark/selftest/test_stage_demux.py

Exits 0 on PASS, non-zero on FAIL.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent.parent
FLEET_DIR = BENCH_DIR.parent
DAEMON_PATH = BENCH_DIR / "grader-daemon.py"
CAPTURE_DIR = FLEET_DIR / "capture"
ENQUEUE = CAPTURE_DIR / "enqueue-capture.sh"


# ── daemon import (mirror test_capture_pipeline.py) ────────────────────────
_spec = importlib.util.spec_from_file_location("grader_daemon", str(DAEMON_PATH))
_gd = importlib.util.module_from_spec(_spec)
sys.modules["grader_daemon"] = _gd
_spec.loader.exec_module(_gd)
gd = _gd  # type: ignore[reportUnknownVariableType]


# ── minimal output helpers ─────────────────────────────────────────────────
def _ok(msg: str) -> None:
    print(f"  OK: {msg}")


def _bad(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


# ── ledger helpers ─────────────────────────────────────────────────────────
LEDGER_HEADER = (
    "# test ledger (hermetic)\n"
    "# date\tsource\tref\twork_class\ttier\tmodel\tverdict\tgate\tscore\t"
    "time_s\tcost_usd\tcorrections\tnote\ttokens_in\ttokens_out\tstage\n"
)


def _rows(p: Path) -> list[list[str]]:
    return [
        ln.split("\t")
        for ln in p.read_text().splitlines()
        if ln and not ln.startswith("#")
    ]


def _write_model_used(model_used_dir: Path, ref: str, model: str) -> None:
    model_used_dir.mkdir(parents=True, exist_ok=True)
    (model_used_dir / ref).write_text(model + "\n")


# ── fixture: hermetic tmpdir wired to the daemon overrides ────────────────
class _Harness:
    """Bundle of per-test directories + reset of all daemon overrides."""

    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="stage-demux-"))
        self.ledger = self.tmp / "model-scorecard.tsv"
        self.ledger.write_text(LEDGER_HEADER)
        self.provisionals = self.tmp / "capture-provisionals"
        self.scorecard_dir = self.tmp / "scorecard-artifacts"
        self.model_used = self.tmp / "model-used"

    def install_overrides(self) -> None:
        gd._LEDGER_PATH_OVERRIDE = self.ledger
        gd._PROVISIONAL_STORE_OVERRIDE = self.provisionals
        gd._SCORECARD_DIR_OVERRIDE = self.scorecard_dir
        gd._MODEL_USED_DIR_OVERRIDE = self.model_used
        gd._REQ_DIR_OVERRIDE = self.tmp / "spool-req"

    def clear_overrides(self) -> None:
        gd._LEDGER_PATH_OVERRIDE = None
        gd._PROVISIONAL_STORE_OVERRIDE = None
        gd._SCORECARD_DIR_OVERRIDE = None
        gd._MODEL_USED_DIR_OVERRIDE = None
        gd._REQ_DIR_OVERRIDE = None


# ── TEST (1): PROVISIONAL TRUST SURVIVES ──────────────────────────────────
def test_provisional_with_real_verdict_lands_provisional() -> None:
    """The CORE assertion. Impossible pre-demux: a capture the caller
    marked ``trust_stage=provisional`` (or legacy ``stage=provisional``)
    AND supplied a real ``actual_verdict`` lands ``provisional`` in
    column 16. Revert ``_append_capture_row`` to the hardcoded literal
    and this test goes RED."""
    print("\n─── Test 1: provisional trust survives (CORE ASSERTION) ───")
    h = _Harness()
    h.install_overrides()
    _write_model_used(h.model_used, "STAGE-DEMUX-1", "kimi-k2.6-nw")

    run_id = "stage-demux-test1"
    model = "kimi-k2.6-nw"
    ref = "STAGE-DEMUX-1"

    # Phase 1: PROVISIONAL spool write (no verdict, so it must NOT land a row).
    prov_req = {
        "run_id": run_id,
        "model": model,
        "unit_id": f"CAPTURE-{ref}",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "money-path",
        "ref": ref,
        "difficulty": "3",
        "trust_stage": "provisional",   # canonical (going-forward) name
        "evidence": "",
    }
    prov_appended = gd._handle_capture(prov_req)
    if prov_appended is not False:
        h.clear_overrides()
        _bad("REVERT DETECTED: a PROVISIONAL phase (no verdict) wrote a ledger row")
    if _rows(h.ledger):
        h.clear_overrides()
        _bad("REVERT DETECTED: PROVISIONAL phase wrote to the ledger")
    _ok("PROVISIONAL phase held (no row written)")

    # Phase 2: FINAL with a real verdict AND trust_stage=provisional.
    # Pre-demux the daemon IGNORED trust_stage and the row landed
    # stage=active. Post-demux the row MUST land stage=provisional.
    final_req = {
        "run_id": run_id,
        "model": model,
        "unit_id": f"CAPTURE-{ref}",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "money-path",
        "ref": ref,
        "difficulty": "3",
        "trust_stage": "provisional",   # <-- THE DEMUX: must reach col 16
        "actual_verdict": "MERGE",
        "actual_gate": "pass",
        "score": 100,
        "evidence": "calibration-debt: an unsaturated item -> provisional trust",
    }
    final_appended = gd._handle_capture(final_req)
    if final_appended is not True:
        h.clear_overrides()
        _bad("REVERT DETECTED: a well-formed FINAL with real verdict did not append")

    rows = _rows(h.ledger)
    if len(rows) != 1:
        h.clear_overrides()
        _bad(f"expected exactly 1 ledger row, got {len(rows)}: {rows}")
    r = rows[0]
    if r[15] != "provisional":
        h.clear_overrides()
        _bad(
            "REVERT DETECTED: FINAL with trust_stage=provisional landed "
            f"col 16 = {r[15]!r} (expected 'provisional') — the demux is "
            f"inert or reverted. Pre-demux hardcode would yield 'active'."
        )
    _ok(f"FINAL trust_stage=provisional -> ledger col 16 = {r[15]!r}")

    h.clear_overrides()


# ── TEST (2): ACTIVE TRUST STILL SURVIVES ─────────────────────────────────
def test_active_with_real_verdict_lands_active() -> None:
    """The other direction. A capture the caller marked
    ``trust_stage=active`` lands ``stage=active`` -- proves the fix is a
    demux, not an inverted hardcode (i.e. nobody swapped the literals)."""
    print("\n─── Test 2: active trust still survives ───")
    h = _Harness()
    h.install_overrides()
    _write_model_used(h.model_used, "STAGE-DEMUX-2", "deepseek-v4-pro")

    run_id = "stage-demux-test2"
    model = "deepseek-v4-pro"
    ref = "STAGE-DEMUX-2"

    final_req = {
        "run_id": run_id,
        "model": model,
        "unit_id": f"CAPTURE-{ref}",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "routing",
        "ref": ref,
        "difficulty": "2",
        "trust_stage": "active",
        "actual_verdict": "MERGE",
        "actual_gate": "pass",
        "score": 95,
        "evidence": "all items saturated -> active trust",
    }
    appended = gd._handle_capture(final_req)
    if appended is not True:
        h.clear_overrides()
        _bad("FINAL with trust_stage=active did not append")

    rows = _rows(h.ledger)
    if len(rows) != 1:
        h.clear_overrides()
        _bad(f"expected exactly 1 ledger row, got {len(rows)}")
    r = rows[0]
    if r[15] != "active":
        h.clear_overrides()
        _bad(
            f"REVERT DETECTED: trust_stage=active landed col 16 = {r[15]!r} "
            "(expected 'active') — looks like the demux was inverted, not "
            "fixed."
        )
    _ok(f"FINAL trust_stage=active -> ledger col 16 = {r[15]!r}")

    h.clear_overrides()


# ── TEST (3): PHASE PROTOCOL UNCHANGED ────────────────────────────────────
def test_provisional_phase_with_provisional_trust_held() -> None:
    """A capture with NO verdict is HELD (not written) regardless of the
    requested trust stage. This proves the demux did not break the
    two-phase spool protocol: PHASE (write-now vs hold) is still keyed
    on ``actual_verdict`` presence, never on the trust value."""
    print("\n─── Test 3: phase protocol unchanged (PROVISIONAL phase held) ───")
    h = _Harness()
    h.install_overrides()

    for trust_tag in ("provisional", "active"):
        run_id = f"stage-demux-test3-{trust_tag}"
        prov_req = {
            "run_id": run_id,
            "model": "any-model",
            "unit_id": f"CAPTURE-{run_id}",
            "kind": "capture",
            "worktree": "/dev/null",
            "claimed_result": "SUCCESS",
            "work_class": "money-path",
            "ref": run_id,
            "difficulty": "3",
            "trust_stage": trust_tag,
            # no actual_verdict -> PROVISIONAL phase
        }
        appended = gd._handle_capture(prov_req)
        if appended is not False:
            h.clear_overrides()
            _bad(
                f"REVERT DETECTED: PROVISIONAL phase (no verdict) with "
                f"trust_stage={trust_tag} WROTE a ledger row — the phase "
                "protocol is broken"
            )
    if _rows(h.ledger):
        h.clear_overrides()
        _bad("REVERT DETECTED: PROVISIONAL phase appended to the ledger")
    _ok("PROVISIONAL phase held for both trust_stage=provisional and active")

    h.clear_overrides()


# ── TEST (4): legacy `stage` field still accepted (backward compat) ──────
def test_legacy_stage_field_still_accepted() -> None:
    """capture/enqueue-capture.sh (out of this ticket's owns:) still
    writes the on-the-wire field as ``stage``. The daemon must accept
    it as a legacy alias so the spool writer does not need to change
    in this PR. The fail-closed STAGE-FAILCLOSED follow-up will switch
    enqueue-capture.sh to the new canonical ``trust_stage`` name."""
    print("\n─── Test 4: legacy `stage` field still accepted (backward compat) ───")
    h = _Harness()
    h.install_overrides()
    _write_model_used(h.model_used, "STAGE-DEMUX-4", "kimi-k2.6-nw")

    run_id = "stage-demux-test4"
    final_req = {
        "run_id": run_id,
        "model": "kimi-k2.6-nw",
        "unit_id": "CAPTURE-STAGE-DEMUX-4",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "money-path",
        "ref": "STAGE-DEMUX-4",
        "difficulty": "3",
        "stage": "provisional",   # legacy alias (no `trust_stage` key)
        "actual_verdict": "MERGE",
        "actual_gate": "pass",
        "score": 100,
        "evidence": "spool writer still uses the legacy `stage` name",
    }
    appended = gd._handle_capture(final_req)
    if appended is not True:
        h.clear_overrides()
        _bad("FINAL with legacy `stage` field did not append")
    rows = _rows(h.ledger)
    if len(rows) != 1:
        h.clear_overrides()
        _bad(f"expected 1 row, got {len(rows)}")
    if rows[0][15] != "provisional":
        h.clear_overrides()
        _bad(
            f"REVERT DETECTED: legacy `stage=provisional` landed col 16 = "
            f"{rows[0][15]!r} (expected 'provisional') — backward compat "
            "with enqueue-capture.sh broken"
        )
    _ok(f"legacy `stage=provisional` -> ledger col 16 = {rows[0][15]!r}")

    h.clear_overrides()


# ── TEST (5): end-to-end via the real enqueue-capture.sh writer ──────────
def test_endtoend_through_enqueue_capture() -> None:
    """Drive the REAL spool writer (enqueue-capture.sh) for one lifetime
    (provisional -> FINAL, same run_id) and confirm the FINAL lands
    ``stage=provisional`` in the ledger. The FLAW-1 fix (distinct
    on-disk filenames per phase) is exercised en route, and a
    ``state/model-used/<ref>`` anchor backs the unpaired shape."""
    print("\n─── Test 5: end-to-end through enqueue-capture.sh ───")
    if not ENQUEUE.exists():
        print(f"  SKIP: enqueue-capture.sh not present at {ENQUEUE}")
        return

    h = _Harness()
    h.install_overrides()
    req_dir = h.tmp / "spool-req"
    req_dir.mkdir(parents=True, exist_ok=True)
    model = "kimi-k2.6-nw"
    ref = "STAGE-DEMUX-E2E"
    run_id = f"stage-demux-e2e-{model}"
    _write_model_used(h.model_used, ref, model)

    def _process_like_daemon(p: Path) -> None:
        req = gd._read_request(p)
        if req is None:
            _bad(f"enqueue produced a request that did not parse: {p}")
        gd._handle_capture(req)
        p.unlink()

    # Phase 1: charon-run.sh provisional enqueue (real script).
    r1 = subprocess.run(
        [str(ENQUEUE), "--model", model, "--claimed-result", "SUCCESS",
         "--ref", ref, "--stage", "provisional", "--run-id", run_id],
        env={**os.environ, "CAPTURE_SPOOL_DIR": str(req_dir)},
        capture_output=True, text=True,
    )
    if r1.returncode != 0:
        h.clear_overrides()
        _bad(f"enqueue-capture.sh provisional failed: rc={r1.returncode}\n{r1.stderr}")

    # Scan and process the provisional.
    seen: set[str] = set()
    batch1 = gd._scan_requests(seen)
    if len(batch1) != 1:
        h.clear_overrides()
        _bad(f"expected 1 provisional file, got {len(batch1)}")
    for p in batch1:
        seen.add(p.name)
        _process_like_daemon(p)
    if _rows(h.ledger):
        h.clear_overrides()
        _bad("PROVISIONAL phase wrote a ledger row")
    _ok("PROVISIONAL phase via enqueue-capture.sh held")

    # Phase 2: done.sh FINAL enqueue, same run_id, stage=provisional (the
    # trust value the pipeline passes for an unsaturated item), with a
    # real verdict.
    r2 = subprocess.run(
        [str(ENQUEUE), "--model", model, "--claimed-result", "SUCCESS",
         "--ref", ref, "--stage", "provisional", "--run-id", run_id,
         "--actual-verdict", "MERGE", "--actual-gate", "pass", "--score", "100",
         "--evidence", "STAGE-DEMUX e2e"],
        env={**os.environ, "CAPTURE_SPOOL_DIR": str(req_dir)},
        capture_output=True, text=True,
    )
    if r2.returncode != 0:
        h.clear_overrides()
        _bad(f"enqueue-capture.sh FINAL failed: rc={r2.returncode}\n{r2.stderr}")

    # FLAW-1 invariant: distinct on-disk filenames.
    on_disk = sorted(req_dir.glob("*.json"))
    if len(on_disk) != 1:
        h.clear_overrides()
        _bad(
            "FLAW-1 REVERT: provisional and FINAL collided on the same "
            f"filename: {[p.name for p in on_disk]}"
        )

    batch2 = gd._scan_requests(seen)
    if len(batch2) != 1:
        h.clear_overrides()
        _bad(
            f"FLAW-1 REVERT: FINAL swallowed by filename dedup (got {len(batch2)})"
        )
    for p in batch2:
        seen.add(p.name)
        _process_like_daemon(p)

    rows = _rows(h.ledger)
    if len(rows) != 1:
        h.clear_overrides()
        _bad(f"expected exactly 1 promoted live row, got {len(rows)}: {rows}")
    r = rows[0]
    if r[1] != "live":
        h.clear_overrides()
        _bad(f"source should be 'live', got {r[1]!r}")
    if r[15] != "provisional":
        h.clear_overrides()
        _bad(
            "REVERT DETECTED: end-to-end FINAL with --stage provisional "
            f"landed col 16 = {r[15]!r} (expected 'provisional') — the "
            "demux is inert end-to-end via the real spool writer"
        )
    _ok(f"end-to-end via enqueue-capture.sh -> col 16 = {r[15]!r}")

    h.clear_overrides()


# ── main ──────────────────────────────────────────────────────────────────
def main() -> int:
    print("=== FAIL-ON-REVERT: STAGE-DEMUX (phase/trust demux in grader-daemon.py) ===")

    test_provisional_with_real_verdict_lands_provisional()
    test_active_with_real_verdict_lands_active()
    test_provisional_phase_with_provisional_trust_held()
    test_legacy_stage_field_still_accepted()
    test_endtoend_through_enqueue_capture()

    print("\n=== ALL CHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
