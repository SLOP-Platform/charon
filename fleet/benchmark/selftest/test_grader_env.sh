#!/usr/bin/env bash
# selftest/test_grader_env.sh — the missing Chunk-D control panel (review F2,
# board fleet/board/EVAL-GRADER-PROVISION.md).
#
# WHY THIS EXISTS: MODEL-PREFLIGHT's OOB battery has NEVER validly
# discriminated. state/preflight-results/CONTROLS-STATUS.md records that a
# real preflight drive hit, in order: (1) a PermissionError on the session
# root (mktemp -d's default 0700 blocks the cross-user bench-grader daemon —
# now fixed, preflight.sh:243), (2) a shutil.Error when the daemon tried to
# snapshot a `.hypothesis` cache file the AGENT's user could read but the
# DAEMON's user could not, (3) "No module named pytest" for bench-grader's
# python3. Every one of these is an ENVIRONMENT failure, not a judgment of
# model quality — every candidate FAILs every task for the same reason,
# which means the battery cannot separate good from bad. That is exactly the
# validity failure this script exists to prove is (or is not) fixed.
#
# test_preflight_graders.py (a sibling selftest) already proves the GRADER
# LOGIC discriminates honest solutions from gaming variants — but it deploys
# graders into a throwaway dir and runs them directly as `stack`; it never
# exercises the actual cross-user SNAPSHOT + DISPATCH path a real preflight
# run takes. This script closes exactly that gap: it drives a MUST-PASS and a
# MUST-FAIL worktree through the REAL `_snapshot_worktree` (grader-daemon.py)
# and the REAL dispatch seam (graders/preflight.py `grade()`) — the same two
# functions production uses — with the SAME class of cross-user-unreadable
# cache artifact that broke every real run, reproduced hermetically (chmod
# 000 blocks reads for the current non-root user exactly as it would for a
# DIFFERENT unix user with no read grant — no sudo/bench-grader login
# required to prove the mechanism).
#
# CONTROLS:
#   MUST-PASS — a real fix (RetryBudget wired on the live dispatch path),
#               poisoned with an unreadable cache artifact -> must grade
#               gate=="pass", NOT an infra fail-closed BLOCK.
#   MUST-FAIL — the unmodified/pristine fixture, same poison -> must grade
#               gate=="fail" with a REAL task reason, not an infra reason.
#   FAIL-ON-REVERT — the pre-fix snapshot algorithm (inlined below, exactly
#               as it existed before this session: no `.hypothesis` in the
#               ignore set, no tolerant catch) is run on the SAME poisoned
#               MUST-PASS worktree and must RAISE. If it does not raise, the
#               poisoned fixture no longer reproduces the historical bug and
#               this selftest is not proving anything -> treated as a FAIL.
#               And: the LIVE call (graders/preflight.py + grader-daemon.py
#               as committed right now) must itself still succeed — if a
#               future edit reverts the real fix, that live call starts
#               raising too and the MUST-PASS assertion above goes RED.
#
# Exit 0 = all controls proved discrimination through the real runtime path.
# Exit 1 = a control failed to discriminate (the thing review F2 warns about).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH_DIR="$(cd "$HERE/.." && pwd)"

python3 - "$BENCH_DIR" <<'PYEOF'
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BENCH_DIR = Path(sys.argv[1]).resolve()
DAEMON_PATH = BENCH_DIR / "grader-daemon.py"
DISPATCH_PATH = BENCH_DIR / "graders" / "preflight.py"
CHECKS_DIR = BENCH_DIR / "graders" / "preflight_checks"
TASKS_DIR = BENCH_DIR / "preflight-tasks"
KEY = "retry-budget-wire"

FAILURES = []
_TMP = []


def tmp(prefix):
    d = Path(tempfile.mkdtemp(prefix=prefix))
    _TMP.append(d)
    return d


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── load the REAL, currently-committed production code (not a copy) ─────────
gd = load_module("grader_daemon_selftest", DAEMON_PATH)
pf = load_module("preflight_dispatch_selftest", DISPATCH_PATH)

# Hermetic overrides: WORK_DIR/KEYS are bench-grader-owned in production and
# unwritable/unreadable to `stack` — this selftest runs as stack, so it
# points the same functions at throwaway dirs it owns. This changes WHERE
# they read/write, never WHAT they do.
gd.WORK_DIR = tmp("pf-envtest-work-")
_log_lines = []
gd.log = lambda msg: _log_lines.append(msg)

KEYS_DEPLOY = tmp("pf-envtest-keys-") / "preflight"
pf.PREFLIGHT_KEYS_DIR = KEYS_DEPLOY


def deploy_grader(key: str) -> None:
    """Mirror deploy-preflight-graders.sh for one grader, into KEYS_DEPLOY."""
    KEYS_DEPLOY.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CHECKS_DIR / "_pf_common.py", KEYS_DEPLOY / "_pf_common.py")
    shutil.copy2(CHECKS_DIR / f"{key}.py", KEYS_DEPLOY / f"{key}.py")
    base = KEYS_DEPLOY / f"{key}.baseline"
    if base.exists():
        shutil.rmtree(base)
    shutil.copytree(TASKS_DIR / key, base,
                     ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                    ".pytest_cache", "MODEL_RESPONSE.md"))


PROXY_FIXED = '''"""dispatch honoring the retry budget on the real path."""


class Upstream:
    RETRYABLE = {429, 503}

    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.attempts = 0

    def attempt(self, request):
        idx = min(self.attempts, len(self._statuses) - 1)
        self.attempts += 1
        return {"status": self._statuses[idx], "request": request}


def dispatch(request, budget=None):
    upstream = request["upstream"]
    result = upstream.attempt(request)
    while result["status"] in Upstream.RETRYABLE:
        if budget is not None and budget.exhausted():
            return result
        if budget is not None:
            budget.spend()
        result = upstream.attempt(request)
    return result
'''


def new_worktree(poisoned: bool) -> Path:
    """A fresh copy of the pristine fixture, optionally poisoned with the
    exact class of cross-user-unreadable cache artifact that broke every
    real preflight run (CONTROLS-STATUS.md attempt 2)."""
    wt = tmp("pf-envtest-wt-") / KEY
    shutil.copytree(TASKS_DIR / KEY, wt,
                     ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    if poisoned:
        hyp = wt / ".hypothesis" / "examples"
        hyp.mkdir(parents=True)
        cache_file = hyp / "example_db_entry"
        cache_file.write_text("cache-data-not-relevant-to-grading")
        cache_file.chmod(0o000)  # unreadable to THIS process, same effect a
                                  # different unix user with no read grant has
        stray = wt / "gateway" / ".unnamed_tool_cache"
        stray.write_text("stray-cache")
        stray.chmod(0o000)
    return wt


def snapshot_and_grade(worktree: Path, run_id: str):
    """The REAL two-function path production uses: daemon snapshot -> OOB
    grader dispatch. Returns the result dict, or raises if the snapshot step
    itself fails closed (the historical bug: the WHOLE battery could not even
    reach a verdict)."""
    snapshot = gd._snapshot_worktree(str(worktree), run_id)
    return pf.grade(snapshot, KEY)


def is_infra_detain(result: dict) -> bool:
    reason = str(result.get("reason", ""))
    return "fail-closed" in reason or "grader internal error" in reason


deploy_grader(KEY)

print("=== FAIL-ON-REVERT: OOB grader RUNTIME (snapshot + dispatch, not just grader logic) ===\n")

# ── MUST-PASS control ────────────────────────────────────────────────────────
pass_wt = new_worktree(poisoned=True)
(pass_wt / "gateway" / "proxy.py").write_text(PROXY_FIXED)
try:
    pass_result = snapshot_and_grade(pass_wt, "envtest-must-pass")
    if pass_result.get("gate") == "pass" and not is_infra_detain(pass_result):
        print(f"  [PASS] MUST-PASS control: gate=pass ({pass_result.get('reason')})")
    else:
        status = "INFRA-DETAINED" if is_infra_detain(pass_result) else "WRONG-VERDICT"
        FAILURES.append(f"MUST-PASS control did not grade pass ({status}): {pass_result}")
        print(f"  [FAIL] MUST-PASS control: {status} — {pass_result}")
except Exception as exc:
    FAILURES.append(f"MUST-PASS control: snapshot/grade RAISED (battery could not even run): "
                     f"{type(exc).__name__}: {exc}")
    print(f"  [FAIL] MUST-PASS control: snapshot/grade RAISED — {type(exc).__name__}: {exc}")

# ── MUST-FAIL control (pristine/unmodified fixture — real dispatch untouched) ─
fail_wt = new_worktree(poisoned=True)
try:
    fail_result = snapshot_and_grade(fail_wt, "envtest-must-fail")
    if fail_result.get("gate") == "fail" and not is_infra_detain(fail_result):
        print(f"  [PASS] MUST-FAIL control: gate=fail, real reason ({fail_result.get('reason')})")
    else:
        status = "INFRA-DETAINED" if is_infra_detain(fail_result) else "WRONG-VERDICT"
        FAILURES.append(f"MUST-FAIL control did not grade a real fail ({status}): {fail_result}")
        print(f"  [FAIL] MUST-FAIL control: {status} — {fail_result}")
except Exception as exc:
    FAILURES.append(f"MUST-FAIL control: snapshot/grade RAISED (battery could not even run): "
                     f"{type(exc).__name__}: {exc}")
    print(f"  [FAIL] MUST-FAIL control: snapshot/grade RAISED — {type(exc).__name__}: {exc}")

# ── FAIL-ON-REVERT proof ─────────────────────────────────────────────────────
# The PRE-FIX snapshot algorithm, exactly as it existed before this session's
# fix (no `.hypothesis` in the ignore set, no tolerant catch of individual
# unreadable files). Kept here ONLY as a comparison fixture: if this no
# longer raises on the poisoned worktree, the poison no longer reproduces the
# historical bug and this whole selftest is proving nothing.
def pre_fix_snapshot_worktree(worktree_path: str, run_id: str) -> Path:
    src = Path(worktree_path)
    dst = gd.WORK_DIR / run_id
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"),
        symlinks=False,
        copy_function=shutil.copy,
    )
    for f in dst.rglob("*"):
        if f.is_file():
            f.chmod(0o444)
        elif f.is_dir():
            f.chmod(0o555)
    return dst


revert_wt = new_worktree(poisoned=True)
(revert_wt / "gateway" / "proxy.py").write_text(PROXY_FIXED)
try:
    pre_fix_snapshot_worktree(str(revert_wt), "envtest-pre-fix-repro")
    FAILURES.append("FAIL-ON-REVERT: the pre-fix algorithm did NOT raise on the poisoned "
                     "MUST-PASS worktree — fixture is stale, this control proves nothing")
    print("  [FAIL] FAIL-ON-REVERT: pre-fix algorithm did not reproduce the historical bug")
except (shutil.Error, PermissionError, OSError) as exc:
    print(f"  [PASS] FAIL-ON-REVERT: pre-fix algorithm reproduces the historical bug "
          f"({type(exc).__name__}) — confirms the poisoned fixture is load-bearing and the "
          f"real fix (still in effect above) is what makes MUST-PASS/MUST-FAIL discriminate")

for d in _TMP:
    shutil.rmtree(d, ignore_errors=True)

print()
if FAILURES:
    print(f"GRADER-ENV SELFTEST FAILURES ({len(FAILURES)}):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)

print("ALL GRADER-ENV SELFTESTS PASS: the real snapshot+dispatch runtime (not just grader")
print("logic) discriminates MUST-PASS from MUST-FAIL through the exact cross-user-unreadable-")
print("cache hazard that made every real preflight run fail-closed for every model.")
print()
print("NOTE: this proves the RUNTIME CODE PATH. bench-grader's pytest availability and")
print("filesystem ACLs are a separate, per-host OPERATOR provisioning step — see")
print("fleet/state/GRADER-PROVISION-NOTE.md.")
PYEOF
