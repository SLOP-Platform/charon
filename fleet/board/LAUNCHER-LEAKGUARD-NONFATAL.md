repo: charon-private
tier: strong
priority: 1
difficulty: 3
work_class: rig-meta
branch: fix/launcher-leakguard-nonfatal
depends_on:
owns: docs/review-log/LAUNCHER-LEAKGUARD-NONFATAL.md
serial_justified: |
  Single defect, single surface. Nothing to parallelise.
substrate: N/A
substrate-novel: |
  No tool adopted. The mechanism already exists and is misconfigured or mis-wired; the novel
  slice is the correction plus the assertion that keeps it corrected.
accept: |
  MEASURED 2026-08-02, 5 tabs killed: a leak-guard REFUSAL (correctly protecting a worktree with
  unpushed commits) ends the ENTIRE self-feeding tab instead of releasing one claim and continuing.
  Log shape: 'leak-guard: REFUSING to remove ... Nothing removed' then 'cleanup: worktree KEPT'
  then the tab exits, with --wait/--retries never honoured.
  NEVER weaken leak-guard — it is protecting real work. Fix how the LAUNCHER reacts: treat the
  refusal as a per-ticket non-fatal outcome, flag it for the manager, release the claim, continue.
  PR #366 (FRONTIER-TAB-DEATH) landed the push-before-cleanup half; this is the non-fatal half.

## Dependencies & Sequence

No inbound deps. Independent of the P0 lanes; disjoint owns.
