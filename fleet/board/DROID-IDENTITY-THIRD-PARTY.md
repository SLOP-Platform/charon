repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: bugfix
branch: fix/droid-identity-third-party
depends_on:
owns: fleet/droid-identity.sh, fleet/tests/droid-identity.test.sh, docs/review-log/DROID-IDENTITY-THIRD-PARTY.md
serial_justified: |
  One file, one identity default, one assertion. Nothing to parallelise.
substrate: N/A
substrate-novel: |
  No tool involved. This is a wrong constant in our own identity helper. The novel slice is the
  assertion that our commit identity must NOT resolve to a real GitHub account.
accept: |
  MEASURED 2026-08-02: `gh api users/charon-bot` resolves to a REAL THIRD-PARTY ACCOUNT —
  login=charon-bot, name="Mr. Charon", created 2018-11-05, 0 public repos. The operator has
  confirmed it is NOT theirs and they have never had such an account.
  `fleet/droid-identity.sh:36-42` defaults every droid commit to
  `charon-bot <charon-bot@users.noreply.github.com>`. GitHub's `<username>@users.noreply.github.com`
  form maps to THAT PERSON'S ACCOUNT, so our commits — on a PUBLIC repo — are attributed to a
  stranger. Verified live: droid commit stamps in the launcher logs read
  `charon-bot <charon-bot@users.noreply.github.com>`.
  How it got here: a prior session ran the same lookup, saw the name resolve, and recorded
  "the charon-bot account EXISTS" (operator action #23) as evidence it was OURS. It was evidence
  only that the name is TAKEN. That reading also made #23 — "get a PAT for charon-bot" —
  permanently unactionable, since we can never hold credentials for someone else's account.
  Done contract:
  1. Change the default identity to an address that resolves to NOBODY. The launcher already
     uses `<droid-id>@fleet.local` for per-droid stamps; use that shape (e.g.
     `charon-fleet <charon-fleet@fleet.local>`), or a real account the operator controls.
     Do NOT pick another bare username — that just moves the collision.
  2. ASSERTION, the load-bearing part: a test that FAILS if the configured commit email matches
     `*@users.noreply.github.com` unless the operator has explicitly set
     CHARON_PUBLIC_GIT_EMAIL to an account they own. Fail-closed.
  3. Sweep for other uses of the string: `grep -rn charon-bot` across both repos, including
     PR-body markers and any reviewer author-matching (REVIEWER-TAB-POOL keyed on
     `CHARON-AUTHOR-DROID`, which no code writes — check for related assumptions).
  4. Historical commits already carry the address. Do NOT rewrite public history; fix it going
     forward and record the decision.
  5. REWRITE operator action #23: its premise is false. Split it — (a) the identity fix, this
     ticket; (b) IF a second GitHub identity is still wanted for reviewer!=builder and for a
     second API-quota pool, it must be an account the operator CREATES and controls.

## Dependencies & Sequence

P0 by blast radius on correctness-of-attribution, not by size — it is a two-line default plus a
test. No inbound deps. Should land BEFORE any further droid PRs so the misattribution stops
accruing. Independent of the quota work in operator action #31, which needs a real owned account.
