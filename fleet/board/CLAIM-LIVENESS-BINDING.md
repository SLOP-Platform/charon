repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: fix/claim-liveness-binding
depends_on:
owns: fleet/claim.sh, fleet/tests/claim-liveness.test.sh
substrate: N/A
substrate-novel: |
  The claim lease is OUR concurrency primitive over OUR board. Reuses what already exists rather
  than inventing: the `heartbeat:` FIELD is already in every marker (it is simply never written
  again), `fleet/state/needs-push/` is already honoured by fleet-droid.sh and surfaced by
  preflight.sh, and `reconcile-stale-claims.sh` + `reap-orphans.sh` already scan claims. Nothing
  new is introduced — three existing mechanisms are connected.
serial_justified: |
  Liveness, death-cleanup and resolution are one invariant ("a claim means someone is working").
  Fixing any one alone leaves the phantom: refreshing without reaping still strands, reaping
  without resolution still loses work.
source: |
  Operator, 2026-08-01: "I don't understand how a phantom claim marker can have real unlanded
  work. Blast radius class level — this is a gap/breakdown in our processes."
note: |
  ## THE BROKEN INVARIANT
  A claim marker is supposed to mean **someone is working this ticket**. It actually means
  **someone started once**. Measured 2026-08-01:
  - `heartbeat:` is written at claim time and **NEVER refreshed** — `heartbeat == claimed` on
    every live marker (verified across all 14). A 4-minute-old lane and a 135-hour-old corpse are
    indistinguishable.
  - Seven markers were phantoms with **zero live processes**, ages 12h to **135h**:
    SW-IDENTITY-FOLD (135h, 2 commits), PREFLIGHT-OWNS-ARBITRATE (134h),
    SECRET-HOTROTATE (131h, 1), SW-STATIC-LEGS-RETIRE (131h, 1),
    BRIDGE-MIGRATE-DROID-CLIENT (14h, 1), PREFLIGHT-GATE-REGISTRY (13.5h, 1),
    LITELLM-CAPABILITY-ADOPTION (12h, 1).
  - **SW-IDENTITY-FOLD's phantom claim blocked PARK-REARM-FUNDED-PROVIDER (P0 money-path)** —
    a live P0 held behind a ticket nobody was working.

  ## HOW A PHANTOM ENDS UP HOLDING REAL WORK (the sequence)
  1. Droid claims -> writes a FILE -> creates worktree -> works -> COMMITS.
  2. The tab dies before publishing (`/quit`, model exhaustion, or the `mkdir` bug at
     fleet-droid.sh:1403 killing the tab under `set -euo pipefail`).
  3. **Nothing removes the claim file when the process dies** — a file has no binding to a process.
  4. `reconcile-stale-claims.sh` later sees unlanded commits and **CORRECTLY fail-closes**,
     refusing to clear a claim over real work.
  5. **Nothing then LANDS that work.** Fail-closed with no resolution path = permanent limbo.
  The safety mechanism is behaving correctly and that is precisely what makes it permanent.

  ## THREE MISSING PIECES — all three, or the phantom survives
  1. **LIVENESS** — refresh `heartbeat:` periodically while the droid runs, so staleness becomes
     measurable. The field already exists; write to it. Pick a refresh interval and a staleness
     threshold well above the longest legitimate run (charon-run's budget is 1800s).
  2. **DEATH CLEANUP** — when a claim is stale AND the branch has unlanded work, convert it to
     `fleet/state/needs-push/<id>` and RELEASE the claim, so the ticket stops blocking dependents
     while the work stays tracked. Stale AND nothing to lose -> release outright.
  3. **RESOLUTION** — a needs-push item must be OWNED and SURFACED until landed, not parked
     forever. It is already surfaced by preflight; the gap is that nothing drives it to closure.

  ## DO NOT
  - Do NOT clear a claim that has unlanded work without writing needs-push first. That is the
    work-destroying path this ticket exists to prevent.
  - Do NOT use wall-clock age alone as the death signal — a legitimately long run must not be
    reaped. Liveness (a refreshed heartbeat) is the signal; age alone is not.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline, fixture board + repo:
    a. a running droid's heartbeat ADVANCES; `heartbeat != claimed` after one interval.
       Revert the refresh -> RED. (Today this assertion fails on the live rig.)
    b. **Reproduce the real case**: a stale claim whose branch has unlanded commits ->
       needs-push written AND claim released. Revert -> RED.
    c. a stale claim with NOTHING to lose -> released, no needs-push noise.
    d. **ANTI-OVER-REAP (the load-bearing one)**: a LIVE droid mid-run, older than the staleness
       threshold in wall-clock but with a FRESH heartbeat, is NOT reaped. Revert -> RED. Reaping a
       live droid is worse than the phantom.
    e. a released phantom no longer blocks a dependent ticket — prove with a fixture dependent.
  Then dogfood against the real board and report what it finds.

D&S — Deps & Sequence:
  - Depends on: nothing. `claim.sh` is uncontended.
  - Pairs with RELEASE-PRESERVES-WORK (release path) and BRANCH-GATE-DIFF-SCOPE (makes the
    rescued branches pushable). This one covers the DEATH path; those cover the exit and push
    paths. Together they close the work-loss triangle.
