#!/usr/bin/env python3
"""reds_replay.py — real-task grader for replayed reds (#25 reds-replay).

This grader is dispatched by ``grader-daemon.py`` (running as
``bench-grader``). It reads the unit's ``check_cmd`` from the answer-key
tree ``$KEYS/reds-replay.tsv`` — a file the graded agent's user cannot
read — and runs it against the daemon's read-only snapshot of the
agent's worktree.

The ``check_cmd`` is the SAME grader used by ``fleet/reds.tsv``: it exits
0 when the red is GONE (green) and non-zero when still RED. For a
replayed red, the grader substitutes ``{worktree}`` in the check_cmd
with the snapshot path so the check targets the agent's pre-fix-starting
worktree, not ``origin/master``.

CLI contract (shared with the S0-S6 graders for the daemon's dispatch):
    python3 reds_replay.py --worktree <snapshot> --keys <keys-dir> --unit-id <id>
        [--prefix-snapshot <pre-fix-baseline>]
emits ONE line of JSON to stdout:
    {"score": int 0-100, "verdict": "MERGE|FIXES|BLOCK", "gate": "pass|fail", "reason": "..."}

Anti-false-green guard (F5): the pre-fix snapshot must FAIL the check (a
red that is already green pre-fix is not a valid task). If a
``--prefix-snapshot`` is supplied, the grader runs the check against it
and requires a RED result. A curated case that is already GREEN pre-fix
scores 0 and is flagged ``invalid`` (gate=fail), never 100. The grader
NEVER invokes a shell on the snapshot path (F2): the check runs via an
argument list (``shell=False``) so untrusted path components cannot
metacharacter-inject.
"""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

REDS_REPLAY_TSV = "reds-replay.tsv"

# Score bands mirror bench.sh's verdict_from_score: ≥90 MERGE, ≥50 FIXES, <50
# BLOCK. A reds-replay check is binary (pass/fail), so we map pass→100/MERGE
# and fail→0/BLOCK. The daemon records the verdict the grader emits.
SCORE_PASS = 100
SCORE_FAIL = 0


def parse_args(argv: list[str]) -> tuple[Path, Path, str, Path | None]:
    args: dict[str, str] = {"worktree": "", "keys": "", "unit-id": "", "prefix-snapshot": ""}
    it = iter(argv)
    for a in it:
        if a == "--worktree":
            args["worktree"] = next(it)
        elif a == "--keys":
            args["keys"] = next(it)
        elif a == "--unit-id":
            args["unit-id"] = next(it)
        elif a == "--prefix-snapshot":
            args["prefix-snapshot"] = next(it)
    if not args["worktree"] or not args["keys"]:
        print(json.dumps({
            "score": 0, "verdict": "BLOCK", "gate": "fail",
            "reason": f"grader usage: --worktree and --keys required (got {args})",
        }))
        sys.exit(2)
    prefix = Path(args["prefix-snapshot"]).resolve() if args["prefix-snapshot"] else None
    return (Path(args["worktree"]).resolve(),
            Path(args["keys"]).resolve(), args["unit-id"], prefix)


def _verdict(score: int) -> str:
    if score >= 90:
        return "MERGE"
    if score >= 50:
        return "FIXES"
    return "BLOCK"


def emit(score: int, gate: str, reason: str) -> None:
    out = {
        "score": max(0, min(100, int(score))),
        "verdict": _verdict(score),
        "gate": gate,
        "reason": reason,
    }
    print(json.dumps(out))


def _load_reds_row(keys: Path, unit_id: str) -> dict[str, str]:
    """Read ``$KEYS/reds-replay.tsv`` and return the row for ``unit_id``.

    Columns (tab-separated): unit_id, check_cmd, expect_green_exit,
    work_class, note
    """
    p = keys / REDS_REPLAY_TSV
    if not p.exists():
        return {}
    for ln in p.read_text().splitlines():
        if ln.startswith("#") or not ln.strip() or "\t" not in ln:
            continue
        cols = ln.split("\t")
        if len(cols) < 2:
            continue
        if cols[0] == unit_id:
            return {
                "unit_id": cols[0],
                "check_cmd": cols[1] if len(cols) > 1 else "",
                "expect_green_exit": cols[2] if len(cols) > 2 else "0",
                "work_class": cols[3] if len(cols) > 3 else "red",
                "note": cols[4] if len(cols) > 4 else "",
            }
    return {}


def _run_check(check_cmd: str, worktree: Path, expect_green: str) -> tuple[bool, int, str]:
    """Substitute ``{worktree}`` in ``check_cmd`` and run it WITHOUT a shell.

    Returns (passed, exit_code, combined_output).

    F2 hardening: the command is split into an argument list (``shlex.split``)
    and executed with ``shell=False``. The ``worktree`` path is derived from
    untrusted input (the request's ``run`` field, via the daemon snapshot), so
    it must NEVER be passed through a shell — a path containing ``; rm -rf``,
    ``$(...)`` or backticks would otherwise execute arbitrary code as
    ``bench-grader``. With an argument list, any metacharacters are inert
    tokens, not shell syntax. ``{worktree}`` is substituted per-token so a
    snapshot path is a single argv element even if it contains spaces.
    """
    # Build the argv without a shell: tokenize the trusted check_cmd, then
    # substitute {worktree} into each token (so a multi-segment path stays one
    # argv element). shlex.split would itself interpret metacharacters in the
    # worktree path if substituted BEFORE splitting, so substitute AFTER.
    try:
        tokens = shlex.split(check_cmd)
    except ValueError as exc:
        return False, -1, f"check_cmd not shell-lexable: {exc}"
    wt_str = str(worktree)
    argv = [tok.replace("{worktree}", wt_str) for tok in tokens]
    if not argv:
        return False, -1, "check_cmd tokenized to empty argv"
    try:
        proc = subprocess.run(
            argv, shell=False, cwd=str(worktree),
            capture_output=True, text=True, timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            return False, -1, "check_cmd timed out after 120s"
        return False, -1, f"check_cmd spawn failed: {exc}"
    out = (proc.stdout or "") + (proc.stderr or "")
    # expect_green is "0" means exit 0 == green (pass). Any other value means
    # that exit code == green. Default: 0.
    green_code = int(expect_green) if expect_green.strip() else 0
    passed = (proc.returncode == green_code)
    return passed, proc.returncode, out.strip()[:400]


def main() -> int:
    worktree, keys, unit_id, prefix_snapshot = parse_args(sys.argv[1:])
    row = _load_reds_row(keys, unit_id)
    check_cmd = row.get("check_cmd", "")
    if not check_cmd:
        return emit(SCORE_FAIL, "fail",
                    f"no check_cmd for unit '{unit_id}' in {keys}/{REDS_REPLAY_TSV}") or 0

    expect_green = row.get("expect_green_exit", "0")

    # F5 — pre-fix false-green guard: if a pre-fix baseline snapshot is
    # available, the check MUST FAIL against it (a curated red that is already
    # green before the fix is not a valid task — it scores 0, never 100). This
    # blocks false positives where a trivially-already-green case would score
    # a perfect MERGE.
    if prefix_snapshot is not None:
        prefix_passed, prefix_rc, prefix_out = _run_check(
            check_cmd, prefix_snapshot, expect_green)
        if prefix_passed:
            return emit(
                SCORE_FAIL, "fail",
                f"invalid curated red: check is GREEN at pre-fix baseline "
                f"(prefix_snapshot={prefix_snapshot}, exit {prefix_rc}); "
                f"a red that is already green pre-fix scores 0, not 100"
                + (f": {prefix_out[:120]}" if prefix_out else "")
            ) or 0

    passed, rc, out = _run_check(check_cmd, worktree, expect_green)
    if passed:
        emit(SCORE_PASS, "pass",
             f"check_cmd passed (exit {rc})" + (f": {out[:120]}" if out else ""))
    else:
        emit(SCORE_FAIL, "fail",
             f"check_cmd FAILED (exit {rc})" + (f": {out[:120]}" if out else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
