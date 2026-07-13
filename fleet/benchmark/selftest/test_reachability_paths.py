#!/usr/bin/env python3
"""FAIL-ON-REVERT test: grader-daemon.py must not hardcode a dev-box FLEET_DIR.

REACHABILITY-GATE CRITICAL FINDING #1 (fleet/board/REACHABILITY-GATE.md):
grader-daemon.py hardcoded ``FLEET_DIR = Path("/home/stack/charon-private/fleet")``.
Because it's a dev-box-only absolute, the bench-grader unix user (uid 999, not
in group ``stack``, /home/stack is drwxr-x--- stack:stack) cannot traverse it
without an ACL grant. The CONTRACT going forward: cross-boundary paths come
from config/env (CHARON_FLEET) or are derived relative to the file's own
location — never a hardcoded dev-box absolute.

This test proves BOTH:
  A. FLEET_DIR resolves correctly with no env override (relative to
     grader-daemon.py's own location — portable across users/hosts/worktrees).
  B. CHARON_FLEET, when set, overrides the derived default.
  C. (fail-on-revert) the daemon source contains no hardcoded
     "/home/stack/charon-private" literal for FLEET_DIR.

Exits 0 on PASS, non-zero on FAIL.
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent.parent
DAEMON_PATH = BENCH_DIR / "grader-daemon.py"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"  OK: {msg}")


def check_A_default_resolution() -> None:
    """No CHARON_FLEET set: FLEET_DIR must equal the real fleet/ dir, derived
    from the daemon's own location, not a hardcoded literal."""
    print("\n─── Check A: default resolution (no env override) ───")

    env = {k: v for k, v in os.environ.items() if k != "CHARON_FLEET"}
    src = (
        f"import sys; sys.path.insert(0, {str(BENCH_DIR)!r}); "
        "import importlib.util; "
        f"spec = importlib.util.spec_from_file_location('grader_daemon', {str(DAEMON_PATH)!r}); "
        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
        "print(str(mod.FLEET_DIR))"
    )
    out = subprocess.run(
        [sys.executable, "-c", src], capture_output=True, text=True, env=env, check=False
    )
    if out.returncode != 0:
        fail(f"daemon import failed:\n{out.stderr}")

    resolved = Path(out.stdout.strip())
    expected = BENCH_DIR.parent
    if resolved != expected:
        fail(f"FLEET_DIR resolved to {resolved}, expected {expected} (daemon's own fleet/ dir)")
    ok(f"FLEET_DIR resolves to {resolved} with no CHARON_FLEET set")


def check_B_env_override() -> None:
    """CHARON_FLEET, when set, must override the derived default."""
    print("\n─── Check B: CHARON_FLEET env override ───")

    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env["CHARON_FLEET"] = tmp
        src = (
            "import importlib.util; "
            f"spec = importlib.util.spec_from_file_location('grader_daemon', {str(DAEMON_PATH)!r}); "
            "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
            "print(str(mod.FLEET_DIR)); print(str(mod.BENCH_DIR)); print(str(mod.SCORECARD_TSV))"
        )
        out = subprocess.run(
            [sys.executable, "-c", src], capture_output=True, text=True, env=env, check=False
        )
        if out.returncode != 0:
            fail(f"daemon import under CHARON_FLEET override failed:\n{out.stderr}")

        lines = out.stdout.strip().splitlines()
        if len(lines) != 3:
            fail(f"unexpected output: {out.stdout!r}")
        fleet_dir, bench_dir, scorecard_tsv = (Path(x) for x in lines)

        expected_fleet = Path(tmp).resolve()
        if fleet_dir != expected_fleet:
            fail(f"CHARON_FLEET={tmp} not honored: FLEET_DIR={fleet_dir}")
        if bench_dir != expected_fleet / "benchmark":
            fail(f"BENCH_DIR did not derive from overridden FLEET_DIR: {bench_dir}")
        if scorecard_tsv != expected_fleet / "model-scorecard.tsv":
            fail(f"SCORECARD_TSV did not derive from overridden FLEET_DIR: {scorecard_tsv}")
        ok(f"CHARON_FLEET={tmp} correctly overrides FLEET_DIR + all downstream paths")


def check_C_no_hardcoded_devbox_literal() -> None:
    """FAIL-ON-REVERT: no hardcoded dev-box absolute for FLEET_DIR in source."""
    print("\n─── Check C: no hardcoded dev-box literal (FAIL-ON-REVERT) ───")

    text = DAEMON_PATH.read_text()
    banned = 'FLEET_DIR          = Path("/home/stack/charon-private/fleet")'
    if banned in text:
        fail(
            "grader-daemon.py re-hardcodes FLEET_DIR to a dev-box absolute — "
            "REACHABILITY-GATE regression (bench-grader cannot traverse /home/stack)"
        )
    if "_resolve_fleet_dir" not in text:
        fail("grader-daemon.py missing _resolve_fleet_dir() — reachability fix reverted")
    ok("no hardcoded dev-box FLEET_DIR literal; _resolve_fleet_dir() present")


def main() -> int:
    print("=== FAIL-ON-REVERT: grader-daemon FLEET_DIR reachability ===")

    check_A_default_resolution()
    check_B_env_override()
    check_C_no_hardcoded_devbox_literal()

    print("\n=== ALL CHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
