# CLOSED-PR-UNLANDED-TRIAGE — review/decision note

**Date:** 2026-08-01
**Ticket:** CLOSED-PR-UNLANDED-TRIAGE
**Method:** git cherry + git merge-base --is-ancestor per branch

## Decision

| Class | Count | Action |
|-------|-------|--------|
| (a) DELIBERATE | 2 | None — partial supersession, content landed |
| (b) SQUASH_ARTEFACT | 3 | None — content on master via different commit |
| (c) SILENTLY_DISCARDED_WORK | 53 | Recorded as dropped — see rationale below |

## Key findings

1. **docs/adr-0017-amend (#179)**: cherry shows `-` (equivalent commit on master). The commit on master has the same patch-id as the branch commit. The content landed via PR #180 (same ADR amended again), not the original PR. This is a genuine squash-merge artefact — correct.

2. **feat/unified-plane-canary-framework (#260)** and **feat/reconcile-gate-wired (#211)**: These show "no commits ahead of master" in the local checkout because the branches are identical to master. The detector reported them because the GitHub PR was closed. Both are (b) — stale PR state, no work lost.

3. **feat/memory-index-compaction (#104)**: cherry shows 1 landed + 1 orphaned — partial supersession. The orphaned commit was dropped deliberately as part of the later rework.

4. **All 53 (c) entries**: git cherry returns all `+` (no equivalent on master); git merge-base --is-ancestor returns false for every commit. No evidence of supersession. These are genuinely orphaned branches.

5. **Duplicate branch names** (reviewer-tab-pool ×3, fixture-bypass-gate ×3, ci-suites-canary ×2, etc.): Each duplicate PR had the same branch at different points in time. The stranded-work detector correctly surfaces each PR as a separate entry, but the branch is the same. All instances of the same branch share the same fate.

## Drop rationale for (c)

The 53 (c) entries are recorded as dropped because:
- Most represent stale work from abandoned or completed feature streams
- The git evidence shows no content landed through any path
- Reopening would require reconstructive context a robot cannot supply
- A human (manager) should review the most substantial ones (console-provider-mgmt: 6 commits, fixture-bypass-gate: 5 commits × 3 PRs, etc.) before deciding to reopen

## Supersession map observations

- Same-branch duplicates (fixture-bypass-gate, reviewer-tab-pool, workloop-stack-spike-run) appear to have been attempted multiple times then abandoned — each PR shows the same orphaned commits, confirming the work was never landed.
- The pattern of multiple PRs for the same branch suggests iterative attempts that all failed to land.
- No evidence was found of any (c) work being successfully landed via a different branch name.
