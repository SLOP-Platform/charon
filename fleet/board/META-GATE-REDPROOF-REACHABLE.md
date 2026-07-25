repo: charon-private
tier: strong
difficulty: 3
priority: 1
work_class: rig-meta
branch: feat/meta-gate-redproof-reachable
owns: fleet/checks/gate-creation-standard.sh, fleet/tests/gate-creation-standard.test.sh
depends_on: META-GATE-CALLSITE-ENUM
source: fleet/state/reviews/CLASS-SCAN-UNAUDITED-GATES-agen-kolar.md §4 generalization step 2
  ("Make 'the red-proof must RUN' an S1 sub-assertion") + §1 item 3 ("S1 is satisfied by a FILE,
  not by an EXECUTION") + §3 rank 1/3.
note: |
  COMPOUNDING CAUSE: the meta-gate's S1 accepts a companion test whose NAME normalizes to the
  check's and which CONTAINS the string `red-proof|fail-on-revert` (gate-creation-standard.sh:169-183).
  It never asks whether ANY RUNNER EXECUTES that test. There are exactly two real runners in the rig:
  `fleet/gate.sh` (globs `fleet/tests/*.test.sh`) and `fleet/checks/rig-ci-scope.sh:CI_SUITES` (a
  16-of-77 literal allowlist). A companion that matches NEITHER is dead on arrival — a proof no
  runner executes is not evidence, it is decoration. The meta-gate's own companion was exactly this
  (`test_gate_creation_standard.sh`: not `*.test.sh`, not in CI_SUITES, and FAILING).
  MEASURED 2026-07-24 (re-measure at build time, do not hardcode): of the 21 files in fleet/checks/,
  16 have a companion and 15 of those are already runner-reachable — the assertion is CHEAP to turn
  on for the fleet/checks population. The expensive population is the call-site set that
  META-GATE-CALLSITE-ENUM introduces, which is why that ticket lands first and freezes its
  exemptions by name.
  ANTI-ACCRETION: no new script, no new runner. The assertion READS the two existing runners'
  definitions (`fleet/gate.sh`'s glob, `rig-ci-scope.sh suites` output) and adds ONE sub-assertion
  inside the loop that is already there.
accept: |
  A. S1 SUB-ASSERTION (inside the existing companion-matching loop, not a second pass). After a
     companion is matched, additionally require it be REACHABLE BY A REAL RUNNER:
       - its basename matches `fleet/gate.sh`'s runner glob (`*.test.sh`), OR
       - it appears in `fleet/checks/rig-ci-scope.sh`'s CI_SUITES (read it by INVOKING
         `rig-ci-scope.sh suites` — do NOT re-parse the array, and do NOT edit that file: it is
         owned by HANDOFF-GATE-NONBYPASSABLE).
     Otherwise => `red "unrun-red-proof: <companion> covers <check> but is executed by no runner
     (S1/NOT-INERT — a proof no runner executes is not evidence)"`.
  B. FAIL-CLOSED ON THE RUNNER LOOKUP. If `rig-ci-scope.sh suites` is missing, non-executable, or
     exits non-zero, that is RED (`runner-set-unresolvable`) — NOT a silent fallback to
     glob-only. An unresolvable predicate must never widen the pass set. [[gates-must-actually-run]]
  C. NON-VACUOUS: if the resolved runner set (glob matches + CI_SUITES entries) is EMPTY, that is
     RED (`runner-set-vacuous`) — because with an empty runner set every companion would trivially
     be "unreachable" OR the check would trivially pass depending on branch order; either way zero
     items examined must not be green.
  D. THE ASSERTION MUST BITE ITS AUTHOR FIRST. On the real tree, `gate-creation-standard.sh check`
     must report `unrun-red-proof` for any check whose companion is unreachable, and must NOT report
     it for gate-creation-standard.sh itself once META-GATE-CALLSITE-ENUM's rename has landed.
     Record the before/after finding list in the review-log.
  E. FAIL-ON-REVERT (extend fleet/tests/gate-creation-standard.test.sh — hermetic, GCS_* seams,
     mktemp -d; ADD cases, never rewrite META-GATE-CALLSITE-ENUM's):
     1. fixture check + companion named `foo_test_helper.sh` (matches neither runner) => RED
        `unrun-red-proof`; rename it to `foo.test.sh` => GREEN; revert the assertion => the case
        goes RED. Fail-on-revert in both directions.
     2. same fixture, companion NOT `*.test.sh` but PRESENT in a stubbed CI_SUITES => GREEN
        (the CI leg of the OR is real, not decoration).
     3. stubbed `rig-ci-scope.sh` exiting non-zero => RED `runner-set-unresolvable`, rc 1.
     4. empty runner set (empty glob + empty suites) => RED `runner-set-vacuous`, rc 1.
  F. `bash fleet/tests/gate-creation-standard.test.sh` exits 0 and is executed by `fleet/gate.sh`
     (paste the runner line). `bash fleet/validate_board.sh` rc 0 modulo pre-existing reds.
  G. ADVERSARIAL REVIEW REQUIRED (reviewer != builder). Specifically check that the assertion cannot
     be satisfied by a companion that exists but whose suite body is empty — and if it can, say so
     in the review-log as a KNOWN residual with a ledger row, rather than silently widening scope.
scope: |
  Rig-only. Leg (ii) ONLY. Does NOT edit fleet/checks/rig-ci-scope.sh (owned by
  HANDOFF-GATE-NONBYPASSABLE) — it only READS its `suites` output; does not add suites to CI_SUITES;
  does not touch fleet/preflight.sh. Making the three currently-unproofed checks green is
  META-GATE-FINDINGS-ZERO's job, not this ticket's.
ds: |
  ## Dependencies & sequence
  depends_on: META-GATE-CALLSITE-ENUM — SHARED SINGLE-OWNER of BOTH
  fleet/checks/gate-creation-standard.sh and fleet/tests/gate-creation-standard.test.sh, and a real
  build prereq: this assertion lives INSIDE the loop that ticket rewrites, and its own companion is
  only runner-reachable after that ticket's `git mv`. Co-writing the two files from parallel
  branches is the multi-writer defect. WAVE 2 (immediately after leg i).
  EDGE REVIEWED 2026-07-24 (re-bundling pass) and KEPT — bucket (c) BLOCKED-ON-UNLANDED-WORK, not
  shared-file serialization: META-GATE-CALLSITE-ENUM is BUILT and pushed (feat/meta-gate-callsite-enum
  @ a92019d, unmerged). It was NOT bundled into this ticket because bundling a built-and-pushed branch
  cannot help — LANDING it does, and landing it makes THIS ticket claimable immediately. It was also
  NOT bundled with META-GATE-FINDINGS-ZERO (the other meta-gate leg) because FINDINGS-ZERO carries two
  further real prereqs (GITHUB-LIMITS-HARDENING, HANDOFF-GATE-NONBYPASSABLE, the latter itself blocked
  behind RECONCILE-WIRING): merging them would inherit a strictly DEEPER blocker set and delay leg ii
  rather than free it.
  CONCURRENCY-SAFETY: rebase onto master after META-GATE-CALLSITE-ENUM lands; never branch from it
  while it is open. Runs in parallel with META-GATE-FINDINGS-ZERO (disjoint files);
  WCI-CONTENTION-TEETH depends_on this ticket. Branch feat/meta-gate-redproof-reachable is unused.
