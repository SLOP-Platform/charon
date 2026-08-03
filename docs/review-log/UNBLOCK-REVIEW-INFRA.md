# Review log: UNBLOCK-REVIEW-INFRA

## Ticket
UNBLOCK-REVIEW-INFRA — reconcile three open PRs in the review-infra lane (queue generator,
reviewer-tab tool, review-pool hardening) against a single moving target (fleet/review-pool.sh).

## What I read (corrected attribution; the first fragment swapped #389 and #346)

**PR #392 (feat/pr-queue-rest-etag, branch feat/pr-queue-rest-etag) — OPEN, CI GREEN**
- `fleet/pr-queue.sh` (NEW): REST+ETag queue generator. Writes the same `QUEUE_TSV` schema
  (6 TSV columns) and same skip rules as `review-pool.sh`'s `queue_gen()`.
  Author extraction: REST `/pulls/{n}/commits` → `.[-1].commit.author.name` (git commit name,
  same as the GraphQL it replaces). ETag 304 is FREE (zero quota cost); author cached under PR
  head SHA. `user.login` explicitly rejected (Nnyan on every PR — would silently disarm B1).
- `fleet/tests/pr-queue.test.sh`: 40/40 PASS, 8-way red-proof, zero real API calls.
- `fleet/review-pool.sh`: NOT modified on this branch.
- `gh pr checks`: bandit, gitleaks, rig-ci, semgrep all PASS.
- Status: READY. The cutover (wire pr-queue.sh into the review-pool.sh call path) is the single
  missing piece and the highest-leverage item in the lane.

**PR #389 (feat/reviewer-pool-headless-tabs, branch feat/reviewer-pool-headless-tabs) — MERGED**
- Merged 2026-08-02T04:48:33Z (merge commit e83bea0) as "feat(reviewer-tab): headless reviewer
  tab with fail-loud preflight".
- Adds `fleet/reviewer-tab.sh`, `fleet/spawn-tab.sh`, `fleet/REVIEWER-POOL-PROCESS.md` — the tool
  the reviewer tabs RUN. Does NOT touch fleet/review-pool.sh.
- Status: LANDED. Step 2 of the ticket ("land or fix the reviewer-tab tool") is DONE.

**PR #346 (feat/reviewer-tab-pool, branch feat/reviewer-tab-pool) — OPEN, BOUNCED**
- Touches fleet/review-pool.sh, fleet/checks/rig-ci-scope.sh, fleet/tests/review-pool.test.sh.
- Contains both good hardening and a fatal author-extraction change:
  - CHARON-AUTHOR-DROID PR-body marker extraction (queue_gen): REJECT — ZERO of 32 open PRs
    carry this marker and no code writes it. With B1 fail-closed, every PR has unknown author →
    every claim refused → the pool reviews NOTHING. Revert to git-commit approach.
  - mapfile+awk field parse (claim_next): KEEP — fixes the bash IFS collapse bug.
  - B1 fail-closed on UNKNOWN author: KEEP — the right behavior.
  - base64-encoded diff in prompt (B4): KEEP — prevents prompt injection via delimiter injection.
  - strict verdict delimiter parse (exit 2 on malformed): KEEP.
  - rig-ci-scope.sh adds review-pool.test.sh to CI_SUITES (B3 fix): KEEP.
- Merges cleanly against current master (verified: `git merge origin/master` → no conflict).
  The earlier claim of a conflict with #393's trap fix no longer applies.

**PR #393 (fix/SANDBOX-CONTAINMENT) — on master (base 2119d77)**
- `fleet/review-pool.sh`: trap-expansion fix only. This is the base the three branches reconcile
  against.

## Decision

1. **PR #392 cutover** — HIGHEST PRIORITY.
   Queue generation is built, tested (40/40), CI-GREEN, and sits untouched. The cutover
   (`pr-queue.sh gen` replaces `review-pool.sh queue` in the reviewer-tab call path) is the single
   highest-leverage action. No review-pool.sh claim/review logic changes in this step.
2. **PR #389** — LANDED (merged 2026-08-02). Nothing further to do.
3. **PR #346 disposition** — REWORK, do NOT land as-is.
   Keep mapfile, B1 fail-closed, base64, strict verdict, CI_SUITES add; REVERT the author
   extraction to the git-commit approach already on master. Land that, or close with evidence
   (marker absent from all 32 open PRs).

## What I proved by executing

- `gh pr list --repo Nnyan/charon-private --state open`: 32 open PRs; scanned every body — none
  carry the CHARON-AUTHOR-DROID marker.
- `gh pr view 389/346/392 --repo Nnyan/charon-private`: confirmed branch↔PR mapping and #389's
  merge (e83bea0, 2026-08-02T04:48:33Z).
- `gh pr diff 389 --name-only`: #389 adds reviewer-tab.sh/spawn-tab.sh/REVIEWER-POOL-PROCESS.md
  only — review-pool.sh untouched.
- `gh pr diff 346`: confirmed the CHARON-AUTHOR-DROID capture + mapfile/B1/base64/verdict/CI_SUITES
  parts; `git merge origin/master` into feat/reviewer-tab-pool succeeds with no conflict.
- `gh pr diff 392 --name-only` + `gh pr checks 392`: pr-queue.sh + test are NEW files,
  review-pool.sh untouched, all four CI checks PASS.

## Gate status

No code changes on this branch — sequencing/disposition documentation only. Gate applies to the
resulting merged branch, not to this fragment.
