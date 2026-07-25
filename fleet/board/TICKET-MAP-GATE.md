repo: charon-private
tier: strong
difficulty: 3
priority: 1
work_class: rig-meta
branch: feat/branch-ticket-map-gate
owns: fleet/work-lease.sh, fleet/fleet-droid.sh, fleet/tests/work-lease.test.sh
depends_on:
dep-kind:
serial_justified: ONE store-resolution contract plus its single dispatch anchor. work-lease.sh's
  `_state_root()` fix and the ten-line `guard-branch` call at fleet-droid.sh:375 are two halves of the
  same gate — a guard that refuses at dispatch is meaningless if the store it consults is the split
  one, and fixing the store without moving enforcement earlier leaves the commit-time refusal that
  produced the built-but-unlandable branches. Splitting them ships a half-gate in either order. It is
  moot in any case: the work is ALREADY BUILT as one commit (b784de1) and pushed; decomposing it now
  would mean unpicking a landed-ready branch for zero wall-clock gain.
priority-why: |
  P:1 — attached CG work on the live work-lease/branch-gate CG, already BUILT and pushed (b784de1) so
  it costs the board one land, and it SUPERSEDES the work-lease.sh half of the P:2
  WORK-LEASE-WORKTREE-RESOLVE. Not P:0 (HANDOFF-GOTCHA-VERIFIABLE is the keystone gating the landing
  queue); not P:4 (it removes the defect that refused every lease this session — four finished
  branches blocked — which is more than a quick win). Operator ranked it #4 of 5 for the next session.
source: 2026-07-24 board audit — branch feat/branch-ticket-map-gate is COMMITTED (b784de1) and PUSHED
  with an active claim marker (fleet/state/claims/TICKET-MAP-GATE, session agen-kolar) but NO board
  ticket; validate_board.sh red'd `orphan-marker: state/claims/TICKET-MAP-GATE matches no board ticket`.
  This ticket DESCRIBES work that is already built; it does not propose new design.
motivating-evidence: |
  ### FOUR REAL INSTANCES IN ONE DAY (2026-07-24) — the case for landing this is concrete, not theoretical.
  Four branches needed `WORK_LEASE_BYPASS=1` to commit PURELY because no board ticket mapped them. The
  bypass is not misuse: the work was real and finished, and the lease gate refuses at COMMIT — the point
  at which the only options left are "bypass" or "throw the work away". That is the defect this ticket
  moves to DISPATCH.
    1. `fix/litellm-order-precall` @ 4b9d401 (PRODUCT) — VERIFIED. Committed with the bypass; money-path
       chain-order + pre-call-checks fix, 300 real completions of evidence. Now boarded as
       LITELLM-ORDER-PRECALL, created after the fact solely to make the branch landable.
    2. `fix/ruff-security-rules` @ f4605c3 (PRODUCT) — VERIFIED. The ticket (RUFF-SECURITY-RULES) was
       requested AHEAD of the commit precisely to avoid a fifth bypass; the sub committed before the
       ticket existed anyway. 32 files, security ratchet.
    3. `feat/branch-ticket-map-gate` @ b784de1 — THIS TICKET'S OWN BRANCH. Committed and pushed with an
       active claim marker and NO board ticket; validate_board.sh red'd
       `orphan-marker: state/claims/TICKET-MAP-GATE matches no board ticket` (see source:). The gate
       that fixes the class was itself an instance of the class.
    4. A fourth branch is reported by the coordinator but I did NOT verify it by name — RECORDED AS
       UNCONFIRMED rather than guessed [[confirm-dont-trust-documentation]]. Three verified instances
       already make the case; do not let the unnamed fourth become a fact by repetition.
  WHY THIS IS THE RIGHT FIX AND NOT "remember to make a ticket first": every one of these was a
  competent operator doing real work. A rule that four separate sessions broke in one day is not a
  discipline problem, it is a mechanism gap [[detection-ticketed-never-built]]. `guard-branch` at
  fleet-droid.sh:375 refuses an unmapped branch at DISPATCH, when the cost of complying is "write the
  ticket", instead of at commit, when the cost is "bypass or lose the work".
note: |
  STATE: work is COMPLETE and COMMITTED in the worktree /home/stack/charon-private-wt/TICKET-MAP-GATE
  on branch feat/branch-ticket-map-gate @ b784de1 (3 files, +215/-9), pushed. This ticket exists so the
  branch is board-mapped and landable, and so the orphan claim marker resolves.
scope: |
  Two defects in the work-lease gate, one root cause each.

  (1) CLAIMS-STORE SPLIT (the reason the lease gate degraded to advisory-by-bypass). `_state_root()`
  now resolves BOTH the claims store and the lock from `git rev-parse --git-common-dir`, so a lease
  acquired INSIDE a worktree is visible to the hook reading the MAIN checkout. Before this, a worktree
  wrote its lease to a store the commit hook never read, so the hook fired a false NO-LEASE refusal on
  legitimate work. That split caused every lease refusal this session — four finished branches were
  blocked by it, and the standard response became WORK_LEASE_BYPASS, i.e. the gate stopped gating.

  (2) LATE ENFORCEMENT. `work-lease.sh guard-branch` is new and is wired into fleet/fleet-droid.sh:375,
  BEFORE `p0_worktree_setup` at :408 — so an UNMAPPED branch is refused at DISPATCH, before any work
  happens, instead of at COMMIT, after the work is already done. Refusing at commit-time is what
  produced built-but-unlandable branches; refusing at dispatch is the class fix.
  [[gates-must-actually-run]] [[fix-root-cause-never-workaround]] [[detection-ticketed-never-built]]
accept: |
  BUILT + RED-PROOFED (verify by re-running, do not rebuild):
  - fleet/tests/work-lease.test.sh: 25/25 green, exit 0.
  - FAIL-ON-REVERT, all three legs, each verified by EXECUTION:
      * revert the `_state_root()` git-common-dir store resolution => tests 16, 17 FAIL, exit 1.
      * make `guard-branch` `return 0` unconditionally => tests 12, 13, 14 FAIL, exit 1.
      * unwire guard-branch from fleet/fleet-droid.sh => tests 15, 15b FAIL, exit 1.
    Reviewer: physically apply each revert and confirm the named tests go RED. A test suite that stays
    green under any of the three reverts is measuring nothing.
  - REACHABLE BY A REAL RUNNER: fleet/tests/work-lease.test.sh is `*.test.sh`, so fleet/gate.sh:33
    picks it up. (A `test_*.sh` name would NOT be matched by that glob.)
  - NON-VACUOUS / EARLY ENFORCEMENT CONFIRMED LIVE: `work-lease.sh guard-branch` returns rc=1 for
    every currently-unmapped branch it was run against — feat/fixture-bypass-gate,
    salvage/preflight-verify-merged-ghcache-wip, feat/substrate-first-gate-v2, feat/work-lease-gate,
    feat/branch-ticket-map-gate. It refuses real branches, not only fixtures.
  - bash fleet/validate_board.sh GREEN, and the `orphan-marker: state/claims/TICKET-MAP-GATE` RED is
    cleared by this ticket existing.
known-open: |
  RECORDED, NOT FIXED (do not silently drop): bare `git worktree add` is STILL UNGATED.
  `leak_worktree_setup` was deliberately left untouched because the test suite and
  fleet/dogfood-eval.sh drive it with non-ticket branches, so gating it there would break both. The
  dispatch path (fleet-droid.sh) IS gated; the bare-worktree path is not. Needs its own ticket
  (gate the bare path with an explicit, recorded exemption for the test/dogfood callers — never an
  implicit-by-shape exemption).
ds: |
  ## Dependencies & sequence
  - depends_on: NONE. Wave-1, claimable/landable immediately — the code is built, committed and pushed.
  - SUPERSEDES the work-lease.sh half of WORK-LEASE-WORKTREE-RESOLVE (fix/work-lease-worktree-resolve
    @ 5d951e8). That branch is PARTIAL and MUST NOT BE MARKED DONE: it fixes `_link_src` ONLY and fails
    its own first accept criterion (the store/lock resolution, which is what this ticket actually
    fixes). Sequencing is by MERGE ORDER, not a dep edge: this branch is BUILT and lands FIRST; what
    remains of WORK-LEASE-WORKTREE-RESOLVE afterwards is its hooks/pre-commit + hooks/commit-msg
    scope, which this ticket does NOT own and does NOT touch — the two compose.
  - DELETE `feat/work-lease-gate`: it is ALREADY MERGED into master and is 98 commits behind. There is
    nothing to land there; leaving it open keeps a stale unmapped branch in the queue (and
    `guard-branch` already refuses it).
  - owns overlap (declared, not hidden — overlap alone is not a collision under validate_board's WCI
    rules; sequencing is merge-order):
      * fleet/work-lease.sh + fleet/tests/work-lease.test.sh — also owned by WORK-LEASE-WORKTREE-RESOLVE
        (see the supersession above; this branch is built, that one is partial).
      * fleet/fleet-droid.sh — also owned by LAUNCHER-CRASH-PARTIAL-DETECT, FLEET-DEMAND-BROKER,
        FLEET-DEMAND-DRIVEN-ROUTING and DROID-LIFECYCLE-REAP. This ticket's edit is a TEN-LINE anchor
        at :375 (one guard call before p0_worktree_setup at :408); it rewrites nothing those tickets
        touch, so it composes in any merge order. It is already committed, so it should anchor first.
  - reads-only (no owns claim, no edit): fleet/hooks/pre-commit, fleet/hooks/commit-msg (owned by
    WORK-LEASE-WORKTREE-RESOLVE), fleet/dogfood-eval.sh (the bare-worktree caller in known-open).
