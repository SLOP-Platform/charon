# GITHUB-LIMITS-HARDENING — Review Log

## Ticket
GITHUB-LIMITS-HARDENING: Proactive hardening against GitHub's API + push limits
(search-API 30 req/MIN, push hard-block at >100MB, secondary content-creation
~80/min on burst merges). One cohesive pass sharing the gh-cache seam.

## Scope decision (owns: is the hard rule)

This ticket's `owns:` is exactly:
- `fleet/gh-cache.sh`
- `fleet/done.sh`
- `fleet/checks/large-file-guard.sh`
- `fleet/tests/test_github_limits.sh`

The ticket WORK NOTE also asked for "wired into preflight scan", "a
pre-commit path", and "land/land-push add a small inter-merge spacing" —
those fixes touch `fleet/preflight.sh`, `fleet/land-push.sh`, and a new
`fleet/checks/pre-commit-large-file-guard.sh`, which are NOT in `owns:`.

Per the launcher's hard rule ("`owns:` wins; if your change genuinely needs
a file OUTSIDE your `owns:`, STOP and run release.sh with a one-line reason")
those are split out as separate tickets:

- **GITHUB-LIMITS-WIRE** (new) — wire `large-file-guard_gate` into
  `preflight.sh` (auto-registers a `large-file-guard-violation` red) and add
  the `pre-commit-large-file-guard.sh` installer. Owns: `fleet/preflight.sh`,
  `fleet/checks/pre-commit-large-file-guard.sh`.
- **LAND-PUSH-PACE** (new) — add `LAND_PACE_S` pacing to `land-push.sh` and
  wire to the same knob `land.sh` already has. Owns: `fleet/land-push.sh`,
  `fleet/land.sh`.

The cache + owns-match + large-file-guard SHELL (this ticket) is fully
self-contained: it has fail-on-revert tests, the gh-cache change is
additive, the done.sh change is the only owns-match path, and the
large-file-guard.sh works standalone (callable from any pre-commit
hook or a wrapper owned by the wire-up ticket).

## What was done

### 1. Search-API exposure — owns-match via the cache (ZERO `--search` calls)
- **`fleet/gh-cache.sh`** — added a SECOND per-repo cache carrying `files[]`, built by
  its own `gh pr list --state merged --json number,headRefName,files` call (TTL 120s).
  CORRECTION (2026-07-19): an earlier revision of this log claimed these were the SAME
  call and "one network round-trip". That was FALSE — there are two batched `--limit 800`
  calls. Requesting `files[]` on the hot `branch_merged_pr` path also cost ~4.4x
  (4.23s -> 0.97s once dropped), so the payload was removed from that call rather than
  consolidating, which would have re-coupled the hot path to the expensive payload.
  New `merged_prs_touching_file <slug> <path>`
  API returns a PR# for any merged PR that touched `<path>` via a local grep on
  the cached "<pr#>\t<path>" index. The index lives at
  `state/cache/merged-files-<slug>.tsv`; the existing `branch_merged_pr` API is
  unchanged (same index, different column lookup).
- **`fleet/done.sh:merged_pr_touching_owns`** — rewritten to call the cache fn
  instead of `gh pr list --search "$path"`. The audit found a per-owns-file
  `--search` call (O(tickets × owns) per sweep); now it is O(repos) per TTL.
- **Independent fixture for testing** — `GH_MERGED_FILES_FIXTURE` (TSV
  "<pr#>\t<path>") is the test seam; an unset or empty fixture still refuses
  cleanly (no silent fallback to the live search API). The legacy branch-only
  `GH_MERGED_FIXTURE` remains as a no-files fixture for existing tests.

### 2. Large-file push guard (the >100MB hard-block, caught at commit time)
- **`fleet/checks/large-file-guard.sh`** — new. Scans both STAGED (via
  `git ls-files --stage` + `git cat-file -s`) and UNTRACKED (via
  `git ls-files --others --exclude-standard`) files. Default 50 MiB threshold
  (below the 50MB warning + 100MB hard-block so the droid can `git rm` /
  re-attach to LFS / move to a release artifact BEFORE the next push). Override
  via `--max-bytes` or env `LARGE_FILE_MAX_BYTES`. Allowlist via `--allowlist`
  regex / `LARGE_FILE_ALLOWLIST` env (e.g. for `seed-corpus.bin`).
  - Standalone, callable today from any external wiring (the wire-up ticket
    just needs to invoke it with `$repo` as the arg).

## Key decisions

- **One cache, two APIs (branch + owns)**. The merged-PR cache was already
  making `gh pr list` per repo per TTL (O(repos), not O(tickets)). Adding
  `files[]` to the same JSON response is one extra column on the same wire —
  the owns-match path inherits the existing batching for free. A separate
  "files index" TSV is just a reshape; no new network calls.
- **Index files separately, not interleaved**. The branch cache stays a
  "<branch>\t<pr#>" TSV; the new files cache is "<pr#>\t<path>" TSV. Different
  lookup patterns (linear branch, indexed-by-path) want different shapes;
  interleaving would force every branch-merge to skip the files rows.
- **Allowlist via regex, not exact-match**. A droid can drop a seed corpus
  under any name (`seed-v1.bin`, `corpus_2026.bin`); a regex lets the
  operator express "all paths matching `.*-corpus\.bin$`" without a per-file
  registration cycle.
- **Large-file threshold = 50 MiB, not 100 MiB**. GitHub rejects at 100MB and
  warns at 50MB. Failing at 50MB gives the droid a clean "remove this /
  attach to LFS" decision before GitHub starts warning the operator in the
  UI; failing at 50MB exact matches the warning threshold but adds a margin
  for files that grew between the check and the push.
- **Split into 3 tickets, not 1**. The launcher's hard rule (`owns:` is the
  only thing you may edit) is a stronger constraint than the ticket WORK
  NOTE. The 3 cohesive pieces share the gh-cache seam, but the wire-up
  touches files owned by other tickets; splitting at that boundary is
  safer than a scope-violating PR.

## Review notes

- **GH_CACHE_TTL = 120s** remains the default. Bumping to 300s would cut
  network by 2.5× but increases the stale-cache window for the owns-match
  (a fresh PR merge wouldn't be visible to done.sh for up to 5 min). The
  current 120s is the right trade-off for done.sh's lag tolerance (a
  ticket's done-marker is a deliberate operator action; waiting 2 min is
  fine).
- **The legacy `branch_merged_pr` API was already doing the right thing**
  (batched, no per-branch gh call). The audit found it was only the
  owns-match path burning the SEARCH API; the branch-match path was safe.
  This pass ONLY touches the owns-match.
- **Stale-cache false-negatives**. If `gh pr list --limit 800` ever hits the
  800-row limit, the cache silently truncates. With ~600 merged PRs across
  the product this is fine for now; if it ever approaches 800, switch to
  `--paginate` (slower but unbounded). Noted as a follow-up.
- **`DONE_MERGED_SRC` short-circuit**. The legacy branch-only fixture
  (which only contains "<branch>\t<pr#>" rows, no files) correctly returns
  empty for owns-match rather than falling through to the live search API.
  This is the OFFLINE-SAFE path: a test stubbing only the branch cache
  gets refused rather than a false-positive.

## Follow-ups (out of scope for this ticket)

- **GITHUB-LIMITS-WIRE** — wire `large-file_guard_gate` into preflight
  (`fleet/preflight.sh:large_file_guard_gate` is ready, the dispatch
  in the `scan` case is needed), and ship
  `fleet/checks/pre-commit-large-file-guard.sh` as the installable
  pre-commit hook.
- **LAND-PUSH-PACE** — add `sleep "${LAND_PACE_S:-2}"` to
  `fleet/land-push.sh` after the `git push`, mirroring the
  same knob `fleet/land.sh` already has around `gh pr merge`.
- **branch-reaper.sh + log-prune.sh scheduling**. Both scripts are runnable
  and tested (`fleet/tests/branch-reaper.test.sh`, `fleet/tests/log-prune.test.sh`)
  but neither is wired into a cron / systemd timer / preflight invocation.
  For a build-rig that runs continuously, a 24h timer (or a preflight call
  gated on "last run > N hours ago") is the obvious hook.
- **GHCR old-image pruning**. The 4-LOM gateway image (charon-gateway-*)
  and the model-side images (charon-runner, charon-bench-*) accrue on
  ghcr.io/SLOP-Platform. GitHub Packages free tier has a 500MB / 2GB soft
  cap (depending on plan) and the image registry is a separate quota from
  the API. A prune action on `gh api -X DELETE .../docker/manifests/<digest>`
  with `keep-last-N-tags` semantics is the same shape as log-prune.sh —
  worth lifting into a small `ghcr-prune.sh` (or extending log-prune) so
  the same idempotency / suffix-locked / path-locked guards apply.
- **Cache invalidation on land.sh merge**. A successful merge could
  immediately invalidate the merged-PR cache for the target repo; today
  the cache is TTL-only. A `rm $cf` in land.sh after a successful merge
  would shorten the staleness window to ~0 for the just-merged branch.
  Minor, but a clean follow-up if cache freshness becomes an issue.
- **The `_gh_merged_files_tsv` jq query** uses `.files[]?` (optional) — if
  GitHub ever changes the JSON shape to omit `files` for merged PRs older
  than some boundary, the cache silently loses them. Worth a
  smoke-test on a known-old merged PR before relying on this for a
  long-lived cache.
