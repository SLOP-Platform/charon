repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 2
priority-why: |
  P:2 (assigned 2026-07-24; the field was ABSENT until then) — the P:2 band is "standalone,
  biggest blast-radius", and this is the largest such piece on the board: 4 tickets list it in
  depends_on (the highest reverse-dep count among the unprioritised set) and it owns the widest
  seam (gh-cache.sh + done.sh + large-file-guard + land pacing). NOT P:0/P:1: it is PROACTIVE
  hardening against limits we have not hit, not operator-escalated or attached-CG work, and a 39th
  P:0 on a 38-P:0 board is no priority at all.
branch: feat/github-limits-hardening
owns: fleet/gh-cache.sh, fleet/done.sh, fleet/checks/large-file-guard.sh, fleet/tests/test_github_limits.sh
serial_justified: One cohesive proactive-hardening pass against GitHub's limits (search-API + large-file + land pacing) sharing the gh-cache seam; splitting fragments the batching contract.
depends_on: VERIFY-MERGED-REPO-AWARE
real-dep: VERIFY-MERGED-REPO-AWARE — shared single-owner of fleet/done.sh. That branch is ALREADY
  BUILT and pending landing (it rewrites done.sh's merge-verification path to be repo-aware); this
  ticket also edits done.sh. Single-writer sequencing — rebase onto it, never co-write.
  Added 2026-07-18 (board correction).
note: |
  PROACTIVE (operator: optimize before we hit a limit, not reactive). GitHub-limits audit (this
  session) found exposures beyond the 5000/hr REST limit already batched by fleet/gh-cache.sh:
  1. SEARCH API is 30 req/MIN (10x tighter than core). done.sh merged_pr_touching_owns does
     `gh pr list --search "$p"` PER owns-file -> can exhaust the search limit fast. FIX: extend
     gh-cache.sh to also cache each repo's merged PRs WITH files (one call: --json number,headRefName,files)
     and rewrite merged_pr_touching_owns to grep the cache -> ZERO search-API calls.
  2. NO large-file guard: a staged file >100MB HARD-blocks push (50MB warns). FIX:
     fleet/checks/large-file-guard.sh fails on any staged/committed file >50MB (allowlist for
     known-large), wired into preflight scan + a pre-commit path.
  3. Secondary content-creation limit (~80/min) is tripped by land BURSTS (observed this session:
     8 rapid merges -> temporary block that cleared in minutes). FIX: land/land-push add a small
     inter-merge spacing (sleep ~2s) so a batch of sequential lands does not trip it.
accept: |
  - merged_pr_touching_owns resolves via the gh-cache (files included); a repo-wide owns match makes
    ZERO `gh ... --search` calls (poisoned-gh fail-on-revert test, like fleet/tests/gh-cache.test.sh).
  - large-file-guard.sh: a staged >50MB file -> FAILS naming the path; clean tree -> passes; wired
    into preflight scan; fail-on-revert test.
  - land/land-push pace sequential merges (small delay) so N lands don't trip the secondary limit.
  - review-log: confirm branch-reaper.sh + log-prune.sh are scheduled; note GHCR old-image pruning as a follow-up.
