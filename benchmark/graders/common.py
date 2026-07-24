"""Shared helpers for all deterministic S0-S5 graders (build-rig only, no product code).

Grader CLI contract (see graders/sN.py):
    python3 graders/sN.py --worktree <dir> --baseline <fixtures/sections/sN>
emits ONE line of JSON to stdout:
    {"score": int 0-100, "verdict": "MERGE|FIXES|BLOCK", "gate": "pass|fail|-", "reason": "..."}
Exit code is always 0 (the score/verdict conveys the result) unless the grader
itself errors out (bad args, missing worktree) - that's an operator-facing error,
distinct from a benchmarked model failing the section.
"""
import difflib
import json
import shutil
import subprocess
import sys
from pathlib import Path

IGNORE_NAMES = {
    "__pycache__", ".pytest_cache", ".mypy_cache", ".hypothesis", "dist", "node_modules",
    ".DS_Store", "*.pyc",
}


def verdict_from_score(score):
    if score >= 90:
        return "MERGE"
    if score >= 50:
        return "FIXES"
    return "BLOCK"


def emit(score, gate, reason):
    score = max(0, min(100, int(score)))
    out = {
        "score": score,
        "verdict": verdict_from_score(score),
        "gate": gate,
        "reason": reason,
    }
    print(json.dumps(out))
    return out


def _walk_files(root: Path):
    files = set()
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if any(part in IGNORE_NAMES for part in p.parts):
            continue
        if p.suffix == ".pyc":
            continue
        files.add(str(p.relative_to(root)))
    return files


def changed_files(baseline: Path, worktree: Path):
    """Return sorted list of relpaths added/removed/modified between baseline and worktree."""
    baseline = Path(baseline)
    worktree = Path(worktree)
    b_files = _walk_files(baseline)
    w_files = _walk_files(worktree)
    changed = set()
    for rel in b_files | w_files:
        bp = baseline / rel
        wp = worktree / rel
        if rel not in b_files or rel not in w_files:
            changed.add(rel)
            continue
        try:
            if bp.read_bytes() != wp.read_bytes():
                changed.add(rel)
        except OSError:
            changed.add(rel)
    return sorted(changed)


def file_diff(baseline: Path, worktree: Path, relpath: str) -> str:
    bp = Path(baseline) / relpath
    wp = Path(worktree) / relpath
    b_lines = bp.read_text().splitlines(keepends=True) if bp.exists() else []
    w_lines = wp.read_text().splitlines(keepends=True) if wp.exists() else []
    return "".join(difflib.unified_diff(b_lines, w_lines, fromfile=f"a/{relpath}", tofile=f"b/{relpath}"))  # noqa: E501


def run_pytest(cwd, args=None, timeout=60):
    """Run pytest -q in cwd. Returns (passed: bool, output: str)."""
    cmd = [sys.executable, "-m", "pytest", "-q"] + (args or [])
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"pytest timed out after {timeout}s"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out


def swap_and_run_pytest(worktree: Path, swap_relpath: str, swap_content: str, test_args=None, timeout=60):  # noqa: E501
    """Copy worktree to a scratch dir, overwrite one file's content, run pytest.
    Used for the "real-path proof" pattern: swap in the pre-fix reference file
    and confirm the model's own test now FAILS (proving the test actually
    exercises that file rather than dodging it).
    Returns (passed: bool, output: str, scratch_dir: Path).
    """
    import tempfile
    scratch = Path(tempfile.mkdtemp(prefix="bench-swap-"))
    dest = scratch / "wt"
    shutil.copytree(worktree, dest, ignore=shutil.ignore_patterns(*IGNORE_NAMES))
    target = dest / swap_relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(swap_content)
    passed, out = run_pytest(dest, args=test_args, timeout=timeout)
    return passed, out, dest


def grep_test_files_for(worktree: Path, baseline: Path, patterns, test_dir="tests"):
    """Grep the model's NEW/CHANGED test files (relative to baseline) for any of
    `patterns` (list of substrings). Returns list of (relpath, pattern) hits."""
    hits = []
    changed = changed_files(baseline, worktree)
    for rel in changed:
        if not rel.startswith(test_dir + "/"):
            continue
        p = Path(worktree) / rel
        if not p.exists() or p.suffix != ".py":
            continue
        text = p.read_text(errors="ignore")
        for pat in patterns:
            if pat in text:
                hits.append((rel, pat))
    return hits


def new_or_modified_test_files(baseline: Path, worktree: Path, test_dir="tests"):
    changed = changed_files(baseline, worktree)
    return [r for r in changed if r.startswith(test_dir + "/") and r.endswith(".py")]


def scope_ok(changed, allowed_prefixes):
    """True if every changed relpath starts with one of allowed_prefixes."""
    for rel in changed:
        if not any(rel.startswith(pfx) for pfx in allowed_prefixes):
            return False
    return True


def parse_args(argv):
    args = {"worktree": None, "baseline": None}
    it = iter(argv)
    for a in it:
        if a == "--worktree":
            args["worktree"] = next(it)
        elif a == "--baseline":
            args["baseline"] = next(it)
    if not args["worktree"] or not args["baseline"]:
        print(json.dumps({"score": 0, "verdict": "BLOCK", "gate": "fail",
                           "reason": "grader usage error: --worktree and --baseline required"}))
        sys.exit(2)
    # Always resolve to absolute paths, even if the caller passed relative
    # ones. Graders that shell out to external tools with cwd=<worktree>
    # (e.g. S3's actionlint call) double-prefix a relative worktree path
    # against that same cwd and fail with a bogus "no such file" - resolving
    # here once fixes it for every grader, not just callers that remember to.
    return Path(args["worktree"]).resolve(), Path(args["baseline"]).resolve()
