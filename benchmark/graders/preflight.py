#!/usr/bin/env python3
"""Preflight-task grader — routes MODEL-PREFLIGHT battery tasks (T1-T12) to
their LOAD-BEARING, out-of-band hidden graders deployed under
``$KEYS/preflight/`` (mode 0700, bench-grader-owned).

This module is the PREFLIGHT-CHUNK0 dispatch seam's entry point. It is OWNED by
the grader-daemon (#26 / PREFLIGHT epic). It is NEVER imported by product code
or by the graded agent's session — the daemon is the sole caller.

Architecture: fleet/state/PREFLIGHT-DESIGN-V2.md §1 (SUBSTRATE) + §4 (Chunk 0).

Grading contract (mirrors ``graders/real.py``):

    grade(snapshot: Path, unit_id: str) -> dict

Returns ``{score, verdict, gate, reason}``. Unlike ``real.py``'s reds-replay
grade (which may return ``None`` to signal "not my unit, caller falls back"),
this ALWAYS returns a dict — see FAIL-CLOSED below.

LOAD-BEARING KEYS (why the graders live in $KEYS, not the git tree):
    Preflight graders gate tier entry, so their hidden assertions, expected
    values and hidden tests MUST be out of the model's reach — deployed to
    ``$KEYS/preflight/`` (0700, bench-grader-owned), exactly like reds-replay
    keys. The in-repo ``benchmark/preflight-graders/`` dir holds only the
    *deploy source*; a deploy step ``install -o bench-grader -m 0700`` copies
    each grader into ``$KEYS/preflight/``. Nothing model-readable ever carries
    the graded assertion. The graders themselves are PREFLIGHT-CHUNK-B — this
    file only wires the seam and defines the interface + a fail-closed stub.

FAIL-CLOSED CONTRACT (the seam's core safety property):
    If no load-bearing grader is deployed for ``unit_id`` under
    ``$KEYS/preflight/``, or the deployed grader crashes / times out / emits
    non-JSON, this returns a **BLOCK / fail** verdict — it NEVER returns a pass
    and NEVER returns ``None``. A missing or broken grader is a hard FAIL, so an
    undeployed or mis-deployed preflight task can never silently green a model
    into ``tier-models.tsv``. "No grader" means "not proven safe", not "assume
    safe".

DEPLOYMENT INTERFACE (what PREFLIGHT-CHUNK-B must satisfy):
    For a task ``unit_id`` the daemon looks for an executable grader at
    ``$KEYS/preflight/<unit_id>`` (or ``<unit_id>.<ext>``). The daemon invokes it
    as ``<grader> --worktree <snapshot>`` with cwd = the read-only snapshot, and
    reads a single JSON object ``{score, verdict, gate, reason}`` from the last
    line of stdout. Exit non-zero, timeout, or non-JSON → fail-closed BLOCK.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Load-bearing preflight graders are deployed here (0700, bench-grader-owned),
# NOT in the git tree. Module-global so the daemon (and selftests) can point it
# at a fixture dir without importing product config.
KEYS_DIR = Path("/home/bench-grader/keys")
PREFLIGHT_KEYS_DIR = KEYS_DIR / "preflight"

GRADER_TIMEOUT_S = 300


def _fail_closed(unit_id: str, reason: str) -> dict:
    """Return a hard BLOCK verdict. This is the ONLY result for a missing or
    broken grader — never a pass, never None."""
    return {
        "score": 0,
        "verdict": "BLOCK",
        "gate": "fail",
        "reason": f"preflight fail-closed [{unit_id}]: {reason}",
    }


def _find_grader(unit_id: str) -> Path | None:
    """Locate the deployed load-bearing grader for ``unit_id`` under
    ``$KEYS/preflight/``. Returns the grader path, or None if none is deployed.

    Reads ``PREFLIGHT_KEYS_DIR`` at call time so the deploy dir can be
    overridden for hermetic tests.
    """
    base = PREFLIGHT_KEYS_DIR
    try:
        if not base.is_dir():
            return None
    except OSError:
        return None
    exact = base / unit_id
    if exact.exists():
        return exact
    try:
        for cand in sorted(base.glob(f"{unit_id}.*")):
            if cand.is_file():
                return cand
    except OSError:
        return None
    return None


def _grader_cmd(grader: Path) -> list[str]:
    """Build the invocation for a deployed grader based on its extension."""
    suffix = grader.suffix
    if suffix == ".py":
        return [sys.executable, str(grader)]
    if suffix == ".js":
        return ["node", str(grader)]
    return [str(grader)]  # executable deployed with a shebang


def grade(snapshot: Path, unit_id: str) -> dict:
    """Grade a preflight task by running its LOAD-BEARING OOB grader from
    ``$KEYS/preflight/``. ALWAYS returns a result dict (fail-closed on any
    missing/broken grader) — never None, never a silent pass.
    """
    grader = _find_grader(unit_id)
    if grader is None:
        return _fail_closed(
            unit_id,
            f"no load-bearing grader deployed in {PREFLIGHT_KEYS_DIR} "
            f"(deploy the PREFLIGHT-CHUNK-B grader before grading this task)",
        )

    cmd = _grader_cmd(grader) + ["--worktree", str(snapshot)]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=GRADER_TIMEOUT_S, cwd=str(snapshot),
        )
    except subprocess.TimeoutExpired:
        return _fail_closed(unit_id, f"grader timed out after {GRADER_TIMEOUT_S}s")
    except OSError as exc:
        return _fail_closed(unit_id, f"grader could not be executed: {exc}")

    if proc.returncode != 0:
        detail = (proc.stderr.strip() or proc.stdout.strip())[:200]
        return _fail_closed(unit_id, f"grader crashed (exit {proc.returncode}): {detail}")

    out = proc.stdout.strip()
    if not out:
        return _fail_closed(unit_id, "grader produced no output")
    try:
        result = json.loads(out.split("\n")[-1])
    except (ValueError, IndexError):
        return _fail_closed(unit_id, f"grader produced non-JSON output: {out[:200]}")
    if not isinstance(result, dict) or "verdict" not in result:
        return _fail_closed(unit_id, "grader output missing required verdict field")
    return result
