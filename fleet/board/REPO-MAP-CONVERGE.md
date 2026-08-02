repo: charon-private
tier: strong
  # priority inherited: blocks a P0 ticket
priority: 0
difficulty: 3
work_class: refactor
branch: feat/repo-map-converge
depends_on: VERIFY-MERGED-REPO-AWARE, REPO-FIELD-REQUIRED, REPO-DECL-CENTRAL, SYNC-SCHEDULE, GH-SEAM-CHOKEPOINT
real-dep: VERIFY-MERGED-REPO-AWARE — that branch establishes fleet/_lib.sh as the SINGLE HOME of the
  repo->path/slug map. Converging the remaining copies onto a home that does not exist yet is
  impossible; this ticket deletes copies and points them at that home. Disjoint owns by design (that
  branch owns _lib.sh; this ticket must NOT touch it).
real-dep: REPO-DECL-CENTRAL — it migrates the FIRST consumer set (handoff.sh, retire-done.sh,
  handoff-check.sh, land-needs-push.sh) onto the canonical decls. This ticket migrates the SECOND set
  (validate_board.sh, preflight.sh, checks/base-integrity.sh). Same pattern, and the convergence gate
  added here would go RED against the un-migrated first set, so it must land after.
owns: fleet/validate_board.sh, fleet/preflight.sh, fleet/checks/base-integrity.sh, fleet/checks/repo-map-single-home.sh, fleet/tests/repo-map-converge.test.sh
serial_justified: |
  the 5 owned surfaces are the CALL SITES of ONE map plus the gate that enforces it —
  converging them is the entire ticket, and splitting per-file recreates the exact
  re-implemented-per-consumer defect being fixed. It is also unsafe in halves: the single-home gate
  goes RED against any consumer not yet migrated, so a partial migration ships a permanently-red gate
  (or forces it warn-only, which is the current unenforced state). The fail-on-revert test "a NEW
  private map is rejected" is only meaningful once _lib.sh is the sole remaining home — that is one
  invariant across all five files. The lint-only half CAN be split out first if a tab needs feeding;
  that option is recorded under free-now in ds:.
accept: |
  PROBLEM. The repo->path/slug map is implemented independently in multiple places and DRIFTS. All
  sites below were VERIFIED IN CODE 2026-07-18 (re-grep before editing; line numbers drift):
    - fleet/validate_board.sh:82-98 — a THIRD, PYTHON copy: `PRODUCT_REPO = os.environ.get(...)` plus
      its own `REPO_ROOTS` dict (charon/product/keystone/ksf/charon-private/rig/fleet) and
      `repo_root()`. Independent of _lib.sh and of the shell copies; nothing keeps them in agreement.
    - fleet/preflight.sh:383 (in detect_needs_push) and fleet/preflight.sh:438 (in done_merge_gate) —
      `_vm_refresh` is called ID-LESS. It cannot know WHICH repo the ticket lives in, so it refreshes
      one repo's ref regardless. A stale RIG ref therefore still FALSE-NEGATIVES a fresh rig merge —
      the exact staleness the "M1" comments at both sites claim to have fixed.
    - fleet/checks/base-integrity.sh:73 — `_vm_refresh` again called ID-LESS.
    - fleet/checks/base-integrity.sh:63 — `repo="$(_vm_repo)"` is TICKET-INDEPENDENT even though the
      script has ALREADY resolved `$id` and `$bfile` three lines earlier (:58-60). It then hard-fails
      with "product repo not found" — the message itself assumes the product repo.

  THIS IS A CLASS ISSUE, not four bugs. It is the handoff's §4 class-issue #1: "board-field predicates
  re-parsed per consumer and drift" — the precedent being the `parked:` predicate, which was WRONG in
  4 of 4 copies. Same shape, same cause, same fix: ONE implementation, and a gate that stops copy #2.

  DO.
    (a) DELETE the validate_board.sh Python copy; read the map from the ONE home (_lib.sh) rather
        than restating it. If a Python consumer genuinely cannot source shell, emit the map from
        _lib.sh and CONSUME it (generated, not hand-maintained) — a generated copy is acceptable, a
        hand-kept parallel dict is not. Do NOT invent a fourth format.
    (b) Make `_vm_refresh` TICKET-AWARE and pass the id at all three sites (preflight.sh:383, :438,
        base-integrity.sh:73) so it refreshes the ref of the repo the TICKET lives in.
    (c) base-integrity.sh:63 — resolve the repo from the already-known ticket, not ticket-independently.
        Fix the hard-fail message to name the resolved repo rather than asserting "product".

  FAIL-ON-REVERT (fleet/tests/repo-map-converge.test.sh — REQUIRED, all three):
    (1) NO SECOND MAP (fleet/checks/repo-map-single-home.sh, the durable half): feed the gate a
        FIXTURE fleet script that declares its own repo->path or repo->slug map (e.g. a literal
        `/home/stack/code/charon` bound to a repo key, or a private REPO_ROOTS-shaped table) -> gate
        RED. Point the fixture at the canonical home -> GREEN. Revert the gate -> the fixture stops
        failing -> the test fails. Allow-list ONLY fleet/_lib.sh.
    (2) STALE RIG REF NO LONGER FALSE-NEGATIVES: with a RIG ticket whose merge exists on the remote
        but NOT in the local rig ref, assert the gate resolves it MERGED. Revert the ticket-aware
        _vm_refresh -> the rig ref stays stale -> false-negative returns -> RED.
    (3) VALIDATOR READS THE ONE MAP: change the canonical map in _lib.sh (temp fixture) and assert
        validate_board's resolution CHANGES with it. Revert to the private Python dict -> the
        validator ignores the canonical map -> RED.

  GREEN-IS-NOT-PROOF (explicit): the whole rig suite is GREEN right now with three divergent copies
  live and a recorded phantom-merge on the record (REPO-DECL-CENTRAL). Nothing exercises a
  cross-repo resolution, so the suite CANNOT go red on a stale-ref false-negative. A test asserting
  that today's three copies happen to agree is a tautology — they agree until someone edits one.
  Only test (1)'s fixture-driven "a NEW copy is rejected" is durable. Reviewer: confirm no test
  asserts value-equality across the copies, and that _lib.sh is the sole allow-listed home.
scope: |
  Converge the repo->path/slug map onto the single _lib.sh home, make the three id-less _vm_refresh
  call sites and base-integrity's ticket-independent repo resolution ticket-aware, and add a gate
  that FAILS if any fleet script implements its own repo map. Handoff §4 class-issue #1
  (board-field predicates re-parsed per consumer and drift; `parked:` was wrong in 4/4 copies).
  [[config-ssot-git-manifest]] [[no-hardcoded-cross-boundary-paths]] [[decomposed-by-design]]
  [[gates-must-actually-run]] [[reviews-use-our-own-tools]] [[always-fix-catalog-mismatches]]
ds: |
  ## Dependencies & sequence
  depends_on: VERIFY-MERGED-REPO-AWARE and REPO-DECL-CENTRAL (both justified in real-dep: fields
    above — the canonical home must exist and the first consumer set must be migrated before the
    convergence gate can be green); REPO-FIELD-REQUIRED, SYNC-SCHEDULE and GH-SEAM-CHOKEPOINT are
    SHARED-OWNS single-writer sequencing, not preference:
      - fleet/validate_board.sh is also owned by REPO-FIELD-REQUIRED (and transitively by
        PROJECT-MEMBERSHIP-GATE + CREATION-GATE-DECOMPOSE-WIRE, which REPO-FIELD-REQUIRED depends on).
      - fleet/preflight.sh is also owned by SYNC-SCHEDULE (live). FOREMAN-WIRE is done and
        BENCH-OOB-GRADING is parked, so neither constrains scheduling.
      - fleet/checks/base-integrity.sh is also owned by GH-SEAM-CHOKEPOINT (live).
    Touch each file ONCE, after its other owner lands ([[optimize-execution-wallclock-tokens]]).
  IS SSOT-DRIFT-GATE THE RIGHT HOME? CHECKED — NO, and it must NOT be duplicated. SSOT-DRIFT-GATE's
    own `reuse:` field states verbatim that per-fact SSOTs are already ticketed
    ("REPO-DECL-CENTRAL = repo paths") and that the gate "COMPOSES them via SSOT-REGISTRY.tsv, it
    does NOT re-own their facts". So it ENFORCES value-agreement between REGISTERED readers; it
    cannot detect a NEW, UN-REGISTERED copy appearing — which is exactly failure mode (1) here, and
    exactly how the third Python copy arrived. Different mechanism (source-pattern lint vs
    registry-driven value diff), so both are needed and neither is redundant.
    COMPOSITION REQUIRED, NOT A PARALLEL GATE: register the repo->path/slug fact as a row in
    SSOT-REGISTRY.tsv (data feed only — no code edit, no build dep in either direction). If
    SSOT-DRIFT-GATE has already landed when this is claimed, implement the value-diff half as a
    REGISTERED RULE inside it and keep only the source-pattern lint standalone. Do not build a
    second drift engine.
  boundary: RIG-ONLY ([[product-vs-build-rig-boundary]]). No product-repo file is edited. Do NOT
    touch fleet/_lib.sh — its single writer is VERIFY-MERGED-REPO-AWARE.
  concurrency: blocked until the five deps land; then a single-writer pass over three shared rig
    scripts plus two NEW files. Do NOT decompose per-file — per-file tickets recreate the
    re-implemented-per-consumer defect this ticket exists to remove.
  free-now (no dep): fleet/checks/repo-map-single-home.sh + fleet/tests/repo-map-converge.test.sh are
    NEW files. If a tab needs feeding before the deps land, the LINT-ONLY half can be split out as a
    first PR (it will report the existing copies as known-RED until the migration lands — land it
    warn-only, then flip to blocking). Manager's call, not the droid's.
  reads-only (no owns claim): fleet/_lib.sh, fleet/done.sh — consumed, never edited here.
  wave: rig board correction 2026-07-18.
  repo: charon-private (rig).
note: |
  Created 2026-07-18 during board maintenance, from the REPO-DECL-CENTRAL phantom-merge correction.
  All four residual sites verified in code that day: validate_board.sh:82-98 (Python REPO_ROOTS +
  repo_root()), preflight.sh:383 and :438 (id-less _vm_refresh), base-integrity.sh:73 (id-less
  _vm_refresh) and :63 (ticket-independent _vm_repo despite $id resolved at :58). Sibling of
  REPO-FIELD-REQUIRED: that one requires the ticket to DECLARE its repo, this one makes every
  consumer RESOLVE it the same way. ADVERSARIAL REVIEW REQUIRED (trust): a stale-ref false-negative
  feeds gates that authorise destructive actions.
