repo: charon-private
tier: strong
difficulty: 2
priority: 0
work_class: rig-meta
branch: fix/reaper-apply-wiring
owns: fleet/branch-reaper.sh, fleet/tests/branch-reaper.test.sh
depends_on:
source: scratchpad WORKTREE-REAP-REPORT.md Part A (reap-pass RCA 2026-07-23); operator directive 2026-07-23
note: |
  fleet/branch-reaper.sh is built, safe, LANDED (e4ae628/45aab71/056d94f), and wired into the
  SessionStart hook — but the hook invokes it WITHOUT --apply, so it has run DRY-RUN-ONLY every
  session forever. Reporting was mistaken for action ("I thought we had reaped these"): 17 clean
  landed/dead worktrees accumulated unreaped. This is the wired-but-inert / built-but-not-wired class.
  SECOND bug found: the worktree guard checks push-REACHABILITY, not open-PR state, so it flagged
  feat/work-lease-gate (open PR #204) for REAP — it would destroy a worktree with an open PR.
accept: |
  - fleet/branch-reaper.sh: worktree-reap guard additionally consults OPEN-PR state (gh pr list
    --state open, repo-aware) — a branch with an open PR is NEVER reaped even if push-reachable.
    Fail-closed: if PR state can't be determined, treat as "has open PR" (do not reap).
  - A SAFE --apply path that removes ONLY worktrees classified LANDED or DEAD with ZERO dirty files
    AND no open PR AND not active (live PID / session-bridge). Never force-remove; if
    `git worktree remove` refuses, SKIP + report. Branches (refs) are left intact — only worktree
    checkouts are removed.
  - fail-on-revert test (fleet/tests/branch-reaper.test.sh): (a) fixture worktree on a branch with a
    simulated OPEN PR is NOT reaped by --apply (revert the open-PR guard -> test goes RED, worktree
    wrongly reaped); (b) a LANDED+clean fixture worktree IS reaped by --apply; (c) a DIRTY fixture
    worktree is never reaped.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — DESTRUCTIVE worktree-removal tool;
    manager gates, PR does NOT merge on the builder's self-report. Fix root cause, not symptoms.
scope: |
  Harden the reaper so --apply is SAFE to run automatically. The final wiring step — adding --apply to
  the SessionStart hook invocation (~/.claude/settings.json, NOT rig-tracked) — is an operator config
  change applied ONLY AFTER this hardening lands + review passes (note in PR body). Do NOT enable
  auto-apply before the open-PR guard + fail-on-revert tests are green.
ds: |
  ## Dependencies & sequence
  Wave-1, no build prereq. Disjoint owns from the HANDOFF-* + RECONCILE-* tickets. The hook-wiring
  operator step is gated on this landing (called out in scope), so auto-apply can't fire on a still-
  buggy guard.
