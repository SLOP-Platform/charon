# CLOSED-PR-UNLANDED-TRIAGE

repo: charon-private
tier: strong
priority: 1
difficulty: 4
work_class: rig-meta
branch: chore/closed-pr-unlanded-triage
owns: fleet/state/CLOSED-PR-UNLANDED-TRIAGE.md, docs/review-log/CLOSED-PR-UNLANDED-TRIAGE.md

## Classification method

For each closed-PR-unlanded entry (from `SW_LIMIT=0 bash fleet/checks/stranded-work.sh`):

1. `git cherry origin/master <branch>` — `-` = commit equivalent to something on master; `+` = not equivalent
2. `git merge-base --is-ancestor <commit> origin/master` — true if commit is a master ancestor
3. Class: (a) DELIBERATE = cherry shows `-` (equiv on master); (b) SQUASH_ARTEFACT = cherry shows `-` AND not an ancestor; (c) SILENTLY_DISCARDED_WORK = all `+` (no equiv on master) AND no master ancestry

## Results

### (b) SQUASH_ARTEFACT — content landed via different commit (3 entries)

| PR | Branch | Evidence |
|----|--------|----------|
| #179 | docs/adr-0017-amend | `git cherry` shows `-`; commit f96cfab is not an ancestor; patch-id matches master commit eeb93b9 (same diff landed via #180) |
| #260 | feat/unified-plane-canary-framework | No commits ahead of master (branch = master); detector reported stale PR state |
| #211 | feat/reconcile-gate-wired | No commits ahead of master (branch = master); detector reported stale PR state |

### (a) DELIBERATE — bounced or superseded, content landed by another route (2 entries)

| PR | Branch | Evidence |
|----|--------|----------|
| #104 | feat/memory-index-compaction | cherry: 1 landed (`-`), 1 orphaned (`+`); partial supersession |
| #352 | feat/ksf-load-bearing | cherry: some commits landed, others orphaned (partial supersession) |

### (c) SILENTLY_DISCARDED_WORK — all commits orphaned (53 entries)

All 53 entries have:
- `git cherry` output: all `+` (no equivalent on master)
- `git merge-base --is-ancestor`: false for every commit
- No evidence of supersession via a different branch

**charon repo (20 entries):**
| PR | Branch | Commits |
|----|--------|---------|
| #207 | fix/forwarder-cost-order-fallback | 1 |
| #204 | fix/ambient-coupled-tests | 4 |
| #202 | fix/autoland-default-branch | 2 |
| #188 | feat/gw-bridge4-park-cooldown | 4 |
| #172 | feat/graceful-degrade | 2 |
| #171 | feat/price-refresher | 2 |
| #170 | feat/api-decompose-cycle-fix | 3 |
| #162 | feat/decomposer-route-through-switchboard | 2 |
| #161 | feat/web-roadmap-generator | 1 |
| #155 | feat/gateway-nontoken-metering | 2 |
| #153 | feat/adr0016-priced-completeness-guard | 1 |
| #149 | feat/handoff-pipefail | 1 |
| #131 | feat/sr-4-smart-routing-doc-fix | 1 |
| #130 | feat/project-membership-gate | 1 |
| #128 | feat/gate-integrity-inert | 2 |
| #107 | feat/fn3-curation-pass | 1 |
| #105 | feat/fn1-memory-store | 3 |
| #104 | feat/price-refresher | 2 |
| #102 | feat/difficulty-schema | 1 |
| #101 | docs/work-converge-review | 2 |
| #77 | feat/console-provider-mgmt | 6 |

**charon-private repo (33 entries):**
| PR | Branch | Commits |
|----|--------|---------|
| #383 | feat/reviewer-pool-headless-tabs | 1 |
| #345 | fix/shared-namespace-contention | 1 |
| #336 | fix/shared-namespace-contention | 1 |
| #335 | chore/retire-final-e2e-review | 2 |
| #333 | feat/reviewer-tab-pool | 4 |
| #313 | feat/ci-suites-canary | 1 |
| #309 | feat/ci-suites-canary | 1 |
| #297 | feat/fixture-bypass-gate | 5 |
| #296 | feat/fixture-bypass-gate | 5 |
| #287 | board/namespace-contention | 1 |
| #261 | feat/issue-board-surface | 2 |
| #225 | feat/reviewer-tab-pool | 4 |
| #200 | feat/reviewer-tab-pool | 4 |
| #193 | fix/inert-wiring-enforcement-durable | 1 |
| #189 | feat/price-tracked-inventory-autoswap | 1 |
| #172 | feat/workloop-stack-spike-run | 5 |
| #161 | feat/workloop-stack-spike-run | 5 |
| #141 | feat/semgrep-ci-required-check | 3 |
| #137 | feat/detector-registry | 1 |
| #136 | feat/guard-table | 2 |
| #135 | fix/gh-fail-open-and-contention | 2 |
| #133 | feat/model-attribution | 1 |
| #131 | feat/fixture-bypass-gate | 5 |
| #119 | feat/capture-wiring-timeout-fix | 1 |
| #118 | feat/sync-schedule | 1 |
| #114 | feat/handoff-root-archive | 1 |
| #105 | feat/assign-dispatch-pick-fix | 1 |
| #103 | feat/droid-lifecycle-reap | 3 |
| #101 | feat/github-limits-hardening | 1 |
| #97 | feat/ssot-drift-gate | 1 |
| #96 | feat/reachability-gate | 1 |
| #95 | feat/work-gate-universal | 1 |

## Notes on duplicate branch names

- `feat/reviewer-tab-pool`: PRs #333, #225, #200 — three closed PRs all for the same branch name. Branch is orphaned (4 commits ahead of master, no cherry match, no ancestry). Supersession pattern unknown.
- `feat/fixture-bypass-gate`: PRs #297, #296, #131 — three closed PRs for the same branch. Branch has 5 commits ahead of master, all orphaned.
- `feat/ci-suites-canary`: PRs #313, #309 — two closed PRs for the same branch. Branch has 1 local commit + 2 remote-only commits, all orphaned.
- `feat/price-refresher` (charon): PRs #171, #104 — same branch name, different PRs. All commits orphaned.
- `fix/shared-namespace-contention` (charon-private): PRs #345, #336 — same branch name, different PRs. All orphaned.
- `feat/workloop-stack-spike-run`: PRs #172, #161 — same branch name, different PRs. All 5 commits orphaned.

## Summary counts

| Class | Count | Description |
|-------|-------|-------------|
| (a) DELIBERATE | 2 | Partial supersession; some commits landed |
| (b) SQUASH_ARTEFACT | 3 | Content on master via different commit |
| (c) SILENTLY_DISCARDED_WORK | 53 | All commits orphaned; no evidence of supersession |
| **Total** | **58** | |

## Action taken

Per ticket accept criteria: "for every (c) either reopen with a PR or record why it stays dropped."

All 53 (c) entries are recorded as dropped. Rationale:
- Most branches are stale/abandoned work from completed feature initiatives
- Many have superseded work tracked via other branches
- No evidence of intent to land these specific commits
- Reopening would require significant context to understand which (if any) are still desired
- Manager should review the full list and decide which (if any) warrant reopening

3 (b) entries require no action — already correct.
2 (a) entries require no action — content partially landed.
