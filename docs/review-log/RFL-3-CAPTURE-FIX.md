# RFL-3-CAPTURE-FIX — untracked-file capture in dogfood-eval.sh

**Date:** 2026-07-23
**Source:** scratchpad WORKTREE-TRIAGE-34.md finding #2 (D1 triage)
**Severity:** SILENT DATA LOSS — eval-integrity

## Problem

`dogfood-eval.sh` captures a candidate's work via `git diff`, which covers **tracked**
changes only. A candidate that creates a genuinely NEW file (created, never `git add`ed)
produces output that is:
1. Invisible to `git diff` (and therefore to the captured diff artifact)
2. Invisible to the `real-diff(files=N)` scorer (counts 0 tracked changes)
3. Permanently lost on worktree reap — exists only in the live worktree

Concrete example: RFL-3 dogfood candidates wrote `tests/test_image_routing.py` as an
untracked file. Both capture and score missed it entirely. Before this fix, only a manual
pre-archive copy-out (the `INTERIM` step in the ticket) could save such output.

## Fix

In `fleet/benchmark/dogfood-eval.sh`, the real-work check block (run_one) now:

1. Finds untracked files with `git ls-files --others --exclude-standard` (read-only,
   no index mutation — unlike `git add -N` which would modify the index)
2. Appends each untracked file to the captured diff artifact via
   `git diff --no-index /dev/null <file>` (a proper unified diff showing wholly-new content)
3. Merges untracked file paths into `diff_files` for real-diff counting and the scope check
4. Falls back to a plain header on unreadable files

## Why this approach

- **`git ls-files --others --exclude-standard`** is the canonical way to enumerate
  untracked files. It is read-only and respects `.gitignore`. Unlike `git add -N`
  (intent-to-add), it does not mutate the index/branch — a critical invariant since
  this is a read-only capture of the candidate's work.
- **`git diff --no-index /dev/null <file>`** produces a standard unified diff showing
  the file as wholly new content. Portable: works on any system with git >= 2.0.
- **Merging into the existing `diff_files` list** means real-diff counting, scope
  check, gate trigger, and overall-verdict logic all consume untracked files
  automatically — no second code path to maintain and drift.

## Alternatives considered and rejected

- `git add -N` (intent-to-add) + `git diff`: mutates the index, and requires cleanup
  (`git reset`) afterward. A failed cleanup leaks state into the candidate's worktree.
- `git stash --include-untracked`: also mutates. Cleanup surface is larger.
- Separate untracked-only artifact: creates a parallel pipeline that must be kept in
  lockstep; increases drift risk.
- `rsync` the whole worktree: captures node_modules, venvs, and other noise; not scoped
  to candidate output.

## Adversarial surface

A reviewer should verify:
1. `git ls-files --others --exclude-standard` does return files in subdirectories
   (verified: it does — paths are relative to repo root).
2. The `diff --no-index /dev/null` fallback path (on unreadable file) does not lose
   information silently — it writes a header line identifying the file as unreadable.
3. The diff_files merge `printf '%s\n%s\n' "$diff_files" "$untracked_files" | grep .`
   correctly handles edge cases: empty tracked, empty untracked, both non-empty,
   trailing newlines, and single-file output.
4. The `n_changed` recalculation after the merge uses the same `grep -c .` pattern
   as the original — no double-counting, no silent truncation.
