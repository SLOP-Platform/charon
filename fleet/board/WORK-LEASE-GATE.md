repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 0
branch: feat/work-lease-gate
owns: fleet/work-lease.sh, fleet/tests/work-lease.test.sh, fleet/hooks/pre-commit, fleet/hooks/commit-msg
substrate: N/A
substrate-novel: |
  No external tool provides this. The commodity primitives are ALREADY adopted in-tree: git's native
  client-side hooks (pre-commit / commit-msg) supply the commit chokepoint, util-linux flock supplies the
  atomic mutex, and claim.sh already owns the fleet's atomic ticket claim under state/lock. The novel slice
  is the CONVERGENCE — making that one atomic claim double as the mandatory lease enforced at BOTH the
  dispatch boundary (a second builder is refused) and the commit boundary (an un-leased or main-checkout
  work-commit is refused), fail-closed on unmapped branches. Off-the-shelf lease managers (etcd/Consul
  sessions, redis SETNX) are network daemons that would fork a SECOND store beside claim.sh's — the exact
  double-store the review rejected — so adopting one would REGRESS the single-source claim, not advance it.
depends_on:
serial_justified: one gate — the lease check + its write-boundary enforcement + the fail-on-revert proof are a single coupled mechanism; splitting ships a check nothing enforces, or enforcement with no check.
work_class_note: |
  Operator-directed 2026-07-23 after a real clobber. REUSE-CHECK (operator-flagged): SUBAGENT-WORKTREE-
  SANDBOX (SEC-SBX) already DESIGNS the FILESYSTEM boundary (bwrap: a sub can't write outside its worktree)
  — but it's designed-not-built. THIS ticket is the CHEAP COMPLEMENTARY slice, NOT a duplicate: the git
  COMMIT-BOUNDARY check + "every work-session (incl. manager subagents) is ASSIGNED a claimed worktree,
  never dropped into main" — the claim/ownership half the sandbox assumes but doesn't provide. Two layers of
  one gate: SEC-SBX = filesystem confinement (heavier, adopt-first); this = the cheap git-level enforcement
  that stops the clobber today with no bwrap. [[commit-dirty-sweeps-subagent-wip]] [[one-checkout-one-agent]]
accept: |
  ONE universal work-lease gate, enforced at the WRITE BOUNDARY (the cheap chokepoint where clobber happens):
    1. **Lease = the existing atomic claim, made MANDATORY for every session type.** REUSE `claim.sh`'s
       flock claim — do NOT build a second lock. A lease binds (ticket, worktree, session-id, heartbeat).
    2. **Main checkout is NOT a work surface.** A pre-commit / pre-land check REFUSES a commit that is
       (a) in the MAIN checkout but not a sanctioned land / board-hygiene op, or (b) for a ticket the
       committing session does not hold the lease on. Work happens ONLY in a leased worktree.
    3. **Manager path:** dispatching an ad-hoc build subagent MUST acquire a lease + isolated worktree first
       (or the subagent goes through the fleet claim path). Provide the one command that does it, so it's
       easy to do right.
    4. **Stale-safe:** a lease heartbeats; a dead-session lease is reclaimable — REUSE CLAIM-LADDER-HEALTH's
       liveness (do not duplicate). A stale lease never permanently blocks.
  Keep it CHEAP: the thinnest slice is the write-boundary check (refuse main-checkout work-commits + refuse
  un-leased-ticket commits) — that alone stops the clobber; the full lease/worktree binding widens from there.
  PROVE IT (fail-on-revert): (a) two sessions cannot both hold the same ticket's lease; (b) a commit in the
  main checkout for a work-ticket is REFUSED; (c) a commit from a session without the ticket's lease is
  REFUSED; (d) a sanctioned land/board-hygiene commit in main is ALLOWED. Revert the gate → the clobber
  fixture succeeds → test RED.
scope: |
  A universal work-lease gate: every session (manager subagent or CG tab) must hold an atomic lease bound to
  an isolated worktree to touch a ticket; the main checkout is land/gate-only; enforced at commit/land.
  Reuses claim.sh + worktrees + CLAIM-LADDER-HEALTH liveness. Mechanizes one-checkout-one-agent so it can't
  be violated, not just documented.
ds: |
  ## Dependencies & sequence
  - depends_on: none. REUSES claim.sh (atomic claim), git worktrees, CLAIM-LADDER-HEALTH (liveness) — build
    none of them anew. Coordinate with SUBAGENT-WORKTREE-SANDBOX (this generalizes it) — fold or sequence,
    don't double-build.
  - owns its own gate + hook (fleet/work-lease.sh + a pre-commit/pre-land hook) — do NOT re-own claim.sh.
  - EXPOSES `work-lease.sh holds <ticket>` (quiet exit-0/1 predicate): the clean callable interface
    CLAIM-LEASE-EXACTLY-ONCE composes with. Do not re-implement the "does this session hold ticket X?" check.
status: |
  ## Fix pass (2026-07-24 — adversarial-review NEEDS-FIX resolved, PR #204)
  Review found the gate only HALF-closed the double-claim leak (commit-time only, inert until manually
  installed, no tests, a fail-open hole, and a forked second store). All six findings fixed:
  1. DISPATCH-time enforcement. The lease IS claim.sh's atomic claim now, so dispatch is gated at the
     claim: fleet-droid.sh acquires via claim.sh BEFORE launch (existing), and the two paths are mutually
     exclusive by construction — a claim.sh claim makes `work-lease acquire` REFUSE, and an acquired ticket
     is SKIPPED by claim.sh. Manager ad-hoc launches use `work-lease.sh dispatch <t> -- <cmd>` (acquire-or-
     refuse-then-exec). A launch for an already-held ticket never runs.
  2. Auto-wired. `work-lease.sh ensure` (idempotent) is fired by fleet/hooks/session-start.sh (every
     session) and fleet-droid.sh (every droid) — no manual `install`; a fresh checkout is not inert.
  3. Tests: fleet/tests/work-lease.test.sh (16 assertions, hermetic, in the CI allowlist). Fail-on-revert
     verified: dropping the acquire conflict branch -> 4 RED; restoring the fail-open -> 1 RED; making
     pre-commit pass -> 2 RED.
  4. Fail-CLOSED: an unmapped-branch worktree (branch resolves to no ticket) is now REFUSED loudly, not
     passed silently. branch->ticket now reuses _lib.sh's ticket_for_branch (the `branch:` field).
  5. ONE store: dropped the parallel state/leases/. acquire/check/release/heartbeat/bind all operate on
     claim.sh's state/claims/<ticket> under the same state/lock flock. No second lock, no second store.
  6. This board ticket updated (satisfies the substrate gate).
  Also touches (not owned): fleet/hooks/session-start.sh (+1 ensure line), fleet/fleet-droid.sh (ensure +
  post-worktree bind), fleet/checks/rig-ci-scope.sh (CI allowlist row).
