# AUTOLAND-DEFAULT-BRANCH-FIX — review note

**Date:** 2026-07-31
**Branch:** `fix/autoland-default-branch`
**File changed:** `tests/test_autoland.py` (only)

## Problem

8/16 test_autoland.py tests failed on hosts where `git config init.defaultBranch` is `main`.
Root cause: `gitutil.init_repo()` uses `git init -q` which inherits the host's default branch.
When that is `main`, fixture repos have no `master` branch, but test helpers hard-code
`rev-parse master` and `branch="master"`.

## Fix

Override the `git_repo` fixture in `test_autoland.py` to use explicit `git init -b master`,
bypassing the shared `conftest.py` fixture. This keeps the fix scoped to one file and does
not touch `gitutil.py` (which is outside this ticket's `owns:` boundary).

## Verification

- With `init.defaultBranch=main`: **16 passed, 0 failed**
- With `init.defaultBranch=master`: **16 passed, 0 failed**
- `PYTHONPATH=src python3 -m charon.cli gate`: **all checks passed** (ruff, mypy, host-boundary, version, pytest, etc.)

## Sweep results

5 latent bugs found across `tests/` that hard-code `"master"` as a git branch name:
- `tests/test_autoland.py` — FIXED (this ticket)
- `tests/test_land.py` lines 224, 229 — not owned by this ticket
- `tests/test_work_land.py` line 111 — not owned by this ticket