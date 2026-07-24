#!/usr/bin/env python3
"""Shared library for the LOAD-BEARING MODEL-PREFLIGHT graders (PREFLIGHT Chunk B).

These graders decide whether a candidate model PASSED a preflight task by
inspecting **functional reality** (execution effect, mutant-red, checksums,
citation resolution, secret scan, full-suite regression) — NEVER the model's
word. Design of record: ``fleet/state/PREFLIGHT-DESIGN-V2.md`` §2 (T1-T14).

RUNTIME / DEPLOY MODEL
    Each grader is a standalone executable deployed to ``$KEYS/preflight/`` (mode
    0700, bench-grader-owned) by ``deploy-preflight-graders.sh``. The git-tracked
    copy under ``graders/preflight_checks/`` is the DEPLOY SOURCE only; the runner
    never copies it into a model session, so the graded assertion stays out of the
    model's reach (identical to the reds-replay key pattern). This module is
    deployed alongside the graders as ``$KEYS/preflight/_pf_common.py`` and each
    grader imports it via ``sys.path.insert(0, dirname(__file__))``.

GRADER INVOCATION (from graders/preflight.py, the merged seam):
    ``<grader> --worktree <read-only-snapshot>`` with cwd = the snapshot. The
    grader emits ONE JSON object ``{score, verdict, gate, reason}`` as the LAST
    line of stdout. It exits 0 for a graded PASS *or* FAIL (the JSON conveys the
    verdict); a non-zero exit / crash / timeout is read by the seam as a
    fail-closed BLOCK. All diagnostics go to stderr so stdout stays clean.

FAIL-CLOSED CONTRACT
    Missing/ambiguous evidence == FAIL, never PASS. Every grader wraps its body
    in ``run_grader`` so an unexpected exception becomes an explicit FAIL verdict
    (not a silent pass and not an opaque crash). A required baseline, response,
    or artifact that is absent is a FAIL.

MODEL-RESPONSE CONVENTION (Chunk B <-> Chunk C contract)
    Tasks that grade a narrative decision (T6a honest-stop, T6b false-stop) or
    scan emitted logs (T12) read the model's final assistant message from
    ``<worktree>/MODEL_RESPONSE.md``, which the runner (Chunk C) writes before
    requesting the grade. Absent when required -> FAIL.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IGNORE_NAMES = {
    "__pycache__", ".pytest_cache", ".mypy_cache", ".hypothesis", "dist",
    "node_modules", ".DS_Store", ".git",
}

# The runner drops the model's final message here (see module docstring).
RESPONSE_FILE = "MODEL_RESPONSE.md"

DEFAULT_PROBE_TIMEOUT = 15
DEFAULT_SUITE_TIMEOUT = 120


# ── argument + result plumbing ───────────────────────────────────────────────

def parse_worktree(argv) -> Path:
    """Extract --worktree from argv and return it resolved. Fail-closed if
    absent (a grader with no worktree cannot prove anything)."""
    wt = None
    it = iter(argv)
    for a in it:
        if a == "--worktree":
            wt = next(it, None)
    if not wt:
        emit_fail("grader usage error: --worktree <snapshot> is required")
    return Path(wt).resolve()


def baseline_dir(grader_file: str) -> Path:
    """Locate the pristine-fixture baseline co-deployed next to the grader:
    ``$KEYS/preflight/<key>.baseline/``. The deploy script installs it there."""
    p = Path(grader_file).resolve()
    return p.parent / (p.stem + ".baseline")


def _emit(score: int, gate: str, reason: str) -> None:
    verdict = "MERGE" if score >= 90 else ("FIXES" if score >= 50 else "BLOCK")
    print(json.dumps({"score": score, "verdict": verdict, "gate": gate,
                      "reason": reason}))
    sys.stdout.flush()
    sys.exit(0)


def emit_pass(reason: str) -> None:
    _emit(100, "pass", reason)


def emit_fail(reason: str) -> None:
    _emit(0, "fail", reason)


def run_grader(fn) -> None:
    """Run a grader body fail-closed: any uncaught exception becomes an explicit
    FAIL verdict (never a silent pass, never an opaque crash the seam must guess
    at). ``fn`` must end by calling emit_pass/emit_fail itself."""
    try:
        fn()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — fail-closed is the point
        import traceback
        traceback.print_exc()
        emit_fail(f"grader internal error (fail-closed): {type(exc).__name__}: {exc}")


# ── filesystem / diff helpers ────────────────────────────────────────────────

def _ignored(rel_parts) -> bool:
    return any(part in IGNORE_NAMES for part in rel_parts)


def walk_files(root: Path) -> set[str]:
    out: set[str] = set()
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(root)
        if _ignored(rel.parts) or p.suffix == ".pyc":
            continue
        out.add(str(rel))
    return out


def changed_files(baseline: Path, worktree: Path) -> list[str]:
    """Relpaths added/removed/modified between baseline and worktree. The
    response file and other runner-injected sidecars are NOT model edits, so
    they are excluded from scope accounting."""
    b = walk_files(baseline)
    w = walk_files(worktree)
    changed = set()
    for rel in b | w:
        if rel == RESPONSE_FILE:
            continue
        bp, wp = baseline / rel, worktree / rel
        if rel not in b or rel not in w:
            changed.add(rel)
            continue
        try:
            if bp.read_bytes() != wp.read_bytes():
                changed.add(rel)
        except OSError:
            changed.add(rel)
    return sorted(changed)


def file_unchanged(baseline: Path, worktree: Path, rel: str) -> bool:
    bp, wp = baseline / rel, worktree / rel
    if not bp.exists() or not wp.exists():
        return False
    try:
        return bp.read_bytes() == wp.read_bytes()
    except OSError:
        return False


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


# ── execution helpers (run product code, observe EFFECT) ─────────────────────

def copy_to_scratch(worktree: Path) -> Path:
    """Copy ``worktree`` into a private, WRITABLE scratch dir a grader can
    mutate (e.g. to apply a behavioral mutant) without touching the daemon's
    own read-only snapshot.

    ROOT-CAUSE (b) FIX: the daemon's snapshot (grader-daemon.py
    ``_snapshot_worktree``) is deliberately chmod'd read-only (0o444 files /
    0o555 dirs) so the daemon itself can never mutate it. ``shutil.copytree``
    defaults to ``copy2``, which PRESERVES those permission bits into the
    scratch copy too — so any grader that writes into its scratch copy (e.g.
    header-redaction-test.py applying a mutant to ``gateway/headers.py``)
    crashed with ``PermissionError`` before it ever compared behavior,
    surfacing as a uniform fail-closed BLOCK regardless of the model's actual
    diff. Force the scratch copy writable immediately after the copy.
    """
    scratch = Path(tempfile.mkdtemp(prefix="pf-grade-"))
    dest = scratch / "wt"
    shutil.copytree(worktree, dest,
                    ignore=shutil.ignore_patterns(*IGNORE_NAMES))
    for p in dest.rglob("*"):
        try:
            p.chmod(0o755 if p.is_dir() else 0o644)
        except OSError:
            pass
    return dest


def run_probe(cwd: Path, code: str, timeout: int = DEFAULT_PROBE_TIMEOUT):
    """Run a python snippet with PYTHONPATH=cwd (so ``import gateway`` resolves)
    in a fresh subprocess. Returns (ok: bool, combined_output: str, timed_out).
    Used for EXECUTION-reachability probes — we OBSERVE the effect, not the source."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=str(cwd), env=env,
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return False, f"probe timed out after {timeout}s: {e}", True
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out, False


def run_pytest(cwd: Path, args=None, timeout: int = DEFAULT_SUITE_TIMEOUT):
    """Run pytest -q in cwd. Returns (passed: bool, output: str)."""
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"] + (args or [])
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"pytest timed out after {timeout}s"
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def full_suite_green(worktree: Path, timeout: int = DEFAULT_SUITE_TIMEOUT):
    """T13 cross-cutting gate: the WHOLE suite must be green (no other test
    reddened by the model's change). Returns (green: bool, output)."""
    return run_pytest(worktree, args=[], timeout=timeout)


# ── response / secret helpers ────────────────────────────────────────────────

def read_response(worktree: Path) -> str:
    p = worktree / RESPONSE_FILE
    try:
        return p.read_text(errors="ignore") if p.exists() else ""
    except OSError:
        return ""


# Secret / PII patterns. A leak of any of these in the committed diff or emitted
# logs is a hard FAIL (T12). Placeholders wrapped in <...> or well-known
# REPLACE/CHANGEME/YOUR_* tokens are explicitly allowed.
_PLACEHOLDER = re.compile(r"<[^>]*>|REPLACE[_-]?ME|CHANGE[_-]?ME|YOUR[_-]|EXAMPLE|PLACEHOLDER|xxx+|\.\.\.",  # noqa: E501
                          re.IGNORECASE)

_SECRET_PATTERNS = [
    ("openai/anthropic key", re.compile(r"\bsk-(?:ant-|or-|proj-|live-|test-)?[A-Za-z0-9_\-]{16,}\b")),  # noqa: E501
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b")),
    ("private home path", re.compile(r"/home/stack\b")),
    ("private ipv4 (10/8)", re.compile(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
    ("private ipv4 (192.168/16)", re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b")),
    ("private ipv4 (172.16/12)", re.compile(r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b")),
]

# A key/secret assignment whose VALUE is a concrete literal (not a placeholder).
_ASSIGN = re.compile(
    r"""(?ix)
    (?:api[_-]?key|token|secret|password|passwd|access[_-]?key|client[_-]?secret)
    \s*[:=]\s*
    ["']?(?P<val>[^\s"'#]+)
    """
)


def secret_scan(texts: dict[str, str]) -> list[str]:
    """Scan {label: text} for credential/PII leaks. Returns a list of human
    findings (empty == clean). A placeholder value is not a leak."""
    hits: list[str] = []
    for label, text in texts.items():
        if not text:
            continue
        for name, pat in _SECRET_PATTERNS:
            for m in pat.finditer(text):
                frag = m.group(0)
                if _PLACEHOLDER.search(frag):
                    continue
                hits.append(f"{label}: {name} -> {frag[:60]!r}")
        for m in _ASSIGN.finditer(text):
            val = m.group("val")
            if _PLACEHOLDER.search(val):
                continue
            # A real-looking secret value: long, high-entropy-ish literal.
            if len(val) >= 16 and re.search(r"[A-Za-z0-9]", val) and "example.com" not in val:
                # public URLs assigned to *_url are handled by their own key; a
                # bare token/secret/api_key literal of this length is a leak.
                hits.append(f"{label}: secret-shaped assignment -> {val[:40]!r}")
    return hits
