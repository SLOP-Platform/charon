repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: feat/pr-queue-rest-etag
owns: fleet/pr-queue.sh, fleet/tests/pr-queue.test.sh
serial_justified: One queue generator plus its fail-on-revert suite; the suite is what proves the ETag/TTL/lock behaviour actually fires.
substrate: N/A
substrate-novel: |
  No tool is being replaced or hand-rolled — this REPLACES rig code with the platform's own
  primitives. The change is to stop using `gh pr list` / `gh pr view` (GraphQL) and instead use
  GitHub's REST API with HTTP conditional requests (`If-None-Match` / 304), which is the
  standards-defined mechanism for exactly this problem. `gh` itself remains the client.

  Considered under ADOPT-FIRST, all rejected on measured grounds, not on "adds a dependency":
    * GitHub webhooks — the genuinely correct long-term answer (event-driven, zero polling cost)
      and NOT rejected on principle. It needs a publicly reachable endpoint on a solo box behind
      NAT; that is a real infrastructure decision with its own security surface, not a drop-in.
      Recorded as the intended successor, not dismissed.
    * A GitHub App installation token instead of a PAT — raises the ceiling, but this ticket
      REMOVES ~99% of the calls, which is strictly better than affording more of them.
    * octokit / PyGithub — full API SDKs. They would replace `gh`, which is already adopted and
      already authenticated, to solve a problem that is one HTTP header. Adopting an SDK here
      would be substrate churn, not substrate adoption.
depends_on:
note: |
  MEASURED 2026-08-01: seven reviewer tabs exhausted GitHub's 5,000/hr GRAPHQL quota in under an
  hour and blocked the manager's own `gh pr review` (the PR #342 bounce) and `land-push` (which
  correctly refuses to read an unverifiable CI status as green).

  Cost per cycle PER TAB in `review-pool.sh`'s `queue_gen()`:
    1x `gh pr list` per repo (2 repos)                        — GraphQL
    1x `gh pr view <n> --json commits` for EVERY open PR (~16) — GraphQL
  = ~18 GraphQL calls/cycle/tab. At 45s x 7 tabs that is >10,000/hr against a 5,000/hr limit.

  THREE MEASURED FACTS THIS IS BUILT ON (verified, not assumed):
    * REST core is a SEPARATE 5,000/hr bucket — it read 5000/5000 untouched while GraphQL sat at 0.
    * `gh api 'repos/{slug}/pulls?state=open&per_page=100'` returned all 16 PRs WHILE GraphQL was
      exhausted.
    * ETag conditional requests are FREE — three consecutive 304s did not increment
      `x-ratelimit-used`.

  B1 CORRECTNESS — THE LOAD-BEARING DECISION. The obvious REST shortcut is `user.login` from the
  `/pulls` payload, which would remove the per-PR call entirely. It was MEASURED and REJECTED:
  `user.login` is `Nnyan` on ALL 16 open PRs (one GitHub account fronts the whole fleet), so column
  3 would become a constant matching no droid id and would SILENTLY DISARM the reviewer!=builder
  guard forever. Author semantics are therefore preserved exactly — the git author name of the
  PR's last commit — via REST `/pulls/{n}/commits`, kept off the hot path by caching under the PR
  head SHA (free from the list payload). `Link: rel="last"` pagination is followed because page 1's
  last element is commit #100, not the last commit, i.e. the WRONG droid id.

  This is the same anti-pattern the session has now hit four times: an infrastructure failure
  laundered into a normal-looking outcome. With `gh` rate-limited, the old path logs a WARN and
  reports an EMPTY QUEUE — indistinguishable from a drained backlog. Hence the fail-LOUD refusal.
accept: |
  - REST only: no `gh pr list` / `gh pr view` on any path.
  - ETag `If-None-Match` cache; a 304 reuses the cached payload and makes ZERO further calls.
  - TTL skip (`PR_QUEUE_TTL_S`, default 120) with `--force` override, re-checked UNDER the lock
    (double-checked) so N tabs regenerate once, not N times.
  - flock so concurrent tabs cannot interleave writes; atomic temp-file -> mv install.
  - Dedup on `(num, repo)`. The old appender produced 3x duplicates with 3 tabs (23 rows -> 66).
  - FAIL LOUD, never fail quiet: if REST remaining is low, or `gh` fails, REFUSE with a non-zero
    exit and a banner. A rate-limit outage must NEVER present as an empty (drained) queue.
  - Output-format parity with the existing queue rows: 6 columns
    `<num> <repo_key> <author_droid> <title> <url> <iso8601_ts>`, same skip rules, same file.
  - B1 preserved: author = git author name of the PR's LAST commit. `user.login` is forbidden.
  - fail-on-revert proof with a stubbed `gh` (ZERO real API calls in tests).
verified: |
  Delivered 2026-08-01 by a sub-session; verified before landing:
    * 40/40 tests PASS, 0 fail.
    * Red-proof: 8 INDEPENDENT reverts, every one caught — user.login author (8 red), no dedup
      (11), no locked TTL re-check (1), warn-instead-of-refuse (5), no flock (1), trusting `gh` rc
      (4), no TTL skip (1), no If-None-Match (2).
    * shellcheck clean at ALL severities on both files.
    * LIVE smoke on the real API: sweep 1 over 16 open PRs cost 16 core calls; sweep 2 with
      `--force` and TTL=0 cost ZERO (core used 18 -> 18). TTL skip and the exit-3 refusal banner
      both fired on the live path with rows preserved.
    * `gh api` exits rc=1 on a 304, so status is parsed from the response line and rc deliberately
      ignored; `/rate_limit` itself is free.

## Dependencies & Sequence

- **depends_on: (none).** Two NEW files; nothing else is touched.
- **Sequence: now.** It is a drop-in but NOT yet dropped in — see below.
- **owns-collision:** none, deliberately. `fleet/review-pool.sh` is owned by REVIEWER-TAB-POOL
  (PR #346, still open), so this was built as a standalone generator rather than an edit to it.
- **NOT DONE HERE — the wiring.** Nothing calls `pr-queue.sh` yet; `review-pool.sh`'s `queue_gen()`
  is still the live path and still burns GraphQL. Cutting it over is a one-line change INSIDE
  review-pool.sh and therefore belongs to REVIEWER-TAB-POOL / PR #346. Until that lands, the
  saving is available but unrealised — this ticket is "built", not "firing".
- **Known gaps, carried forward rather than hidden:**
  (a) ROW ORDER vs the old generator is reasoned, not measured — GraphQL was at 0 all session so no
      side-by-side was possible. `sort=created&direction=desc` matches `gh pr list`'s documented
      default. It matters because `claim_next` takes the first claimable row. VERIFY when GraphQL
      resets.
  (b) The `Link: rel="last"` >100-commit pagination branch is exercised by reasoning only — no open
      PR has that many commits.
  (c) The new suite is NOT registered in `rig-ci-scope.sh`'s `CI_SUITES` (owned by
      HANDOFF-GATE-NONBYPASSABLE) — the same gap `review-pool.test.sh` already has. Follow-up.
