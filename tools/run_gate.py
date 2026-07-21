#!/usr/bin/env python3
"""Repo-local CHARON-GATE entrypoint. Run this, not the installed console script.

    python3 tools/run_gate.py

WHY A SECOND ENTRYPOINT EXISTS. ``charon gate`` (and ``python3 -m charon.cli
gate``) resolve the ``charon`` package through Python's normal import machinery.
Under the editable install this repo uses, that resolves to whichever checkout
was ``pip install -e``'d — normally the main one, on the default branch. But
``gate_runner.CHECKS`` shells ``python3 tools/check_*.py`` **CWD-relative**. Run
from a git worktree, the check LIST therefore came from the main checkout while
the check SCRIPTS came from the worktree: a gate added on the branch was not in
the list that ran, and the run still printed "all checks passed".

That produced real false receipts. Several rounds of a security fix were declared
locally green having never once invoked the gate they were adding.

This script fixes it structurally rather than by remembering: it derives the repo
root from its own location, puts that root's ``src/`` at the FRONT of
``sys.path``, and chdir's there. A file at ``<root>/tools/run_gate.py`` cannot
resolve to a different checkout than ``<root>``, so the two halves are always
from the same commit. ``gate_runner._verify_same_tree()`` re-asserts this at
runtime, so the guarantee is checked rather than assumed.

Stdlib only; no install required.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    src = REPO_ROOT / "src"
    if not (src / "charon" / "gate_runner.py").is_file():
        print(
            f"run_gate: {src}/charon/gate_runner.py not found — "
            f"{REPO_ROOT} does not look like a charon checkout",
            file=sys.stderr,
        )
        return 2

    # FRONT of sys.path, so this checkout wins over any installed charon.
    sys.path.insert(0, str(src))
    os.chdir(REPO_ROOT)

    from charon import gate_runner

    # Belt and braces: if some earlier sys.path entry still shadowed us, say so
    # rather than run the wrong tree's check list.
    loaded = Path(gate_runner.__file__).resolve()
    expected = (src / "charon" / "gate_runner.py").resolve()
    if loaded != expected:
        print(
            f"run_gate: imported gate_runner from {loaded}, expected {expected}. "
            "Refusing to run a different checkout's check list.",
            file=sys.stderr,
        )
        return 2

    return gate_runner.run_gate()


if __name__ == "__main__":
    raise SystemExit(main())
