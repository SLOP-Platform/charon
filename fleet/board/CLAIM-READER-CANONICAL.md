repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: rig-meta
branch: fix/claim-reader-canonical
owns: fleet/_lib.sh, fleet/reap-orphans.sh, fleet/reconcile-stale-claims.sh, fleet/status.sh, fleet/board.sh, fleet/ladder-health.sh, fleet/tests/claim-reader-canonical.test.sh
serial_justified: |
  One grammar cannot be landed in parallel lanes. The whole defect is that five readers each
  carried their own private copy of the claim-file parse and three of them had already drifted
  off the on-disk format. Splitting the fix by file would recreate exactly the condition being
  removed — a window in which some readers use the shared reader and some still use their own —
  and the shared function has to exist in the same commit as its first caller or the callers
  do not run at all.
substrate: N/A
substrate-novel: |
  There is nothing to adopt. The artifact being parsed is the rig's own claim marker, a file
  format this repo invented and writes from two of its own scripts, so no external library has
  any notion of it.
  In-tree was checked first, and one prior art genuinely exists: work-lease.sh:claim_epoch /
  lease_wt / lease_session already read BOTH shapes correctly and have done so since the lease
  writer landed. That is the proof the dual format is understood somewhere; it is not a reader
  the other scripts can call, because work-lease.sh is an executable with its own arg parser,
  lock acquisition and state-root resolution — sourcing it to borrow three functions would run
  its whole preamble. The novel slice is therefore only the RELOCATION of that already-correct
  grammar into _lib.sh (which every one of these scripts already sources) plus the two
  properties none of the existing copies had: an explicit UNKNOWN verdict and a loud,
  fail-closed report for it.
  The `key: value` parse itself is NOT rewritten — claim_field delegates to _lib.sh:_vm_meta,
  the ONE board-field parser, rather than adding a second grammar for the same shape.
source: |
  Measured live 2026-08-01. `fleet/reap-orphans.sh` printed
  `SKIP <id> (claim owner 'ticket:' has no parseable PID — format drift?)` and exited 0 for
  every work-lease claim. A read-only sweep of the 19 claims held at the time found 10 whose
  owner is dead — 2 by dead PID, 8 by a heartbeat hours stale — none of which the reaper could
  ever have released.
note: |
  ## THE DEFECT — A COMMENT THAT DESCRIBED A FORMAT THAT NO LONGER EXISTED
  `state/claims/<TICKET>` has TWO live writers, and both shapes are present in the SAME
  directory right now. `claim.sh:337` writes a legacy one-liner `<tier>-<pid> <ISO8601Z>`.
  `work-lease.sh:write_lease` writes a `key: value` block whose owner is the `session:` field.
  This is not a migration awaiting a cutover; it is a permanent dual format.
  `reap-orphans.sh` read the owner with `awk '{print $1}'` under a comment asserting the legacy
  shape. On a lease file that awk emits field 1 of EVERY line, so the owner came back as the
  literal `ticket:` followed by four more keys, the PID parse failed, and the whole thing fell
  into a `SKIP` branch that counted the claim as LIVE and exited 0.

  ## WHY THAT IS WORSE THAN A PARSE BUG
  The parse is the shallow half. The deep half is that an unreadable claim DEGRADED TO A
  SILENT SKIP. A dead droid's claim was never released, the ticket froze as `claimed` forever,
  the board silently lost claimable depth, and nothing appeared on stderr or in the exit code
  for the operator to notice. A sweeper that cannot act must SAY SO.

  ## THE OPPOSITE FAILURE IS WORSE STILL
  The fix must not answer silence with over-reaping. Releasing a claim you cannot parse can
  hand a LIVE droid's ticket to a second droid, and one-checkout-one-agent is a hard rule.
  So UNKNOWN is a third verdict, distinct from both live and dead: report it loudly, exit
  non-zero, and KEEP the claim. Fail closed.

  ## SCOPE
  1. ONE canonical reader in `_lib.sh` — `claim_is_lease`, `claim_field`, `claim_owner`,
     `claim_worktree`, `claim_owner_pid`, `claim_liveness`, `claim_unreadable_report`. Every
     consumer already sources `_lib.sh`, so this adds no new dependency edge.
  2. Liveness is ONE notion, PID-first: `kill -0` is ground truth and beats a heartbeat, which
     can be stale on a live process or fresh on a dead one. Owners with no PID (a manager or
     bridge lease) fall back to the `heartbeat:` threshold — the policy
     `reconcile-stale-claims.sh` already shipped. No third liveness signal is created.
  3. `reap-orphans.sh` and `reconcile-stale-claims.sh` lose their private copies and call it.
  4. The DISPLAY readers are the same class and are fixed with it: `status.sh` (twice),
     `board.sh` and `ladder-health.sh` each showed the literal `ticket:` as the claim holder,
     and `ladder-health.sh` additionally mislabelled every live lease STALE because its
     `droid_alive` matched a `fleet-droid.sh` command line that a lease owner never has.
  5. NOTHING is released by hand. The live claims are audited read-only only.

  ## DONE CONTRACT — RED THEN GREEN
  Hermetic. A temp fleet dir per arm, a genuinely dead PID and a genuinely live one; the real
  `state/claims/` is never touched.
    a. Lease claim owned by a DEAD pid is classified DEAD and RELEASED under `--apply`.
       Revert the reader and this returns to SKIP/live. This is the reported defect.
    b. Lease claim owned by a LIVE pid is untouched under `--apply`. Guards the over-reap
       direction, which is the unrecoverable one.
    c. Unreadable claim: banner on STDERR, surfaced on stdout, sweep exits NON-ZERO, and the
       claim is STILL PRESENT after `--apply`. Drop the loudness and c1/c3/c5 go red; drop the
       fail-closed hold and c4 goes red.
    d. Legacy one-liner still reads live and dead correctly — the fix must not trade one
       format for the other.
    e. `reconcile-stale-claims.sh` has the same three properties from the same shared reader.
    f. No consumer retains a private field-1 awk over a claim file.
    g. The three display readers call `claim_owner` and retain no private parse.
    h. Unit: `claim_owner` returns non-zero on an unparseable claim and `claim_liveness`
       returns rc 2 (UNKNOWN), so unknown can never be mistaken for dead.
  Report both counts. Adjacent suites (`test_droid_reap.sh`, `reconcile-stale-claims.test.sh`,
  `ladder-health.test.sh`) must stay green.

  ## WHY PRIORITY 0
  It is a board-depth leak that is invisible by construction. Every dead droid permanently
  removes one ticket from the claimable pool and reports success while doing it, so the board
  drains monotonically and no run ever says why.

## Dependencies & Sequence

- **depends_on: none.** The reader is a pure function over a file this repo already writes. It
  imports nothing new, adds no dependency edge, and every consumer already sources `_lib.sh`.
- **Sequence: NOW, before any further claim-lifecycle work.** Both sweepers and all three
  operator views are currently reading the claim store wrong, so every downstream decision
  about who holds what is made on bad input. Anything built on top of them inherits the defect.
- **owns-collision with `KILL-PATH-WORK-GUARD` on `fleet/reap-orphans.sh` — SEQUENCED, not
  ignored.** That ticket wires a work-preservation check into the kill paths, including this
  reaper. It now declares `depends_on: CLAIM-READER-CANONICAL` so the two are merge-ordered
  rather than concurrent: the guard should be written against the corrected reader, not the
  one that cannot identify a claim owner. That is a real build/correctness prereq, not merge
  hygiene — a kill-path guard keyed off a mis-parsed owner is worse than no guard.
- **`fleet/_lib.sh`, `fleet/status.sh`, `fleet/board.sh`, `fleet/ladder-health.sh`,
  `fleet/reconcile-stale-claims.sh` and the new test path: owned by no other live ticket.**
  Verified against the live board before claiming.
- **Related, do NOT fold in:** `CLAIM-LIVENESS-BINDING`, `CLAIM-RECONCILE-INERT` and
  `STALE-CLAIM-RECONCILE` all touch claim lifecycle POLICY — what to do with a stale claim.
  This ticket is the READ only: who owns it and are they alive. Policy is unchanged.
- **Blocks / unblocks:** unblocks any correct stale-claim reclamation, because none of it can
  be right while the owner cannot be read.
