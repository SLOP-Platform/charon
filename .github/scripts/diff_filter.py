#!/usr/bin/env python3
"""diff_filter.py — keep only scanner findings that land on lines THIS PR added.

CI-ONLY helper shared by .github/scripts/{bandit,gitleaks,semgrep}.sh. Not product code: it is
not importable from ``charon``, not on the package path, and not part of any shipped artifact.

WHY IT EXISTS. A merge-blocking scanner must block on NEW findings only. The obvious
approximation — "scan the files the PR changed" — is FILE-scoped, not LINE-scoped, so it reds on
findings that were already on master the moment anyone edits an unrelated line of the same file.
Measured on master 2026-08-04: bandit reports 4 pre-existing findings across
``src/charon/{acceptance,connect,land,gateway}.py`` and gitleaks reports 10 pre-existing findings
across 8 files under ``tests/`` (synthetic key-shaped strings those tests exist to contain). Under
file scoping, every PR touching any of those hot files would red on somebody else's finding — and
a gate that reds on untouched code is a gate that gets switched off. This module makes the
scoping LINE-exact: a finding blocks iff it overlaps a line the diff ADDED.

FAIL-CLOSED. Every failure path exits 2, never 0:
  * merge-base cannot be resolved (a shallow checkout — the classic silent-green cause),
  * ``git diff`` fails,
  * the scanner report is missing / not parseable JSON,
  * an unknown --kind.
A green from this module always means "a real report was parsed and nothing survived filtering".

Usage:
    <scanner> --json ... | python3 diff_filter.py --kind {bandit,gitleaks,semgrep} \\
        --base <ref> --head <ref> --root <repo-root>

Writes surviving findings to stderr (human-readable), the surviving count to stdout.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _die(msg: str) -> None:
    print(f"diff_filter: FAIL — {msg}; failing closed.", file=sys.stderr)
    raise SystemExit(2)


def added_lines(base: str, head: str, root: str) -> dict[str, set[int]]:
    """Return {repo-relative path: set of line numbers ADDED between base and head}.

    Uses ``git diff -U0`` so hunk headers describe exactly the changed lines with no context
    padding. A file added wholesale yields all of its lines, so a brand-new file is fully in
    scope.
    """
    mb = subprocess.run(
        ["git", "-C", root, "merge-base", base, head],
        capture_output=True, text=True, check=False,
    )
    if mb.returncode != 0 or not mb.stdout.strip():
        _die(f"cannot resolve merge-base({base},{head}) — a shallow checkout cannot be scoped")
    proc = subprocess.run(
        ["git", "-C", root, "diff", "-U0", "--diff-filter=ACMR", mb.stdout.strip(), head],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        _die(f"git diff failed (rc={proc.returncode}): {proc.stderr.strip()[:200]}")

    out: dict[str, set[int]] = {}
    path: str | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            path = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
            continue
        if path is None:
            continue
        m = _HUNK_RE.match(line)
        if m:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count:
                out.setdefault(path, set()).update(range(start, start + count))
    return out


def _rel(path: str, root: str) -> str:
    """Normalize a scanner-reported path to a repo-relative path."""
    p = path
    if p.startswith("./"):
        p = p[2:]
    if p.startswith(root.rstrip("/") + "/"):
        p = p[len(root.rstrip("/")) + 1:]
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
    args = ap.parse_args(argv)

    raw = sys.stdin.read()
    if not raw.strip():
        _die(f"{args.kind} produced an EMPTY report (crash?) — a no-report run is not a green")
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        _die(f"{args.kind} report is not parseable JSON ({exc})")

    added = added_lines(args.base, args.head, args.root)
    kept = [
        desc for rel, rng, desc in normalize(args.kind, report, args.root)
        if added.get(rel) and any(ln in added[rel] for ln in rng)
    ]
    for desc in kept:
        print(f"  {desc}", file=sys.stderr)
    print(len(kept))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
