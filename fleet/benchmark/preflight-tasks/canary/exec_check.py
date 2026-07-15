#!/usr/bin/env python3
"""exec_check.py — SANDBOXED exec-checker for the leg-preflight canary (F14).

Runs MODEL-EMITTED code, never the caller's own process. leg-canary-prototype.py
did a bare exec(code, ns) inline ("trusted-ish, short") — fine for a scratch
script, a supply-chain hole once promoted (MODEL-TESTING-ADVERSARIAL-REVIEW.md
F14). This module is the fix: the candidate's code runs in a FRESH child
process (subprocess.run, not exec() in-process) with:
  - a wall-clock timeout (subprocess `timeout=`, kills on expiry)
  - resource limits applied via preexec_fn before the child execs Python:
    RLIMIT_CPU (cpu seconds), RLIMIT_AS (address-space bytes), RLIMIT_NPROC
    (no forking further children), RLIMIT_FSIZE (no writing large files),
    core dumps disabled
  - a stripped environment (no inherited secrets/tokens/PATH surprises)
  - stdin/stdout/stderr fully captured, never shared with the parent's fds

Usage:
    exec_check.py <checks.json>
    reads the candidate's raw code from stdin.
    checks.json: a JSON list of [input, expected_bool] pairs. The candidate
    code must define is_bal(s) (matching the canary prompt's contract); this
    checker calls it for each input and compares against expected_bool.

Prints one JSON line to stdout: {"passed": N, "total": M, "note": "..."}
Never raises on candidate misbehavior — a crash/timeout/non-callable/wrong
answer all just reduce "passed", they never propagate an exception past
main() (a hostile/broken candidate must never crash the preflight run).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

TIMEOUT_S = 5
CPU_LIMIT_S = 3
AS_LIMIT_BYTES = 256 * 1024 * 1024  # 256MB address space ceiling

# The child-process wrapper: receives the candidate's code on ITS OWN stdin,
# execs it in a throwaway namespace, runs the checks, prints ONLY a JSON
# result line. This text is written into the child's argv (via -c), not
# eval'd by the parent — the parent (main() below) never executes candidate
# code itself, only launches this fixed, trusted wrapper as a subprocess.
_CHILD_WRAPPER = r"""
import json, sys
code = sys.stdin.read()
checks = json.loads(sys.argv[1])
passed, note = 0, ""
try:
    ns = {}
    exec(compile(code, "<candidate>", "exec"), ns)
    f = ns.get("is_bal")
    if callable(f):
        for s, expected in checks:
            try:
                if bool(f(s)) == expected:
                    passed += 1
            except Exception as e:
                note = f"call-fail:{e!r}"[:80]
    else:
        note = "no-callable-is_bal"
except Exception as e:
    note = f"exec-fail:{e!r}"[:80]
print(json.dumps({"passed": passed, "total": len(checks), "note": note}))
"""


def _limit_resources():
    """preexec_fn: applied in the child AFTER fork, BEFORE exec — bounds the
    candidate's runtime footprint. Best-effort: platforms lacking `resource`
    (non-POSIX) just skip this and rely on the timeout+process-boundary."""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_S, CPU_LIMIT_S))
        resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT_BYTES, AS_LIMIT_BYTES))
        resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))  # no further forking
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))  # no file writes
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))  # no core dumps
    except Exception:
        pass


def strip_fences(text: str) -> str:
    """Model output is often fenced despite the prompt saying not to —
    strip a leading/trailing ``` fence defensively (never trust prose)."""
    return re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text.strip())


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"passed": 0, "total": 0, "note": "usage: exec_check.py <checks.json>"}))
        return 2
    checks_path = sys.argv[1]
    with open(checks_path) as fh:
        checks = json.load(fh)
    raw_code = sys.stdin.read()
    code = strip_fences(raw_code)

    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD_WRAPPER, json.dumps(checks)],
            input=code,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            env={"PATH": "/usr/bin:/bin"},  # stripped env — no inherited secrets
            preexec_fn=_limit_resources,
        )
    except subprocess.TimeoutExpired:
        print(json.dumps({"passed": 0, "total": len(checks), "note": "sandbox-timeout"}))
        return 0
    except Exception as e:  # noqa: BLE001 — a sandbox failure is a DEGRADED signal, not a crash
        print(json.dumps({"passed": 0, "total": len(checks), "note": f"sandbox-error:{e!r}"[:100]}))
        return 0

    out = (proc.stdout or "").strip().splitlines()
    result_line = out[-1] if out else ""
    try:
        result = json.loads(result_line)
    except Exception:
        result = {"passed": 0, "total": len(checks), "note": f"sandbox-bad-output rc={proc.returncode}"}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
