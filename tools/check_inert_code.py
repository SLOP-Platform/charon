#!/usr/bin/env python3
# @covers: inert
"""Inert-code gate — dead/unwired code detector, wired into the merge gate.

Adapter around KSF's ``inert_code`` detector (vendored verbatim in
``tools/_vendor/ksf_inert_code.py`` — see that module's docstring and
``tools/_vendor/README.md`` for provenance). KSF's detector builds a stdlib
``ast`` call graph of the target tree, computes reachability from real
entrypoints (``pyproject.toml`` ``[project.scripts]`` + ``__main__`` guards),
and flags any public top-level function/class with ZERO production callers
that isn't otherwise registered or annotated ``@inert_by_design`` — exactly
the "built but never wired in" bug class a hand-rolled audit previously found
(``tool_repair.py``, ``capability/actuals.py::ActualsLedger``,
``pricing_limits_checker.py``, ``engine/reconcile.py`` + ``board.set_cert()``)
before this gate existed.

Scope: Charon's product source (``src/charon``). Charon has no KSF
``module.toml`` module registrations, so the detector's "registered module"
escape hatch is deliberately never exercised here (``modules=[]``) — every
symbol must earn reachability from a real entrypoint or an explicit
``@inert_by_design`` decorator.

**Green-without-hiding**: a 0-caller symbol is not automatically a gate
failure. It must be tracked in ``tools/inert-code-disposition.json`` with a
``{reason, disposition}`` entry (``disposition`` one of ``wire``, ``delete``,
or ``keep-<why>``). Any 0-caller symbol found that is NOT in the disposition
file fails the gate immediately — so newly introduced dead code is caught on
the same push that introduces it, while already-known dead code stays
tracked with an explicit plan instead of silently accumulating between
audits.

Exit 0 on clean (or fully disposed), 1 on any undisposed dead symbol or a
malformed disposition entry.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools._vendor import ksf_inert_code as _ksf_impl  # noqa: E402
from tools._vendor.ksf_inert_code import check_inert_code  # noqa: E402

# Extend the vendored detector's _EXCLUDE_DIRS to skip local-machine / harness
# noise that pollutes the AST scan on a live dev box. The vendored module's
# header forbids hand-edits; we monkeypatch the constant in place from this
# adapter (spec: S1-GATE-INTEGRITY-SPEC §3). Add the const name as a re-vendor
# merge-survival hook so a future KSF re-vendor carries this exclusion list.
#
# - .claude       : Claude Code local session state + ephemeral agent worktrees
#                   (.claude/worktrees/agent-* is a full copy of src/, tests/,
#                   tools/, packaging/ — its symbols get namespaced into the
#                   same call graph and cause run-to-run non-determinism).
# - .worktrees    : any other local ad-hoc worktree convention.
# - .mypy_cache / .ruff_cache / .hypothesis : tool caches
# - .opencode     : opencode local state
# - dist / build / scratch : build/scratch output
# - graphify-out  : graphify local cache/output (gitignored per commit 1a1f88f)
# - .charon       : charon runtime state dir
_ksf_impl._EXCLUDE_DIRS = _ksf_impl._EXCLUDE_DIRS | {
    ".claude",
    ".worktrees",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".opencode",
    "dist",
    "build",
    "scratch",
    "graphify-out",
    ".charon",
}

DISPOSITION_PATH = REPO_ROOT / "tools" / "inert-code-disposition.json"
_VALID_DISPOSITIONS = re.compile(r"^(wire|delete|keep-.+)$")
_MESSAGE_RE = re.compile(r"^inert-code: (\S+) unreachable")


def _strip_src_prefix(sym: str) -> str:
    """KSF computes dotted module names relative to the repo root, which
    yields an ``src.charon.*`` prefix for this layout. Strip it so tracked
    symbol names read as ``charon.module.Symbol``, matching how the rest of
    the codebase refers to its own modules."""
    return sym[4:] if sym.startswith("src.") else sym


def find_dead_symbols(repo_root: Path = REPO_ROOT) -> list[str]:
    """Run the vendored KSF inert_code detector and return the sorted list of
    dead (0-caller, unregistered) symbols scoped to Charon's product source
    (``src/charon``), with the ``src.`` path prefix stripped for readability.
    """
    # check_inert_code() derives repo_root as db_path.parent.parent (KSF's
    # native shape is <repo_root>/.ksf/<db file>). Charon has no .ksf/
    # directory, so we hand it a synthetic two-levels-deep path purely for
    # that arithmetic — nothing is ever created or read at this path.
    shim_db_path = repo_root / "_ksf_shim" / "state.db"
    result = check_inert_code(db_path=shim_db_path, manifest={}, modules=[])

    dead: set[str] = set()
    for message in result.messages:
        m = _MESSAGE_RE.match(message)
        if not m:
            continue
        sym = _strip_src_prefix(m.group(1))
        if sym.startswith("charon."):
            dead.add(sym)
    return sorted(dead)


def load_dispositions() -> dict[str, dict]:
    if not DISPOSITION_PATH.exists():
        return {}
    return json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))


def validate_dispositions(dispositions: dict[str, dict]) -> list[str]:
    """Return a list of schema-violation messages (empty if all entries are
    well-formed: a non-empty 'reason' string and a 'disposition' matching
    wire|delete|keep-<why>)."""
    issues: list[str] = []
    for sym, entry in dispositions.items():
        if not isinstance(entry, dict):
            issues.append(f"{sym}: entry is not an object")
            continue
        reason = entry.get("reason")
        disposition = entry.get("disposition")
        if not isinstance(reason, str) or not reason.strip():
            issues.append(f"{sym}: missing/empty 'reason'")
        if not isinstance(disposition, str) or not _VALID_DISPOSITIONS.match(disposition):
            issues.append(
                f"{sym}: 'disposition' must be wire|delete|keep-<why>, got {disposition!r}"
            )
    return issues


def check(repo_root: Path = REPO_ROOT) -> tuple[bool, list[str], list[str], list[str]]:
    """Return (passed, undisposed_dead_symbols, all_dead_symbols, schema_issues)."""
    dead = find_dead_symbols(repo_root)
    dispositions = load_dispositions()
    schema_issues = validate_dispositions(dispositions)
    undisposed = [s for s in dead if s not in dispositions]
    passed = not undisposed and not schema_issues
    return passed, undisposed, dead, schema_issues


def main() -> int:
    passed, undisposed, dead, schema_issues = check()
    dispositions = load_dispositions()

    print(
        f"inert-code: {len(dead)} dead symbol(s) found, "
        f"{len(dead) - len(undisposed)} tracked in {DISPOSITION_PATH.name}"
    )
    for sym in dead:
        tag = dispositions.get(sym, {}).get("disposition", "UNDISPOSED")
        print(f"  [{tag}] {sym}")

    stale = sorted(set(dispositions) - set(dead))
    if stale:
        print(
            f"  (info) {len(stale)} disposition entr{'y is' if len(stale) == 1 else 'ies are'} "
            f"stale (symbol no longer dead — safe to remove from "
            f"{DISPOSITION_PATH.name}): {stale}",
            file=sys.stderr,
        )

    if schema_issues:
        print(f"\nFAIL: {DISPOSITION_PATH.name} has malformed entries:", file=sys.stderr)
        for issue in schema_issues:
            print(f"  - {issue}", file=sys.stderr)

    if undisposed:
        print(
            f"\nFAIL: {len(undisposed)} dead symbol(s) not present in "
            f"{DISPOSITION_PATH.name} — every 0-caller symbol must be tracked "
            f"with a {{reason, disposition}} entry:",
            file=sys.stderr,
        )
        for sym in undisposed:
            print(f"  - {sym}", file=sys.stderr)

    if not passed:
        return 1

    print("check_inert_code: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
