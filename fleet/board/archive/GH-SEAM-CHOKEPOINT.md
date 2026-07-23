repo: charon-private
tier: strong
difficulty: 4
work_class: ci-infra
branch: feat/gh-seam-chokepoint
depends_on: GITHUB-LIMITS-HARDENING, STARTUP-CONTEXT-DIET, FOREMAN-MULTI-TRIGGER, VERIFY-MERGED-REPO-AWARE
real-dep: VERIFY-MERGED-REPO-AWARE — shared single-owner of fleet/_lib.sh. That branch is ALREADY
  BUILT and pending landing (+92 lines in _lib.sh establishing the canonical PRODUCT_REPO/
  FLEET_REPO declarations); this ticket also edits _lib.sh. Single-writer sequencing: land that one
  first, then route the gh call sites. Added 2026-07-18 (board correction).
owns: fleet/status.sh, fleet/_lib.sh, fleet/handoff.sh, fleet/land.sh, fleet/submit.sh, fleet/reconcile-merged.sh, fleet/reconcile-held-markers.sh, fleet/checks/base-integrity.sh, fleet/checks/gh-direct-call-guard.sh, fleet/tests/gh-seam.test.sh
serial_justified: The 9 owned surfaces are not 9 independent builds — they are the CALL SITES of ONE
  seam (fleet/gh-cache.sh), and consolidating them is the entire ticket. Splitting per-file recreates
  the exact multi-writer/re-implemented-per-consumer defect being fixed ("GitHub calls re-implemented
  per consumer instead of routed through the ONE cached seam") and violates touch-a-file-ONCE
  [[optimize-execution-wallclock-tokens]]. It is also unsafe in halves: the CHARON_GH_BUDGET breaker
  and the REST-over-GraphQL substitution only protect the quota once EVERY site is behind the seam —
  a half-migrated fleet still starves GraphQL and still hard-fails boot, so each sub-PR would ship a
  green-but-unprotected quota. Per-file edits are also small and mechanical (route the call, drop the
  literal); the difficulty=4 comes from the shared invariant and the fail-on-revert call-COUNT test,
  which are inherently one unit. Finally 3 of the 9 (handoff.sh especially) are dep-gated behind
  in-review owners, so parallel sub-claims would collide on the one file that most needs a single
  writer. The guard+test CAN be split out first if a tab needs feeding — noted in ds: as a manager option.
accept: |
  PROBLEM (a REAL recorded boot failure, not a hypothetical). GitHub calls are re-implemented per
  consumer instead of routed through the ONE cached seam (fleet/gh-cache.sh). 15 direct gh/git-fetch
  call sites across 8 files bypass it. VERIFIED sites — do NOT re-research:
    - fleet/handoff.sh:300  `gh pr list --repo SLOP-Platform/charon --state open --json ...` (uncached)
    - fleet/status.sh:60    `gh pr list --repo "$REPO_SLUG" --json ...` (uncached)
    - fleet/handoff.sh:51   freshness_stamp does a `git fetch` per repo (x2) with NO TTL
    - plus fleet/_lib.sh, fleet/reconcile-held-markers.sh, fleet/checks/base-integrity.sh,
      fleet/reconcile-merged.sh, fleet/land.sh, fleet/submit.sh (grep, excluding gh-cache.sh) = 15 total.
  WHY IT MATTERS: fleet/state/GITHUB-RUNAWAY-POSTMORTEM.md names handoff.sh "the highest remaining
  risk", and fleet/STARTUP-FRICTION-LOG.md records a REAL boot HARD-FAIL — GraphQL quota 0/5000
  exhausted while REST core sat at 4999/5000, because `gh pr list --json` is GraphQL-ONLY. Quota
  exhaustion blocks ALL landing + boot for the remainder of the hour. This is the same class as the
  `parked` predicate (re-parsed per consumer -> drifts).

  DO (COMPOSE, do not rebuild — gh-cache.sh was built for exactly this):
    (a) Route handoff.sh:300 + status.sh:60 + the other 6 files' gh calls through gh-cache.sh's
        `branch_merged_pr` / batched path. Do NOT add a second cache.
    (b) TTL-gate the handoff.sh:51 `git fetch` (per-repo freshness stamp; skip inside the window).
    (c) PREFER REST over GraphQL: `gh api repos/OWNER/REPO/pulls` instead of `gh pr list --json`. The
        recorded failure is specifically GraphQL starvation while REST was nearly untouched — this
        single substitution is the highest-leverage line in the ticket.
    (d) `CHARON_GH_BUDGET` circuit breaker (postmortem rec#2): decrement BEFORE any gh call; refuse and
        fail loud at zero rather than melting the quota.
    (e) fleet/checks/gh-direct-call-guard.sh (rec#4): lint rule REFUSING new direct `gh pr list --head`
        / uncached gh in fleet/ scripts. Allow-list gh-cache.sh itself. This is the durable half — it is
        what stops the 16th call site from being added next week.

  FAIL-ON-REVERT (fleet/tests/gh-seam.test.sh — REQUIRED, all three):
    (1) GUARD CATCHES A NEW BYPASS: feed the guard a FIXTURE script containing a direct uncached
        `gh pr list` -> RED. Move it behind the seam -> GREEN. Revert the guard -> fixture stops
        failing -> test fails.
    (2) SEAM IS ACTUALLY USED (the money question): with a stub/fake `gh` on PATH that COUNTS
        invocations, run the handoff/status path TWICE and assert the second run makes ZERO new `gh`
        calls (cache hit) — i.e. assert the call COUNT, not that the code merely imports gh-cache.sh.
        Revert the routing -> call count doubles -> RED.
    (3) BUDGET BREAKER: with CHARON_GH_BUDGET exhausted, assert the path refuses loudly and makes no
        gh call. Revert the breaker -> RED.

  GREEN-IS-NOT-PROOF (explicit, and this session has already been burned by exactly this): PRs shipped
  19/19 and 40/40 green this session while the real path was broken, because EVERY test used fixtures.
  The whole rig suite is green RIGHT NOW with all 15 bypasses live and a recorded boot hard-fail on the
  record — the suite never exercises the real GitHub path, so it CANNOT go red on quota starvation. A
  test that stubs `gh` and asserts the code "calls gh-cache.sh" proves only that a function was invoked,
  NOT that the quota is protected. Test (2)'s invocation COUNT across two runs is the minimum bar: it is
  the only assertion here that can distinguish a real cache hit from a decorative one. Reviewer:
  confirm no test asserts against a mocked-in-advance cache-hit, and that REST replaced GraphQL at the
  `gh pr list --json` sites.
scope: |
  Route the 15 direct gh/git-fetch call sites (8 files) through the ONE cached seam gh-cache.sh, TTL-gate
  handoff.sh:51's per-repo fetch, prefer REST over the GraphQL-only `gh pr list --json` that starved the
  quota in a recorded boot hard-fail, add a CHARON_GH_BUDGET circuit breaker, and lint new direct calls
  so the class cannot regrow. Compose the existing seam; do not build a second cache. Quota exhaustion
  blocks ALL landing + boot, so this is a fleet-wide availability fix.
  [[fleet-selfcheck-forkbomb-class]] [[slowness-triggers-investigation]] [[gates-must-actually-run]]
  [[no-stiff-single-provider-tools]]
ds: |
  ## Dependencies & sequence
  depends_on: GITHUB-LIMITS-HARDENING, STARTUP-CONTEXT-DIET, FOREMAN-MULTI-TRIGGER — all three are REAL
    prereqs (not merge-order preference); each is justified below. All three are currently IN REVIEW
    (state/submitted), so this ticket becomes claimable as the manager lands them.
  real-dep: GITHUB-LIMITS-HARDENING owns the seam this ticket CONSUMES (fleet/gh-cache.sh + fleet/done.sh
    + fleet/checks/large-file-guard.sh). Routing 8 files into gh-cache.sh before its hardening lands
    would build against an API that ticket is actively changing. Do NOT co-own gh-cache.sh or done.sh —
    this ticket consumes the seam, that ticket hardens it. done.sh's search-API call is ITS leg, not ours.
  real-dep: STARTUP-CONTEXT-DIET owns fleet/handoff.sh (declared absolute: /home/stack/charon-private/
    fleet/handoff.sh) and fleet/preflight.sh. This ticket also edits fleet/handoff.sh (:51 fetch TTL,
    :300 gh call). NOTE FOR THE VALIDATOR AND THE NEXT READER: that overlap is INVISIBLE to
    validate_board's owns-collision check because the two declarations use different path FORMS
    (absolute vs repo-relative) and it keys on the exact string — the collision is real regardless. This
    dep is what actually sequences it. Land STARTUP-CONTEXT-DIET first; touch handoff.sh ONCE, after.
  real-dep: FOREMAN-MULTI-TRIGGER owns fleet/handoff.sh (exact-string collision) + fleet/foreman-cadence.sh.
    Same single-writer reason: handoff.sh must have exactly one writer at a time.
  concurrency: BLOCKED until the three land, then runs alone on the fleet/*.sh surface. Deliberately
    single-writer over 8 shared scripts ([[optimize-execution-wallclock-tokens]]: touch a file ONCE) —
    do NOT decompose this into per-file tickets, that recreates the multi-writer problem it fixes.
  free-now (no dep): fleet/checks/gh-direct-call-guard.sh + fleet/tests/gh-seam.test.sh are NEW files. If
    the manager needs this tab fed BEFORE the three deps land, split the guard+test out as a standalone
    lint-only first PR; the call-site migration still waits. Manager's call, not the droid's.
  reads-only (no owns claim): fleet/gh-cache.sh, fleet/done.sh — consumed, never edited here.
  wave: strong refill 2026-07-16. Frontier may claim down.
  repo: charon-private (rig).
note: Created 2026-07-16 from fleet/session-notes/2026-07-16-evidence/audit-harvest.md item 1
  (GITHUB-RUNAWAY-POSTMORTEM rec#1/#2/#4 + STARTUP-FRICTION-LOG). Dep-gated behind 3 in-review tickets
  because handoff.sh currently has two other declared owners — single-writer discipline, not preference.
</content>
</invoke>
