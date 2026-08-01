repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 0
branch: feat/work-lease-gate
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
