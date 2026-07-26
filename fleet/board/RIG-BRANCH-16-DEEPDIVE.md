repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 0
branch: fix/rig-branch-16-deepdive
depends_on:
owns: fleet/state/RIG-BRANCH-16-RULING.md
serial_justified: |
  ONE cohort, ONE per-branch verdict file. The 16 branches share a single hypothesis (landed by
  re-derivation); verifying them as a set is what makes the equivalence claim checkable.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  Graded sample: record into fleet/model-scorecard.tsv. One checkout, one agent — its OWN worktree.
source: |
  Reap verification 2026-07-26 (operator item #3) skipped these 16; operator approved proceeding under
  a content-equivalence rule (item #12) and ordered a deep dive.
note: |
  ## THE COHORT (16 rig branches, each with 1-6 commits NOT reachable from origin/master)
  feat/substrate-first-gate, feat/substrate-first-gate-v2, feat/coverage-meta-gate,
  feat/coverage-meta-gate-rederive, feat/semgrep-ci-v2, feat/semgrep-ci-required-check,
  feat/stranded-work-detect, feat/stranded-work-detect-v2,
  salvage/preflight-verify-merged-ghcache-wip, feat/github-limits-hardening,
  feat/github-limits-hardening-v2, feat/session-end-push-gate, feat/session-end-push-gate-v2,
  design/unified-reconciliation-gate, doctrine/adopt-substrate-first, chore/gitignore-state-negations

  The reap skipped them correctly: the rule was zero-unique-commits and these have unique SHAs. The
  claim is that they landed BY RE-DERIVATION — same content, different SHAs — and all 16 are published
  on `gitea` at their exact local SHA.

  ## THE OPERATOR RULING (item #12, approved)
  Proceed under CONTENT-equivalence rather than SHA-reachability. **But equivalence must be VERIFIED
  PER BRANCH, never inferred from the re-derivation story.** "They all landed by re-derivation" is a
  narrative; a diff is evidence. A branch whose content is NOT on master is real unlanded work and
  must be surfaced, not reaped — this cohort is exactly where the next SECRET-HOTROTATE would hide.

  ## THE PATTERN WORTH EXPLAINING (the deep-dive half)
  Note the `-v2` / `-rederive` pairs: substrate-first-gate, coverage-meta-gate, stranded-work-detect,
  github-limits-hardening, session-end-push-gate all exist twice. Something in the landing flow makes
  people re-cut a branch rather than continue the original. Explain WHY with evidence — that mechanism
  is a prime suspect for the sprawl in BRANCH-SPRAWL-ROOT-CAUSE, and fixing it is worth more than
  deleting the 16.
accept: |
  DONE-CONTRACT (per branch, all 16 — no sampling):
  - A verdict of EQUIVALENT / NOT-EQUIVALENT / AMBIGUOUS with the evidence that produced it. For
    EQUIVALENT: show the content comparison against origin/master (e.g. `git diff origin/master..<b>`
    empty, or a file-level diff proving each unique commit's content is present). A commit-count
    comparison is NOT content evidence.
  - Confirm the gitea publication per branch (`git branch -r --contains <sha>`) with the remote ref
    named — the claim "all 16 are on gitea" is the entire safety net for this operation and must be
    re-verified, not inherited from the prior report.
  - Any NOT-EQUIVALENT or AMBIGUOUS branch: describe the unlanded content and author a follow-up
    ticket. Reaping is NOT approved for these.
  - An explanation of the `-v2`/`-rederive` duplication pattern, evidenced from the landing scripts.
  - THEN, and only for branches verified EQUIVALENT and confirmed on gitea: delete them locally,
    recording every SHA in the ruling file first. Local only — never delete a remote branch.
  - NON-VACUOUS: a ruling covering fewer than 16 branches is incomplete, not partial credit.
  - When verification is ambiguous, SKIP. Skipping costs nothing; a wrong delete loses work that
    exists nowhere else.

## Dependencies & sequence

- **Depends on: NOTHING. Startable immediately.**
- **Related (do not duplicate):** BRANCH-SPRAWL-ROOT-CAUSE owns the general cause; this ticket owns
  this cohort and the re-derivation mechanism. Share findings, do not re-derive them.
- **Wave:** parallel lane, P0.
