# CLUSTER TRIAGE — LANE B1

## Summary
| Branch | Ticket | Age | Commits | Verdict | One-line what-it-does | PR? |
|---|---|---|---|---|---|---|
| feat/reconcile-gate-wired | RECONCILE-GATE-WIRED | 8d | 2 | LAND | Wire the built-but-inert meta-gate into preflight scan + simplify WCI advisory | — |
| feat/reconcile-board-pr-done | RECONCILE-BOARD-PR-DONE | 8d | 1 | LAND | Board-PR-done reconciler: detect merged PRs with open/missing tickets (R-A/B/C) | — |
| fix/reaper-apply-wiring | REAPER-APPLY-WIRING | 8d | 1 | LAND | Add OPEN-PR guard to branch-reaper so live-PR worktrees survive --apply | — |

> `gh` unavailable — PR status could not be confirmed. All board tickets are live (not archived, no done-marker).

## Per branch

### feat/reconcile-gate-wired
- **What it does**: Wires the meta-gate (detects built-but-inert checks — the detector was itself
  built-but-inert since its creation) into preflight.sh's scan pipeline. Also simplifies WCI
  contention from autoticketing to advisory, removes `detect_service_watchdog`, drops
  `reconcile-stale-claims.sh` from the scan pipeline, and adds `rig-meta` to VALID_AREA.
- **Evidence**: `git -C <wt> diff --name-only master...feat/reconcile-gate-wired` returns 4 files
  (+688/−93). Master's `preflight.sh` has 0 occurrences of `reconcile_gate_wired_gate`; the branch
  adds it as a full function wired into the `scan|"")` dispatch. The check script
  `fleet/checks/reconcile-gate-wired.sh` (355 loc Python3-backed) is NOT on master. Board ticket
  RECONCILE-GATE-WIRED.md is live in `fleet/board/`, priority P0, not archived. No done-marker.
  `git log master..feat/reconcile-gate-wired` shows 2 commits:
  `940bce8` "detector, no wire" → `6d4d6db` "salvage + WIRE".
- **Verdict: LAND**. The meta-gate is the SINGLE HIGHEST-LEVERAGE fix in the built-but-not-wired
  class (ticket's own words: "PRIORITY BUMPED 1→0"). Wiring it into scan makes every session see
  R-G/R-H gaps. The removals (WCI autoticketing, detect_service_watchdog) are deliberate cleanup.
  **Conflict risk: moderate** — preflight.sh has been stable on master since 7 days ago; the edit
  touches the scan dispatch line and removes ~65 lines of WCI machinery.
- **Loss if dropped**: No automated detection of built-but-inert checks ever fires. The meta-tool
  that detects unwired code stays unwired forever. Also lose the WCI simplification (the old
  autoticket machinery was noisy and nobody acted on it).

### feat/reconcile-board-pr-done
- **What it does**: Adds `fleet/checks/reconcile-board-pr-done.sh` — cross-references merged GitHub
  PRs against board tickets to detect three drift classes: R-A (open ticket whose branch matches a
  merged-but-not-done PR), R-B (merged PR with no matching ticket), R-C (open ticket, stale branch,
  no open PR — WARN). Includes AMBIGUOUS disambiguation ladder for N>1 owns-overlap.
- **Evidence**: `git -C <wt> diff --name-only master...feat/reconcile-board-pr-done` returns 3 new
  files (+377 lines). Neither the check nor test exist on master (`git ls-tree master` returns
  empty). Board ticket RECONCILE-BOARD-PR-DONE.md is live in `fleet/board/`, P1 bugfix,
  not archived. No done-marker. Commit `54e0f5d` is a launcher auto-commit ("droid exited without
  committing — review for completeness"). The test suite has 4 scenarios (a through d) with
  fail-on-revert fixtures.
- **Verdict: LAND**. Well-structured standalone check with proper AMBIGUOUS handling. **Not wired
  into preflight.sh** — this is intentional detector-first delivery: the RECONCILE-GATE-WIRED
  meta-gate (above) will discover it and flag it as built-but-inert, triggering a wiring ticket.
  This is the correct architecture per UNIFIED-RECONCILIATION-GATE-DESIGN.md §1.1. The check
  resolves a "live defect" in reconcile-merged.sh (ticket's own words).
- **Loss if dropped**: Lose the board↔PR↔done reconciler. Merged PRs with open tickets (R-A)
  and merged PRs with no ticket at all (R-B) go undetected — board drift accumulates silently.

### fix/reaper-apply-wiring
- **What it does**: Adds an OPEN-PR guard to `fleet/branch-reaper.sh`'s `_rp_keep_reason` — a
  branch with an open GitHub PR is NEVER reaped, even when pushed+clean+unclaimed. Uses `gh pr
  list --state open --head <branch>`. Fail-closed: if `gh` is unavailable or the query fails,
  treat as "has open PR" (KEEP). Configurable via `REAPER_GH_CMD` env var.
- **Evidence**: `git -C <wt> diff --name-only master...fix/reaper-apply-wiring` returns 3 files
  (+87 lines). Master's `branch-reaper.sh` has 0 occurrences of "OPEN-PR GUARD"; the branch adds
  23 lines of guard logic + 27 lines of test (scenario v: mock gh reports open PR, worktree
  SURVIVES `--apply`). The test includes a fail-on-revert check: reverting the guard causes the
  worktree to be DESTROYED. No done-marker. Board ticket: REAPER-APPLY-WIRING.md not found as a
  standalone board file; the related B4-BRANCH-REAPER is archived.
- **Verdict: LAND**. Small, focused, fail-closed safety fix with a destructive-revert test. No
  conflicts expected — the edit appends to one function. **Conflict risk: low** — master's
  branch-reaper.sh has been stable.
- **Loss if dropped**: The reaper can destroy worktrees holding branches with live PRs. This is a
  data-loss risk for any pushed, clean, unclaimed worktree whose branch happens to have an open PR.

## Recommended landing ORDER
1. **fix/reaper-apply-wiring** — lowest risk, isolated edit, safety-critical (prevents data loss)
2. **feat/reconcile-gate-wired** — moderate risk (preflight.sh edit), highest leverage (P0 meta-gate)
3. **feat/reconcile-board-pr-done** — new files only, no wiring conflicts; logically sequences
   after the meta-gate is live (the meta-gate will discover it as built-but-inert)

## Anything I could not determine
- **PR status**: `gh` unavailable in this environment — could not confirm whether open PRs already
  exist for any of these branches. An operator should check `gh pr list --repo Nnyan/charon-private
  --state open --head <branch>` for all three before landing.
- **reconcile-stale-claims removal**: The branch drops `reconcile-stale-claims.sh` from the scan
  pipeline. That script was wired in via PR #273 (`002a385`). Intentional cleanup or accidental
  deletion? The commit message says "salvage + WIRE" suggesting conscious editing, but an operator
  should verify this was deliberate.
- **REAPER-APPLY-WIRING board ticket**: No `fleet/board/REAPER-APPLY-WIRING.md` was found. The
  code is real and the review-log is present, but the board ticket may be missing or named
  differently.
