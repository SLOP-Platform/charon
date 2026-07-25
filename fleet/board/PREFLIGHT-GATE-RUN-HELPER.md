repo: charon-private
tier: strong
difficulty: 3
priority: 1
work_class: rig-meta
branch: feat/preflight-gate-run-helper
depends_on: WCI-CONTENTION-TEETH
real-dep: WCI-CONTENTION-TEETH — SHARED owner of fleet/preflight.sh, and a real build prereq. Its
  PHASE 2 EXTRACTS preflight.sh's 8 inline `*_gate()` functions into one file each under
  fleet/checks/. Applying the fail-CLOSED contract BEFORE that extraction means nine hand-edits to
  nine inline functions that are about to move — the edits are then re-done by the extraction, and
  two branches co-write a 906-line file. After the extraction each check is a FILE, so "missing
  machinery is RED" becomes a structural property of the invocation seam instead of nine copies of
  the same guard. Sequencing here is the cheap order, not a formality.
restored: |
  RESTORED 2026-07-24 (reconstructed, not recovered). This ticket was created earlier the same day,
  never committed, then DELETED by a bundling pass that folded it into WCI-CONTENTION-TEETH as
  "PHASE 3". It is not in git, so this file is rebuilt from the absorbed content (WCI-CONTENTION-
  TEETH's phase-3 note + acceptance items L/M/N/O, which were written FROM this ticket) plus its
  cited source. Bundling means GROUP AT ONE PRIORITY IN ONE WAVE — the group is the ROADMAP wave
  `gate-audit-generalization` — it does NOT mean fuse tickets into one serial branch.
  [[decomposed-by-design-not-reactive]] [[optimize-execution-wallclock-tokens]]
source: fleet/state/reviews/CLASS-SCAN-UNAUDITED-GATES-agen-kolar.md §2a (execution-verified
  fail-open table), §3 rank 2-3, §4 "Note on the fail-open pattern (#1-8)".
owns: fleet/preflight.sh, fleet/tests/preflight-gate-run.test.sh
note: |
  THE DEFECT: fleet/preflight.sh's gate legs each carry a copied `[ -f "$CHECK" ] || return 0`
  guard. A check whose machinery is MISSING, non-executable, or that dies on rc-126/rc-127/a signal
  therefore SKIPS SILENTLY and the session reads GREEN. The gate is not enforcing anything and says
  so nowhere — the class-scan found the idiom copied across the leg set. A second copy of the same
  class: the `cmd_add … >/dev/null 2>&1 || true` mask means a gate that CANNOT RECORD its red still
  exits clean, so the red never reaches reds.tsv. [[gates-must-actually-run]]
  THE FIX IS ONE INVARIANT, APPLIED EVERYWHERE: missing / unrunnable machinery is RED, and a gate
  that cannot write its red row fails loudly. No `return 0`, no "skipped", no advisory downgrade.
  MEASURE, DO NOT ASSUME: count the real fail-open guards on the branch base before starting (the
  class scan counted nine, six of them the literal `[ -f … ] || return 0` idiom) and state the
  MEASURED number in the PR. Acceptance is "ZERO remaining", never "six changed".
accept: |
  L. MISSING MACHINERY IS RED, everywhere: board_gate, executor_gate, coverage_gate, handoff_gate,
     graphify_freshness_gate, hold_reason_gate, done_merge_gate, detect_needs_push,
     startup_budget_gate. A missing / non-executable / rc-126 / rc-127 / signal-killed check MUST
     open the red row and make `preflight scan` exit non-zero.
  M. NO SILENT REGISTRY FAILURE: the `cmd_add … || true` mask is gone; if the red row cannot be
     appended, the gate fails loudly (non-zero). A gate that cannot record its red has not run.
  N. VACUITY GUARD: `preflight scan` REDs if the gate chain executed ZERO gates. Assert a floor
     equal to the MEASURED chain length — zero gates run must never read green.
  O. FAIL-ON-REVERT (fleet/tests/preflight-gate-run.test.sh — hermetic `mktemp -d` fixture fleet;
     NEVER delete anything in the real tree, the source scan proved this defect that way):
     1. per converted gate: machinery present + green => rc 0, no red row; machinery REMOVED from
        the fixture => rc non-zero AND the gate's red row is in the fixture reds.tsv. Restoring
        `[ -f … ] || return 0` makes every one of these go RED.
     2. registry-write failure injected (read-only fixture reds.tsv) => non-zero, never green.
     3. empty gate chain => rc non-zero (vacuity guard).
     4. machinery exists and exits 127 => RED, not pass.
  P. RUNNER-REACHABLE: the suite is named `*.test.sh` and is EXECUTED by fleet/gate.sh's
     `*.test.sh` glob — PASTE THE RUNNER LINE. A `test_*.sh` name is matched by neither runner; a
     proof no runner executes is not evidence.
  Q. `bash fleet/validate_board.sh` rc 0 modulo pre-existing reds. `bash fleet/preflight.sh scan`
     on the REAL tree reports its rc HONESTLY — a newly-surfaced pre-existing red is a FINDING to
     report, not a reason to weaken a gate [[never-ignore-preexisting-issues]]. Run the NAMED
     suites only; do NOT run the full fleet/tests sweep (the benchmark grader suites block for
     hours).
  R. ADVERSARIAL REVIEW REQUIRED (reviewer != builder) — this rewrites the rig's primary session
     gate. Confirm BY EXECUTION, not by diff, that at least three converted gates go RED with their
     machinery deleted. The whole class is "it looked wired".
scope: |
  Rig-only [[product-vs-build-rig-boundary]]. The fail-open invariant across preflight.sh's gate
  legs, and its red-proof. Does NOT arm the contention detector (WCI-CONTENTION-TEETH phase 1), does
  NOT perform the preflight decomposition (that ticket's phase 2 — this one applies the contract to
  the extracted checks), and does NOT wire the meta-gate into the chain (META-GATE-PREFLIGHT-WIRE-
  CLOSED owns that leg and its ledger row).
ds: |
  ## Dependencies & sequence
  depends_on: WCI-CONTENTION-TEETH only — shared fleet/preflight.sh AND a real build prereq (see
  real-dep). THE SHARED FILE IS THE WHOLE CONSTRAINT, AND IT IS TEMPORARY: the operator-approved
  DECOMPOSITION of preflight.sh (WCI-CONTENTION-TEETH phase 2, 8 inline gates -> one file each under
  fleet/checks/) is what DISSOLVES it. Once each check is its own file, this ticket and
  META-GATE-PREFLIGHT-WIRE-CLOSED touch different files and can run in PARALLEL. The decomposition
  is the real fix for the contention; fusing the tickets was not.
  DOWNSTREAM: META-GATE-PREFLIGHT-WIRE-CLOSED depends on this ticket — it wires a new leg through
  the fail-closed machinery this one establishes; wiring a leg into a chain that still fails open
  would ship an enforcing gate that skips silently.
  CONCURRENCY-SAFETY: never co-write fleet/preflight.sh from a parallel branch — rebase onto the
  dep's merge. fleet/tests/preflight-gate-run.test.sh is a NEW file with no other live owner
  (verified 2026-07-24 against every `owns:` line); branch feat/preflight-gate-run-helper is unused.
  BENCH-OOB-GRADING owns `preflight.sh` UNPREFIXED — that is fleet/benchmark/preflight.sh, a
  DIFFERENT file (verified by `find . -name preflight.sh`). No edge needed or declared.
