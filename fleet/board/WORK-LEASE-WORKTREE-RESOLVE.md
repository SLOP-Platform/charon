repo: charon-private
tier: strong
difficulty: 3
priority: 2
work_class: rig-meta
branch: fix/work-lease-worktree-resolve
owns: fleet/work-lease.sh, fleet/hooks/pre-commit, fleet/hooks/commit-msg, fleet/tests/work-lease.test.sh
serial_justified: ONE path-resolution contract — work-lease.sh's store derivation and the two hook shims that exec it must agree on the SAME claims dir by construction; changing one without the others reproduces the split-store defect being fixed. The `holds` arg guard is a two-line change on the same file. Not splittable into collision-free chunks.
depends_on: TICKET-MAP-GATE
dep-kind: build
real-dep: TICKET-MAP-GATE — added 2026-07-24. It OWNS fleet/work-lease.sh + fleet/tests/work-lease.test.sh
  too, and it is the ticket that actually lands the `_state_root()` git-common-dir store+lock resolution
  (BUILT+PUSHED, b784de1, 25/25 red-proofed). This ticket's own branch fix/work-lease-worktree-resolve
  @ 5d951e8 is PARTIAL — it fixes `_link_src` ONLY and fails its own first accept criterion — so it must
  NOT be marked done. What remains here after TICKET-MAP-GATE lands is the hooks/pre-commit +
  hooks/commit-msg half, which composes on top of the landed store fix.
priority_justification: P:2 (PRIORITY-LADDER "standalone, biggest blast-radius") — this defect is
  why the commit-boundary lease gate has degraded to ADVISORY-BY-BYPASS: it fires a false NO-LEASE
  on every correctly-leased worktree commit, so authors reach for WORK_LEASE_BYPASS=1. THREE
  branches did exactly that today. A guardrail that trains its users to bypass it is worse than no
  guardrail. Not P:0/P:1 — nothing is mis-merged today and it is not attached to active CG work;
  above P:3/P:4 because it silently voids a landed gate fleet-wide.
work_class_note: rig-meta — the rig's own commit-boundary guardrail. No product code.
state: ROOT-CAUSED, PARTIALLY BUILT — NOT DONE. Both symptoms below were reproduced today; do NOT
  re-derive them.
partial_fix_warning: |
  DO NOT MARK THIS TICKET DONE ON THE PARTIAL FIX. Commit 5d951e8 on branch
  fix/work-lease-worktree-resolve fixes `_link_src` ONLY. It does NOT satisfy accept criterion 1:
  the CLAIMS STORE is still resolved from the INVOKING CHECKOUT's script location, so a lease
  acquired from inside a worktree still writes that worktree's fleet/state/claims while the shared
  hook reads the MAIN checkout's. That split store is the symptom behind every lease refusal seen on
  2026-07-24. The remaining work is the `git rev-parse --git-common-dir` (or main-worktree-toplevel)
  derivation demanded by accept criterion 1, plus the fail-on-revert test that acquires from inside
  a fixture worktree and runs the hook from that worktree.
  Whoever closes this ticket must show BOTH: (i) the store path derived from the git common dir, and
  (ii) the worktree-acquire -> hook-check case passing and going RED when the derivation is
  reverted. A `_link_src`-only diff is a REFUSED close. [[document-model-self-report-lies]]
source: Session 2026-07-24 board repair. Predecessor WORK-LEASE-GATE (DONE) built this gate;
  this ticket fixes two defects in the landed result.
note: |
  TWO SYMPTOMS, ONE TICKET. Both are in the landed work-lease gate.

  SYMPTOM 1 — the commit hook resolves the WRONG checkout's lease store (the real defect).
    /home/stack/charon-private/.git/hooks/pre-commit is an ABSOLUTE symlink to
    /home/stack/charon-private/fleet/hooks/pre-commit, and that shim does:
        FLEET="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
        exec bash "$FLEET/work-lease.sh" pre-commit
    work-lease.sh then derives its store from its OWN location (fleet/work-lease.sh:24-26):
        FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        CLAIMS="$FLEET/state/claims"
    Git worktrees SHARE the main repo's hooks directory, so the hook ALWAYS execs the MAIN
    checkout's work-lease.sh and therefore always reads /home/stack/charon-private/fleet/state/claims.
    But an author working inside a worktree acquires the lease by running that worktree's copy —
    `bash fleet/work-lease.sh acquire <ticket>` from /home/stack/charon-private-wt/<TICKET> —
    which writes /home/stack/charon-private-wt/<TICKET>/fleet/state/claims/<ticket>.
    Net effect: the lease IS held, the hook cannot see it, the commit is refused as un-leased, and
    the author's only escape is WORK_LEASE_BYPASS=1. The gate's own doctrine comment ("ONE STORE,
    ONE LOCK — do NOT fork a second") is violated in practice by path resolution: there is one
    store PER CHECKOUT.

  SYMPTOM 2 — `work-lease.sh holds` crashes on missing arg.
        $ bash fleet/work-lease.sh holds
        fleet/work-lease.sh: line 136: $1: unbound variable
    fleet/work-lease.sh:136 is `cmd_holds() { cmd_check "$1" >/dev/null 2>&1; }` under `set -u`,
    and the dispatcher at :308 passes "$@" through unchecked. `holds` is documented as the "clean,
    callable interface CLAIM-LEASE-EXACTLY-ONCE composes with" — a quiet predicate that dies with a
    bash error instead of returning 1 is not composable, and a caller using `if ! holds ...` gets a
    crash on the very path that is supposed to be the safe check.
accept: |
  - Single canonical lease store, resolved from the GIT COMMON DIR, not from the executing script's
    location: every worktree and the main checkout must agree on ONE state/claims path (e.g. derive
    from `git rev-parse --git-common-dir` / the main worktree toplevel) so a lease acquired inside a
    worktree is the same file the hook checks. Reuse the existing store — do NOT fork a second.
  - Fail-on-revert test (fleet/tests/work-lease.test.sh, hermetic — the existing harness already
    copies the real scripts into a temp FLEET): acquire a lease from INSIDE a fixture worktree, then
    run the pre-commit hook from that worktree → PASS. Revert the resolution fix → the test goes RED
    with the NO-LEASE refusal. This is the exact case that is broken today and it currently has no
    coverage.
  - `work-lease.sh holds` with NO argument exits non-zero QUIETLY (no bash error, no stderr noise),
    and with a valid/invalid ticket returns 0/1 as documented. Covered by the same test file.
  - BYPASS ACCOUNTING: report how many WORK_LEASE_BYPASS=1 commits exist on the current open
    branches (three are known from 2026-07-24) and confirm each is legitimate work, so the fix does
    not silently bless a real double-claim. If the bypass env var is kept, it must be LOUD (logged
    to state) rather than silent.
  - bash fleet/validate_board.sh GREEN.
scope: |
  Path resolution + the `holds` arg guard + their tests. Does NOT redesign the lease protocol, does
  NOT change claim.sh's store format, and does NOT remove WORK_LEASE_BYPASS (making the gate
  usable is the prerequisite for later removing its escape hatch, not the same ticket).
ds: |
  ## Dependencies & sequence
  No depends_on. Its owned surface (fleet/work-lease.sh, fleet/hooks/pre-commit,
  fleet/hooks/commit-msg, fleet/tests/work-lease.test.sh) collides with NO live board ticket —
  verified against the full board. Claimable NOW, runs concurrently with everything else on the
  board.
  Predecessor WORK-LEASE-GATE is DONE (this fixes its landed result), so no edge is needed.
  Wave note: land this EARLY relative to the other three repaired tickets — TIER-BALANCE,
  FLEET-DEMAND-BROKER and GATE-REENTRANCY-GUARD are all worktree-resident branches whose authors
  hit exactly this false NO-LEASE, so fixing it removes the bypass pressure from their landings.
  Concurrency safety: the fix changes hook resolution — test hermetically in the existing temp-FLEET
  harness, never by re-pointing the live .git/hooks symlinks mid-session.
