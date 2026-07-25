repo: charon-private
tier: strong
difficulty: 2
priority: 1
work_class: tests
branch: feat/meta-gate-findings-zero
owns: fleet/GATE-CREATION-STANDARD.md, fleet/tests/large-file-guard.test.sh, fleet/tests/rig-ci-scope.test.sh
depends_on: GITHUB-LIMITS-HARDENING, HANDOFF-GATE-NONBYPASSABLE
real-dep: GITHUB-LIMITS-HARDENING owns fleet/checks/large-file-guard.sh and is actively changing its
  behaviour (routing gh calls through gh-cache.sh). A red-proof written against the pre-change
  behaviour would be a test that passes for the wrong reason, or breaks the moment that ticket
  lands. Real correctness prereq — write the proof against the FINAL behaviour, not the current one.
real-dep: HANDOFF-GATE-NONBYPASSABLE owns fleet/checks/rig-ci-scope.sh and is adding a
  PR-changed-scoped handoff-check invocation plus new CI_SUITES entries to it. Same reasoning: the
  red-proof for rig-ci-scope.sh must exercise the scope-resolution behaviour AFTER that change,
  otherwise it locks in the old contract.
source: fleet/state/reviews/CLASS-SCAN-UNAUDITED-GATES-agen-kolar.md §3 rank 3 ("the meta-gate is
  inert AND currently RED") + §5 (its 4 live findings, verified by execution).
note: |
  BLOCKER FOR THE WIRING LEG: `bash fleet/checks/gate-creation-standard.sh check` is RED RIGHT NOW
  with 4 findings that no gate surfaces. WCI-CONTENTION-TEETH (which absorbed the former
  META-GATE-PREFLIGHT-WIRE-CLOSED and PREFLIGHT-GATE-RUN-HELPER tickets, legs iii+iv) wires it
  FAIL-CLOSED into
  preflight — so unless these are cleared first, the wiring lands and immediately blocks every
  session on debt it did not create, which is precisely how a gate gets bypassed or disabled
  [[gates-must-actually-run]]. Clearing them is not scope creep; it is what makes the fix landable.
  THE FOUR FINDINGS (re-measure at build time; do not trust this list):
    1. `no-red-proof-test: large-file-guard.sh`  -> this ticket (new companion red-proof).
    2. `no-red-proof-test: rig-ci-scope.sh`      -> this ticket (new companion red-proof).
    3. `class-untraced: ledger root_class 'no-decision-time-gate' (line 25) maps to NO item in
       fleet/GATE-CREATION-STANDARD.md` -> this ticket (trace the class in the standard).
    4. `unproofed-gate: 'reachability-gate' has no red_proof` -> NOT FIXABLE FROM THIS REPO. That
       entry lives in the PRODUCT registry /home/stack/code/charon/tools/gates.json (repo: charon).
       SURFACE IT TO THE MANAGER to open the product-repo companion ticket; do NOT add it to
       GRANDFATHER_NO_REDPROOF — grandfathering a gate that shipped with no red-proof is EXACTLY
       the class this wave exists to close, and doing so is a review-blocking failure.
  NAMING MATTERS: both new companions must be named so the meta-gate's own `norm()` matcher finds
  them AND so a real runner executes them — i.e. `fleet/tests/<check-stem>.test.sh`, picked up by
  fleet/gate.sh's `*.test.sh` glob. A companion named `test_*.sh` would satisfy the matcher and be
  executed by nobody (see META-GATE-REDPROOF-REACHABLE).
accept: |
  A. fleet/tests/large-file-guard.test.sh — a REAL fail-on-revert proof of fleet/checks/large-file-guard.sh:
     a fixture repo containing a file over the guard's threshold => the check goes RED (non-zero,
     names the file); shrink/remove the file => GREEN; revert the guard's threshold logic => RED
     again. Carries the literal `red-proof` / `fail-on-revert` marker the meta-gate greps for.
     NON-VACUOUS: a fixture with ZERO candidate files must be RED (`examined 0 files`), not green.
  B. fleet/tests/rig-ci-scope.test.sh — a REAL fail-on-revert proof of fleet/checks/rig-ci-scope.sh:
     the already-fixed fail-CLOSED behaviour of `_resolve_scope` (an unresolvable scope must RED, not
     silently narrow the suite set) plus a suites-non-empty assertion. NON-VACUOUS: `suites` returning
     zero entries => RED. Revert the fail-closed resolution => the test goes RED.
  C. fleet/GATE-CREATION-STANDARD.md — trace root_class `no-decision-time-gate` to a real checklist
     item (it is the substrate/decision-time class: a rule that only fires after the decision it was
     meant to gate has already been made). Do NOT delete the ledger row to make the finding go away —
     the ledger is APPEND-ONLY (S3 UN-GAMED) and deleting a row is itself a RED.
  D. VERDICT, MEASURED: `bash fleet/checks/gate-creation-standard.sh check` goes from 4 findings to
     exactly 1 (the product-registry `reachability-gate` item), and the remaining one is REPORTED to
     the manager with the product-repo ticket request. Paste both runs (before/after) in the PR.
     A finding count that drops for any reason other than a real fix must be explained.
  E. BOTH new suites are executed by `fleet/gate.sh` (paste the runner lines) and exit 0.
  F. `bash fleet/validate_board.sh` rc 0 modulo pre-existing reds.
  G. ADVERSARIAL REVIEW REQUIRED (reviewer != builder): confirm by EXECUTION that reverting each
     guard makes its new suite RED. A suite that passes against a reverted guard is not a red-proof.
scope: |
  Rig-only. Writes only NEW test files plus one markdown traceability edit. Explicitly does NOT edit
  fleet/checks/large-file-guard.sh (owned by GITHUB-LIMITS-HARDENING) or fleet/checks/rig-ci-scope.sh
  (owned by HANDOFF-GATE-NONBYPASSABLE) — if a proof cannot be written without changing the check,
  STOP and hand the finding back to that ticket's owner rather than co-writing the file.
  The product-repo gates.json fix is out of scope by construction (different repo).
ds: |
  ## Dependencies & sequence
  depends_on: GITHUB-LIMITS-HARDENING, HANDOFF-GATE-NONBYPASSABLE — DISJOINT owns (this ticket owns
  only new test files + the standard doc), so both are justified above as real correctness prereqs:
  each owns the check under test and is changing its behaviour now. Writing the proof first would
  freeze the wrong contract.
  WAVE 2 — runs in PARALLEL with META-GATE-CALLSITE-ENUM / META-GATE-REDPROOF-REACHABLE /
  WCI-CONTENTION-TEETH (fully disjoint files).
  DOWNSTREAM: WCI-CONTENTION-TEETH depends_on this ticket (it absorbed leg iii on 2026-07-24)
  — the fail-closed wiring is not
  landable while the meta-gate is RED on debt it did not cause.
  CONCURRENCY-SAFETY: sole owner of all three paths (verified 2026-07-24 against every `owns:` line
  on the board). Branch feat/meta-gate-findings-zero is unused.
