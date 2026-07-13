#!/usr/bin/env python3
"""FAIL-ON-REVERT test for the PREFLIGHT-CHUNK0 dispatch seam.

Proves the two properties the seam must guarantee, and goes RED if the
``kind=="preflight"`` branch in ``grader-daemon.py::_grade`` (or the
``graders/preflight.py`` entry point) is removed:

  1. ROUTING — a ``kind=="preflight"`` job is dispatched to the preflight
     grader (``graders/preflight.py::grade``), NOT to the section/red/unknown
     fallback. Proven positively: with a stub grader deployed under a fixture
     ``$KEYS/preflight/`` dir, ``_grade`` returns the STUB's distinctive output.
     Revert the seam → the job falls through to the "unknown unit" BLOCK, whose
     reason never contains the stub marker → this assertion FAILS (RED).

  2. FAIL-CLOSED — with NO grader deployed, a ``kind=="preflight"`` job returns
     a BLOCK/fail verdict carrying the preflight fail-closed marker (never a
     pass, never None). Revert the seam → the job falls through to the generic
     "unknown unit … no grader available" BLOCK, which lacks the preflight
     marker → this assertion FAILS (RED). The generic fallback also happens to
     BLOCK, so asserting *verdict==BLOCK* alone would NOT catch a revert — the
     test asserts the preflight-SPECIFIC marker precisely so a revert is caught.

Runs entirely as the ``stack`` user against a tempdir fixture — needs no
bench-grader substrate.

Usage:
  python3 fleet/benchmark/selftest/test_preflight_dispatch.py
Exits 0 on PASS, non-zero on FAIL.
"""
from __future__ import annotations

import importlib.util
import os
import stat
import sys
import tempfile
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent.parent
DAEMON_PATH = BENCH_DIR / "grader-daemon.py"

# Make `from graders.preflight import grade` resolvable (BENCH_DIR is the
# import root the daemon runs under).
sys.path.insert(0, str(BENCH_DIR))


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"  OK: {msg}")


def _load_daemon():
    spec = importlib.util.spec_from_file_location("grader_daemon", DAEMON_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_routing_positive(daemon) -> None:
    """1. A preflight job routes to the deployed grader (positive proof)."""
    print("\n─── Check 1: preflight ROUTING (positive) ───")
    import graders.preflight as pf

    with tempfile.TemporaryDirectory() as td:
        keys = Path(td) / "preflight"
        keys.mkdir()
        marker = "STUB-ROUTED-MARKER-7f3a"
        grader = keys / "PF-ROUTED.py"
        grader.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            f'print(json.dumps({{"score": 100, "verdict": "MERGE", '
            f'"gate": "pass", "reason": "{marker}"}}))\n'
        )
        grader.chmod(grader.stat().st_mode | stat.S_IXUSR)

        orig = pf.PREFLIGHT_KEYS_DIR
        pf.PREFLIGHT_KEYS_DIR = keys
        try:
            snap = Path(td) / "snapshot"
            snap.mkdir()
            req = {"run_id": "r1", "model": "m", "unit_id": "PF-ROUTED",
                   "kind": "preflight", "worktree": str(snap)}
            result = daemon._grade(snap, req)
        finally:
            pf.PREFLIGHT_KEYS_DIR = orig

    if not isinstance(result, dict):
        fail(f"_grade returned non-dict: {result!r}")
    if result.get("reason") != marker or result.get("verdict") != "MERGE":
        fail("preflight job did NOT route to the deployed grader "
             f"(seam missing/reverted?): got {result!r}")
    ok("kind=='preflight' dispatched to graders/preflight.py and ran the deployed grader")


def check_fail_closed(daemon) -> None:
    """2. With no grader deployed, a preflight job fails CLOSED (BLOCK)."""
    print("\n─── Check 2: FAIL-CLOSED (no grader deployed) ───")
    import graders.preflight as pf

    with tempfile.TemporaryDirectory() as td:
        empty_keys = Path(td) / "preflight"  # deliberately NOT created
        orig = pf.PREFLIGHT_KEYS_DIR
        pf.PREFLIGHT_KEYS_DIR = empty_keys
        try:
            snap = Path(td) / "snapshot"
            snap.mkdir()
            req = {"run_id": "r2", "model": "m", "unit_id": "PF-UNDEPLOYED",
                   "kind": "preflight", "worktree": str(snap)}
            result = daemon._grade(snap, req)
        finally:
            pf.PREFLIGHT_KEYS_DIR = orig

    if not isinstance(result, dict):
        fail(f"_grade returned non-dict: {result!r}")
    if result.get("verdict") != "BLOCK" or result.get("gate") != "fail":
        fail(f"undeployed preflight task did NOT fail closed: {result!r}")
    reason = str(result.get("reason", ""))
    # The preflight-SPECIFIC marker distinguishes the seam from the generic
    # "unknown unit" fallback that a revert would hit.
    if "preflight fail-closed" not in reason:
        fail("preflight job did NOT reach the fail-closed preflight path "
             f"(seam missing/reverted → generic fallback?): reason={reason!r}")
    if result.get("score", 0) != 0:
        fail(f"fail-closed verdict must score 0, got {result.get('score')}")
    ok("undeployed preflight task fails CLOSED with the preflight marker (never a silent pass)")


def check_stub_never_none() -> None:
    """graders/preflight.grade must NEVER return None (unlike real.py)."""
    print("\n─── Check 3: preflight grade() never returns None ───")
    import graders.preflight as pf
    with tempfile.TemporaryDirectory() as td:
        pf.PREFLIGHT_KEYS_DIR = Path(td) / "nope"
        r = pf.grade(Path(td), "ANY-UNIT")
    if r is None:
        fail("graders/preflight.grade returned None — would let a caller skip grading")
    if r.get("verdict") != "BLOCK":
        fail(f"grade() with no grader must BLOCK, got {r!r}")
    ok("graders/preflight.grade always returns a fail-closed dict")


def main() -> int:
    print("=== FAIL-ON-REVERT: preflight dispatch seam ===")
    daemon = _load_daemon()
    check_routing_positive(daemon)
    check_fail_closed(daemon)
    check_stub_never_none()
    print("\n=== ALL CHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
