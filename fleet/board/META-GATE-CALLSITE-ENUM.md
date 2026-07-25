repo: charon-private
tier: strong
difficulty: 3
priority: 1
work_class: rig-meta
branch: feat/meta-gate-callsite-enum
owns: fleet/checks/gate-creation-standard.sh, fleet/tests/gate-creation-standard.test.sh, fleet/tests/test_gate_creation_standard.sh
depends_on:
source: fleet/state/reviews/CLASS-SCAN-UNAUDITED-GATES-agen-kolar.md §4 "Root cause" + generalization
  step 1 ("Enumerate by CALL SITE, not by directory"). §3 rank 1-3, 7. Findings were verified BY
  EXECUTION in a scratch copy (see that doc §5); re-verify at build time, do not trust the counts.
note: |
  ROOT CAUSE, stated exactly: `fleet/checks/gate-creation-standard.sh:155` decides "is this a gate
  I must audit?" by asking WHERE THE FILE LIVES (`"$CHECKS_DIR"/*.sh "$CHECKS_DIR"/*.py`).
  Membership in the audited population is therefore an author's free choice — put the enforcement
  logic anywhere else (an inline block in validate_board.sh, an inline `*_gate()` in preflight.sh,
  a top-level fleet/*.sh, a CI step) and it is exempt with NO override record and NO signal. The
  escape is not a bug in a rule; it is the ADDRESSING SCHEME of the rule. 23 enforcement checks are
  unaudited today because of it, and the trigger instance (the tier-drift block inlined into
  validate_board.sh, commit 0a759a8) is exactly this escape being used.
  ANTI-ACCRETION (binding): NO new script. One file changes. A new `fleet/checks/inline-gate-audit.sh`,
  a per-instance tier-drift checker, or a separate "is-it-wired" script are EXPLICITLY REJECTED —
  all three re-create the class one directory over. [[fix-root-cause-never-workaround]]
  SIZING REALITY (measured 2026-07-24): of the 21 files in fleet/checks/ today, only ONE
  (gate-creation-standard.sh itself) has an unreachable companion; but the call-site union pulls in
  the §2e population (validate_board.sh, handoff-check.sh, push-verify.sh, release.sh, reap-orphans.sh,
  lease-enqueue.sh, access-check.sh, cg-drift.sh, dark-work-check.sh, reuse-check.sh, project-audit.sh)
  which has NO companion tests at all. Those are FROZEN into one explicit named grandfather list, not
  silently skipped — the point is that the exemption becomes a RECORD instead of a placement trick.
accept: |
  A. ENUMERATOR (fleet/checks/gate-creation-standard.sh §B, the line-155 glob). The audited set
     becomes the UNION of:
       (a) today's `"$CHECKS_DIR"/*.sh "$CHECKS_DIR"/*.py` (unchanged), and
       (b) every script path INVOKED by the rig's enforcement entrypoints: fleet/preflight.sh,
           fleet/gate.sh, fleet/land.sh, fleet/land-push.sh, fleet/validate_board.sh,
           fleet/foreman.sh, fleet/hooks/*, fleet/watchdog/*.sh, .github/workflows/*.yml.
     The entrypoint list is an EXPLICIT frozen constant with an env seam (`GCS_ENTRYPOINTS`,
     matching the file's existing GCS_* self-test seam convention). REUSE `in_list`/`norm`
     verbatim — do not write a second matcher.
  B. NON-VACUOUS, THREE WAYS (zero items examined = RED, never GREEN):
     - the derived call-site set resolving to ZERO paths => RED `callsite-enum-vacuous` (S2);
     - an entrypoint named in the frozen list that does not exist on disk => RED (S3 UN-GAMED —
       the node-set cannot silently shrink, same shape as the existing `check-removed` rule);
     - a floor `CALLSITE_MIN` (seam `GCS_CALLSITE_MIN`), seeded at land time from the MEASURED
       count, append-only: a derived set below the floor => RED `callsite-set-shrunk`.
  C. FROZEN EXEMPTIONS, NOT SILENT ONES. Pre-existing call-site members with no companion test are
     enumerated by NAME into one explicit `GRANDFATHER_CALLSITE_NO_TEST` default (same style as the
     existing GRANDFATHER_NO_TEST). Any invoked script that is neither in fleet/checks/ nor in that
     frozen list => RED `unaudited-callsite: <path> (S1 RED-PROOFED)`. A name in the frozen list
     that no longer exists on disk => RED (stale exemption). The list may only SHRINK.
  D. THE PROOF MUST RUN. `git mv fleet/tests/test_gate_creation_standard.sh
     fleet/tests/gate-creation-standard.test.sh` so `fleet/gate.sh`'s `*.test.sh` glob actually
     executes it (today it matches neither that glob nor rig-ci-scope.sh:CI_SUITES). The suite
     currently FAILS (PASS=30 FAIL=1 as of the scan) — it must exit 0 at land, with the fixed
     assertion explained in the review-log. Fixing it by DELETING the failing case is refused.
  E. FAIL-ON-REVERT (fleet/tests/gate-creation-standard.test.sh — hermetic, mktemp -d fixture tree
     driven entirely through the GCS_* env seams; no writes to the real fleet):
     1. fixture entrypoint invoking a fixture script that has no companion test => RED with
        `unaudited-callsite:`; add a companion carrying a red-proof marker => GREEN; revert the
        enumerator change => the case goes RED (the whole point: it must FAIL if reverted).
     2. TRIGGER-INSTANCE REPRODUCTION: a fixture `validate_board.sh` carrying an INLINE enforcement
        block => validate_board.sh itself is pulled into the audited set and is RED until red-proofed.
        This is the tier-drift escape; it must be impossible after this ticket.
     3. VACUITY: entrypoint set resolving to zero existing files => RED `callsite-enum-vacuous`,
        rc 1. A run that examined zero items MUST NOT be green.
     4. FLOOR: derived set below `GCS_CALLSITE_MIN` => RED `callsite-set-shrunk`.
     5. STALE EXEMPTION: a grandfathered name deleted from the fixture tree => RED.
  F. `bash fleet/tests/gate-creation-standard.test.sh` exits 0; `bash fleet/gate.sh` picks the suite
     up by glob (show the run line); `bash fleet/validate_board.sh` rc 0 modulo pre-existing reds.
  G. ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder): this file is the rig's meta-gate
     of last resort. Report the meta-gate's finding count BEFORE and AFTER; a finding count that
     DROPS is a red flag to be explained, not celebrated.
scope: |
  Rig-only [[product-vs-build-rig-boundary]]. This ticket changes WHO IS AUDITED (leg i) only. The
  "the red-proof must actually RUN" assertion is META-GATE-REDPROOF-REACHABLE (leg ii); wiring the
  meta-gate into preflight is WCI-CONTENTION-TEETH (legs iii+iv, absorbed into that ticket
  2026-07-24). It does NOT touch
  fleet/preflight.sh, fleet/checks/rig-ci-scope.sh, or the GATE-GAP-LEDGER (all owned elsewhere).
ds: |
  ## Dependencies & sequence
  depends_on: (none) — WAVE 1, first of the four legs. No live ticket owns
  fleet/checks/gate-creation-standard.sh or either test path (verified 2026-07-24 by grepping every
  `owns:` line on the board); CONFIG-SSOT-CANARY-REGISTER mentions the meta-gate only in PROSE and
  owns fleet/tests/config-ssot-gate.test.sh, so there is no collision.
  CONCURRENCY-SAFETY: META-GATE-REDPROOF-REACHABLE edits the SAME check file and the SAME test file
  and is sequenced AFTER this ticket (it depends_on this id) — never co-write them from two branches.
  Runs in PARALLEL with META-GATE-FINDINGS-ZERO (disjoint files). WCI-CONTENTION-TEETH (which now
  carries legs iii AND iv plus the preflight.sh decomposition) depends_on this ticket, so it is
  sequenced AFTER, not alongside.
  Branch feat/meta-gate-callsite-enum is unused (no other ticket declares it).
