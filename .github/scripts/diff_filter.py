#!/usr/bin/env python3
"""diff_filter.py — keep only scanner findings that land on lines THIS PR actually introduced.

CI-ONLY helper shared by .github/scripts/{bandit,gitleaks,semgrep}.sh. Not product code: it is
not importable from ``charon``, not on the package path, and not part of any shipped artifact.

WHY IT EXISTS. A merge-blocking scanner must block on NEW findings only. The obvious
approximation — "scan the files the PR changed" — is FILE-scoped, not LINE-scoped, so it reds on
findings that were already on master the moment anyone edits an unrelated line of the same file.
Measured on master 2026-08-04: bandit reports 4 pre-existing findings across
``src/charon/{acceptance,connect,land,gateway}.py`` and gitleaks reports 12 pre-existing findings
across 7 files under ``tests/`` (synthetic key-shaped strings those tests exist to contain). Under
file scoping, every PR touching any of those hot files would red on somebody else's finding — and
a gate that reds on untouched code is a gate that gets switched off.

TWO FILTERS, BOTH REQUIRED:

1. LINE SCOPE. A finding blocks only if it overlaps a line the diff ADDED.

   The diff is parsed with a HUNK-BUDGET state machine, NOT by pattern-matching ``+++ `` at line
   start. That naive test cannot distinguish a file header from an ADDED CONTENT LINE whose text
   begins with ``++ `` (git renders that as ``+++ ...``), so a single ``++ sample`` line anywhere
   in a PR silently re-attributed or DROPPED every later hunk of that file — proven end-to-end to
   turn a real bandit/gitleaks/semgrep RED into a green. Here, ``diff --git `` starts a file
   section (a body line carrying that text renders as ``+diff --git ``, so it can never be
   confused), ``+++ `` is honoured as a header ONLY outside a hunk body, and each ``@@`` hunk
   consumes exactly its declared old+new line count as body. Body lines are counted, never
   interpreted as structure.

2. MOVED / REFORMATTED PRE-EXISTING FINDINGS. A line the diff "added" is not necessarily new
   code: ``ruff format``, a reindent, or moving a function re-emits an untouched pre-existing
   finding as ADDED, which reds the gate on somebody else's finding — the over-red that gets
   gates disabled. So a finding is dropped when the STRIPPED TEXT of its line already existed
   somewhere in that file at the merge base. Deliberate trade-off: an added line whose stripped
   text is byte-identical to a line already in that file is treated as pre-existing. That is
   sound for this purpose — if the identical construct is already in the file, the file already
   carries that finding, and the gate's job is new findings, not a census.

FAIL-CLOSED. Every failure path exits 2, never 0:
  * merge-base cannot be resolved (a shallow checkout — the classic silent-green cause),
  * ``git diff`` / ``git show`` fails,
  * the scanner report is missing / not parseable JSON,
  * an unknown --kind.
A green from this module always means "a real report was parsed and nothing survived filtering".

Usage:
    <scanner> --json ... | python3 diff_filter.py --kind {bandit,gitleaks,semgrep} \\
        --base <ref> --head <ref> --root <repo-root> [--exclude-prefix P]...

Writes surviving findings to stderr (human-readable), the surviving count to stdout.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

_HUNK_RE = re.compile(r"^@@+ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _die(msg: str) -> None:
    print(f"diff_filter: FAIL — {msg}; failing closed.", file=sys.stderr)
    raise SystemExit(2)


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    # core.quotePath=false is LOAD-BEARING: with git's default, any path containing a non-ASCII
    # byte comes back C-quoted ("na\303\257ve.txt"), which then matches nothing and silently drops
    # that file's findings.
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", root, *args],
        capture_output=True, text=True, check=False,
    )


def merge_base(base: str, head: str, root: str) -> str:
    mb = _git(root, "merge-base", base, head)
    if mb.returncode != 0 or not mb.stdout.strip():
        _die(f"cannot resolve merge-base({base},{head}) — a shallow checkout cannot be scoped")
    return mb.stdout.strip()


def added_lines(mb: str, head: str, root: str) -> dict[str, set[int]]:
    """Return {repo-relative path: set of line numbers ADDED between *mb* and *head*}.

    Hunk-budget state machine — see this module's docstring for why a naive ``+++ ``/``@@`` scan
    is exploitable. ``-U0`` keeps hunk bodies free of context lines.
    """
    proc = _git(root, "diff", "-U0", "--no-color", "--diff-filter=ACMR", mb, head)
    if proc.returncode != 0:
        _die(f"git diff failed (rc={proc.returncode}): {proc.stderr.strip()[:200]}")

    out: dict[str, set[int]] = {}
    path: str | None = None
    budget = 0          # remaining BODY lines of the current hunk
    next_added = 0      # line number the next added ('+') body line will occupy
    for line in proc.stdout.split("\n"):
        if budget == 0:
            # ── structural region: file-section markers and hunk headers only ──
            if line.startswith("diff --git "):
                path, next_added = None, 0
                continue
            if line.startswith("+++ "):
                target = line[4:].strip()
                if target == "/dev/null":
                    path = None
                else:
                    path = target[2:] if target[:2] in ("b/", "a/") else target
                continue
            m = _HUNK_RE.match(line)
            if m:
                old_count = int(m.group(2)) if m.group(2) is not None else 1
                new_start = int(m.group(3))
                new_count = int(m.group(4)) if m.group(4) is not None else 1
                budget = old_count + new_count
                next_added = new_start
            continue
        # ── hunk body: consume exactly `budget` lines, never re-read them as structure ──
        if line.startswith("\\"):        # "\ No newline at end of file" is not a body line
            continue
        if line.startswith("+"):
            if path is not None:
                out.setdefault(path, set()).add(next_added)
            next_added += 1
        budget -= 1
    return out


def base_lines(mb: str, root: str, paths: set[str]) -> dict[str, set[str]]:
    """Return {path: set of STRIPPED source lines that file held at the merge base}."""
    out: dict[str, set[str]] = {}
    for p in paths:
        proc = _git(root, "show", f"{mb}:{p}")
        if proc.returncode != 0:      # file did not exist at base — everything in it is new
            out[p] = set()
            continue
        out[p] = {ln.strip() for ln in proc.stdout.split("\n") if ln.strip()}
    return out


def head_lines(root: str, paths: set[str], head: str) -> dict[str, list[str]]:
    """Return {path: list of source lines at *head*} (1-based indexing via [n-1])."""
    out: dict[str, list[str]] = {}
    for p in paths:
        proc = _git(root, "show", f"{head}:{p}")
        if proc.returncode != 0:
            _die(f"cannot read {p} at {head}")
        out[p] = proc.stdout.split("\n")
    return out


def _rel(path: str, root: str) -> str:
    """Normalize a scanner-reported path to a repo-relative path."""
    p = path
    if p.startswith(root.rstrip("/") + "/"):
        p = p[len(root.rstrip("/")) + 1:]
    if p.startswith("./"):
        p = p[2:]
    return p


def normalize(kind: str, report: object, root: str) -> list[tuple[str, range, str]]:
    """Return [(rel_path, line_range, human_description)] for every finding in *report*."""
    findings: list[tuple[str, range, str]] = []
    if kind == "bandit":
        if not isinstance(report, dict):
            _die("bandit report is not a JSON object")
        for r in report.get("results", []):
            lines = r.get("line_range") or [r.get("line_number", 0)]
            lo, hi = min(lines), max(lines)
            findings.append((
                _rel(str(r.get("filename", "")), root), range(lo, hi + 1),
                f"{r.get('issue_severity')}/{r.get('issue_confidence')}  {r.get('test_id')} "
                f"{r.get('test_name')}  {r.get('filename')}:{r.get('line_number')}  "
                f"{r.get('issue_text')}",
            ))
    elif kind == "gitleaks":
        if not isinstance(report, list):
            _die("gitleaks report is not a JSON array")
        for r in report:
            lo = int(r.get("StartLine", 0))
            hi = int(r.get("EndLine", lo) or lo)
            findings.append((
                _rel(str(r.get("File", "")), root), range(lo, hi + 1),
                f"{r.get('RuleID')}  {r.get('File')}:{lo}  {r.get('Description')}",
            ))
    elif kind == "semgrep":
        if not isinstance(report, dict):
            _die("semgrep report is not a JSON object")
        for r in report.get("results", []):
            lo = int(r.get("start", {}).get("line", 0))
            hi = int(r.get("end", {}).get("line", lo) or lo)
            msg = str(r.get("extra", {}).get("message", "")).strip().replace("\n", " ")
            findings.append((
                _rel(str(r.get("path", "")), root), range(lo, hi + 1),
                f"{r.get('check_id')}  {r.get('path')}:{lo}  {msg[:160]}",
            ))
    else:
        _die(f"unknown --kind {kind!r}")
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", required=True, choices=("bandit", "gitleaks", "semgrep"))
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--exclude-prefix", action="append", default=[],
                    help="repo-relative path prefix whose findings never block (repeatable)")
    args = ap.parse_args(argv)

    raw = sys.stdin.read()
    if not raw.strip():
        _die(f"{args.kind} produced an EMPTY report (crash?) — a no-report run is not a green")
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        _die(f"{args.kind} report is not parseable JSON ({exc})")

    mb = merge_base(args.base, args.head, args.root)
    added = added_lines(mb, args.head, args.root)
    for pref in args.exclude_prefix:
        for p in list(added):
            if p.startswith(pref):
                del added[p]

    candidates = [
        (rel, rng, desc)
        for rel, rng, desc in normalize(args.kind, report, args.root)
        if added.get(rel) and any(ln in added[rel] for ln in rng)
    ]

    # Filter 2 — drop findings whose source line already existed in that file at the merge base
    # (a move / reindent / reformat re-emits an untouched pre-existing finding as ADDED).
    kept: list[str] = []
    if candidates:
        touched = {rel for rel, _, _ in candidates}
        before = base_lines(mb, args.root, touched)
        now = head_lines(args.root, touched, args.head)
        for rel, rng, desc in candidates:
            texts = {
                now[rel][ln - 1].strip()
                for ln in rng
                if 0 < ln <= len(now[rel]) and now[rel][ln - 1].strip()
            }
            if texts and texts <= before.get(rel, set()):
                print(f"  (pre-existing, moved/reformatted — not blocking) {desc}", file=sys.stderr)
                continue
            kept.append(desc)

    for desc in kept:
        print(f"  {desc}", file=sys.stderr)
    print(len(kept))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
