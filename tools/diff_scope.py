#!/usr/bin/env python3
"""Shared diff-scoping primitives for the two diff-scoped quality gates.

WHY DIFF-SCOPED — this repo carries a large pre-existing uncovered surface
(measured 2026-08-04: 87.0% of ``src`` statements, 1736 uncovered lines). A
whole-tree coverage floor would red every PR on the day it landed and be
switched off within a week. Only lines the change ADDS or MODIFIES may block a
merge; the standing surface is reported, never gated.

WHY THIS MODULE EXISTS — both gates need the identical answer to "which lines
does this change add?", and the dangerous failure is the two of them disagreeing
(one gate scoping to a base the other never resolved). One implementation, one
base-resolution policy, one failure type.

FAIL-CLOSED POLICY — every function here raises :class:`DiffScopeError` rather
than returning an empty result when it cannot establish the truth. "I could not
work out what changed" is never "nothing changed": an unresolvable base ref, a
missing merge-base, or an untracked source file are all reasons a caller must
exit non-zero. The one exemption is a diff that is PROVABLY empty of in-scope
lines, and the caller has to print the evidence for it.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

DEFAULT_BASE = "origin/master"
BASE_ENV_VAR = "CHARON_DIFF_BASE"
# pytest exports this for the duration of every test it runs.
_PYTEST_MARKER = "PYTEST_CURRENT_TEST"

# `git diff -U0` hunk header: @@ -<old>[,<n>] +<new>[,<count>] @@
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class DiffScopeError(RuntimeError):
    """The diff could not be established. Callers MUST exit non-zero."""


def repo_root() -> Path:
    """The checkout the gate is running against (CWD, like every other gate)."""
    return Path.cwd().resolve()


def running_inside_pytest() -> bool:
    """True when this process was spawned from within a running test.

    BOTH gates in this pair launch the whole test suite as a subprocess. The
    repo's own ``test_declared_gate_emits_a_count_at_or_above_its_minimum``
    executes every registered gate script, so without this guard registering
    them would make the suite invoke itself — a fork bomb wearing a gate's
    clothes, the exact hazard the fleet self-check class documents. The guard
    only ever fires under pytest; ``gate_runner`` and CI invoke these scripts
    directly and never trip it.
    """
    return bool(os.environ.get(_PYTEST_MARKER))


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )


def resolve_base(explicit: str | None = None) -> str:
    """Return the base ref to diff against, or raise.

    Precedence: explicit argument > ``CHARON_DIFF_BASE`` > ``origin/master``.
    There is deliberately NO fallback chain — silently sliding from
    ``origin/master`` to a stale local ``master`` is how a gate ends up
    measuring a diff nobody asked for. One ref, and it must resolve.
    """
    base = explicit or os.environ.get(BASE_ENV_VAR) or DEFAULT_BASE
    probe = _git("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
    if probe.returncode != 0 or not probe.stdout.strip():
        raise DiffScopeError(
            f"base ref {base!r} does not resolve to a commit in this checkout. "
            f"In CI this usually means the checkout is shallow — actions/checkout "
            f"needs `fetch-depth: 0` so the base branch is present. Override with "
            f"${BASE_ENV_VAR} or a CLI argument."
        )
    return base


def merge_base(base: str) -> str:
    """Return the merge-base SHA of *base* and HEAD, or raise.

    An unresolvable merge-base (unrelated histories, grafted shallow clone)
    means the "lines this change adds" question has no answer at all.
    """
    result = _git("merge-base", base, "HEAD")
    sha = result.stdout.strip()
    if result.returncode != 0 or not sha:
        raise DiffScopeError(
            f"no merge-base between {base!r} and HEAD "
            f"(git exited {result.returncode}: {result.stderr.strip()!r}). "
            "The set of added lines is undefined, so this gate cannot pass."
        )
    return sha


def head_is_at_base(base_sha: str) -> bool:
    """True when HEAD IS the merge-base — i.e. nothing has been added yet.

    This is the trunk case (a push build on master). It is the only situation in
    which an empty scope is a fact rather than a measurement failure, and even
    then the caller prints the SHA it proved it against.
    """
    head = _git("rev-parse", "HEAD").stdout.strip()
    return bool(head) and head == base_sha


def untracked_python_files(pathspec: str) -> list[str]:
    """Untracked, non-ignored ``*.py`` under *pathspec*.

    ``git diff`` cannot see an untracked file, so a brand-new module that was
    never ``git add``-ed is invisible to both gates — the precise shape of "a
    new module lands with no exercising test". Callers fail closed on a non-empty
    result instead of reporting a clean diff.
    """
    result = _git("ls-files", "--others", "--exclude-standard", "--", pathspec)
    if result.returncode != 0:
        raise DiffScopeError(
            f"git ls-files failed for {pathspec!r} (exit {result.returncode}): "
            f"{result.stderr.strip()!r}"
        )
    return [line for line in result.stdout.splitlines() if line.endswith(".py")]


def changed_files(base_sha: str, pathspec: str | None = None) -> list[str]:
    """Files added or modified between *base_sha* and the WORKING TREE.

    Working tree, not HEAD: a gate run locally must see the change the developer
    is about to commit, and in CI the working tree and HEAD are identical.
    """
    args = ["diff", "--name-only", "--diff-filter=AM", base_sha]
    if pathspec:
        args += ["--", pathspec]
    result = _git(*args)
    if result.returncode != 0:
        raise DiffScopeError(
            f"git diff --name-only failed (exit {result.returncode}): "
            f"{result.stderr.strip()!r}"
        )
    return [line for line in result.stdout.splitlines() if line.strip()]


def unified_diff(base_sha: str, pathspec: str | None = None, context: int = 0) -> str:
    """The unified diff text handed verbatim to diff-cover.

    The gate feeds diff-cover THIS diff (``--diff-file``) rather than letting it
    recompute one from a branch name. Two tools independently deriving "the
    diff" is two chances to derive different diffs, and the disagreement would
    show up as an unexplained green.
    """
    args = ["diff", f"-U{context}", base_sha]
    if pathspec:
        args += ["--", pathspec]
    result = _git(*args)
    if result.returncode != 0:
        raise DiffScopeError(
            f"git diff failed (exit {result.returncode}): {result.stderr.strip()!r}"
        )
    return result.stdout


def added_lines_by_file(base_sha: str, pathspec: str | None = None) -> dict[str, set[int]]:
    """Map ``path -> {line numbers this change adds or modifies}``.

    Parsed from ``git diff -U0`` hunk headers, so it is an independent second
    opinion on the diff — the cross-check that catches diff-cover measuring
    fewer lines than the change actually contains.
    """
    text = unified_diff(base_sha, pathspec, context=0)
    added: dict[str, set[int]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = None if target == "/dev/null" else target.removeprefix("b/")
            continue
        if current is None:
            continue
        match = _HUNK_RE.match(line)
        if not match:
            continue
        start = int(match.group(1))
        count = 1 if match.group(2) is None else int(match.group(2))
        if count:
            added.setdefault(current, set()).update(range(start, start + count))
    return {path: lines for path, lines in added.items() if lines}
