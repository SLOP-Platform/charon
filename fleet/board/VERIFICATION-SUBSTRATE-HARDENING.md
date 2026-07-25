repo: charon-private
tier: frontier
difficulty: 5
priority: 0
work_class: rig-meta
branch: feat/verification-substrate-hardening
owns: fleet/checks/verify-substrate.sh, fleet/tests/verify-substrate.test.sh,
  fleet/state/VERIFICATION-SUBSTRATE-DESIGN.md
depends_on:
real-dep: none — startable immediately. It deliberately does NOT own any existing gate file;
  the DESIGN pass decides which existing gates to extend, and those edits are sequenced as
  follow-on tickets so this one does not collide with the ~6 live owners of preflight.sh /
  gate-creation-standard.sh.
serial_justified: |
  The investigation and the mechanism are one unit — a mechanism designed without the full
  instance corpus reproduces the class it is meant to close (this happened twice on 2026-07-24:
  a "no-callers" detector was specified while a working one sat unlanded, and a reentrancy guard
  was nearly shipped as a fake-green switch).
source: |
  Operator directive, 2026-07-25, after session agen-kolar. Verbatim intent: "can we mechanize the
  things being measured on the wrong thing so it doesn't go on habit? We need a deep investigation
  into how to stop fake greens. We also keep using search patterns that don't work (grep) and
  ref-citing errors, almost landing broken code. We need to be better."
decisions: |
  Q1 ANSWERED (operator, 2026-07-25): **"logically strict without becoming a problem."**
  Interpretation to build to: strict where a wrong answer is SILENT and CONSEQUENTIAL (a gate that
  cannot fail, a search whose zero-hits reads as absence, an exit code masked away, a claim about
  code with no ref) — because those are precisely the cases a human cannot catch by reading. NOT
  strict where it merely adds ceremony to work that already fails loudly. Design rule: every
  enforcement point must justify itself against a REAL instance from the corpus; if it cannot cite
  one, it is ceremony and must be cut. A gate people route around is worse than no gate — this rig
  has already produced five `WORK_LEASE_BYPASS` uses in one day for exactly that reason.
  Q2 ANSWERED (operator, 2026-07-25): **investigate BOTH rig and product.**
  The product carries the same class independently: `reachability-gate` in
  `/home/stack/code/charon/tools/gates.json` names an enforcer that exists NOWHERE, and
  `optional:true` converts that into a SKIP reporting OK rc=0. Product gate stack is
  `tools/gates.json` + `src/charon/gate_runner.py` + `tests/test_gate_contract.py`. Note the
  product is PUBLIC — the mechanism must not leak rig paths into it, and a rig detector reaching
  into the product repo is itself the boundary-leak class (already ruled on 2026-07-24).
note: |
  ## THE CLASS
  Every instance below is the same shape: **A CHECK RAN AND DID NOT CHECK WHAT ITS READER
  BELIEVED IT CHECKED.** Not laziness — the verification substrate itself permits a confident
  wrong answer. Discipline has already failed here; four sub-sessions had to refuse manager
  instructions to avoid propagating errors, and were right every time. The fix must be
  MECHANIZED, not another rule.

  ## SUB-CLASS A — MEASURED THE WRONG THING (verification substrate)
  A1. `work-lease.sh guard-branch` declared NON-EXISTENT by two independent sessions — both
      grepped `master`; it lived on an unlanded branch. Nearly written as a "correction" into
      three tickets. A sub-session refused and was right.
  A2. `gate.sh` fork loop reported UNBOUNDED at `:44-50`; on `origin/master` it is BOUNDED at
      `:56-63` (`JOBS` cap + `wait -n`). Measured on a local checkout **13 commits behind**.
      Neither report stated its ref. This also produced a false "two subs contradict each other,
      both cannot be right" — one `git fetch` dissolved it.
  A3. Grep pattern `rc -ge 128` returned 0 hits; the source reads `[ "$rc" -ge 128 ]`. **The
      PATTERN was wrong, not the code** — and a 0-hit grep was read as evidence of absence.
  A4. Gate red counts reported as 76/2, 69/9, 68/10 across the same day — different refs, under
      different concurrency, never reconciled. A land decision was nearly made on the wrong one.
  A5. `git cherry` / `git log origin/master..<branch>` give FALSE NEGATIVES here: work lands by
      RE-DERIVATION, not cherry-pick, so fully-landed branches still report unique commits.
      Six branches looked live and were dead.
  A6. A tier direction relayed between sub-sessions was inverted (`FT-CATALOG-SEED` reported
      frontier→strong while declared `economy`); applying it blind would have written a wrong tier.
  A7. `| tail` masked an exit code — `handoff-check.sh` printed FAIL while the pipeline reported
      rc=0. Committed by the manager INSIDE the check meant to catch that class.

  ## SUB-CLASS B — FAKE GREENS (a gate that cannot fail, or passes over no work)
  B1. tier-drift gate could never return RED — its RED-set file did not exist, so every mismatch
      was an advisory WARN at rc 0. A security ticket mis-tiered to `economy` stayed GREEN.
  B2. diff-cover/mutmut: a no-op `mutmut` printed "all mutants killed"; and both gates exited 0
      with `WORK-UNITS: 0` whenever `git diff <base>` failed — which CI's shallow checkout guarantees.
  B3. product `reachability-gate`: its enforcer file **does not exist anywhere**, and
      `optional:true` converts that into a SKIP that reports OK rc=0 — an affirmative green for
      work never done.
  B4. gateway preflight (PR #271) — `derive_gateway_token()` stored to `local derived` while the
      preflight read `$_derived_tok`; under `set -u` it died `unbound variable` and **the exit-5
      stand-down never fired**. 77/10 RED. **This was the fix for B-class defects, and was itself one.**
  B5. `parallelizability-gate.sh` needs ~21.7s against a hardcoded 15s budget, so it reports
      failure-to-run and the board still prints GREEN — a budget breach silently disabling a check.
  B6. 33 test files never executed by ANY runner: named `test_*.sh` while `gate.sh` globs
      `*.test.sh`. Seven guard money-path, security or data-loss surfaces.
  B7. Test FIXTURES encoded the same defect they tested: `{"pools":{}}` used to mean "nothing
      capped", the exact empty-vs-error conflation under repair.
  B8. `is_infra_fault()` booked infra crashes as MODEL failures — 42 of 46 lifetime BLOCK
      enqueues were provably infra, corrupting the ledger routing ranks on.

  ## SUB-CLASS C — ALMOST LANDED BROKEN CODE
  C1. PR #271 nearly merged with B4 live. It was caught ONLY because the land was gated on a
      green suite — not by review, not by the author, not by CI.
  C2. Rig merges are NOT test-gated at all: `land.sh` runs `validate_board.sh` (a board STRUCTURAL
      check) and never `gate.sh`. Eight red suites sat on master unnoticed.

  ## WHAT THIS TICKET IS NOT
  - NOT another rule in MANAGER-OPERATING-RULES.md. Discipline already failed.
  - NOT a new per-instance script. Anti-accretion is hard here: extend existing gates
    (`gate-creation-standard.sh` is the natural host; `META-GATE-REDPROOF-REACHABLE` and
    `WCI-CONTENTION-TEETH` already establish the emit/registry pattern to reuse).
  - NOT a fix for the listed instances one at a time. Most already have their own tickets.
    **This ticket owns the SUBSTRATE that let all of them be believed.**
accept: |
  PHASE 1 — INVESTIGATION (deliverable is a design doc, reviewed before any code)
  - A complete instance corpus, each with file:line and the ref it was measured on. Start from
    A1-A7/B1-B8/C1-C2 above; find the ones not yet known. State how you searched, and prove the
    search was non-vacuous — a 0-hit grep is NOT evidence of absence (see A3).
  - Root-cause each sub-class. Say explicitly which are the SAME root cause and which are not.
  - Adopt-first: survey what already exists for this (assertion libraries, shellcheck/bats/shunit2
    idioms, CI provenance tooling, `set -u`/`set -o pipefail` enforcement, git plumbing that pins a
    ref). Record "no tool fits because X" if that is the honest answer — but the standing rule is
    that hand-rolling carries heavy negative weight and must be argued adversarially.
  - Design → `fleet/state/VERIFICATION-SUBSTRATE-DESIGN.md`, INDEPENDENTLY reviewed before code.
  PHASE 2 — MECHANISM (must satisfy all)
  - **Ref-pinning:** a claim about code cites the ref it was measured on, and that is CHECKED, not
    trusted. `handoff-check.sh` already enforces `<script>.sh:<line>` citations — extend, do not fork.
  - **Non-vacuous search:** a search that matched nothing is distinguishable from a search that
    proved absence. Zero hits must not read as evidence.
  - **No exit-code masking:** `| tail`/`| head`/`|| true`/missing `set -o pipefail` on any
    verification path is RED. (`gate-creation-standard.sh` S5 covers pipes; extend to budgets and
    to unbound-variable death under `set -u`, which is B4.)
  - **Every gate proves it CAN fail** — red-proof executed and reachable by a real runner, and the
    proof itself must be non-vacuous.
  - **Optional/skip cannot yield an affirmative green** (B3): a skipped gate reports SKIPPED, never OK.
  - **Fail-on-revert** on the mechanism itself, and it must catch at least B1, B3, B4, B5 and B6
    replayed as fixtures. A mechanism that cannot catch the corpus it was built from is not done.
  - Non-vacuous: zero checks examined = RED.
  PHASE 3 — ADOPTION
  - Wired into a real runner (`gate.sh` `*.test.sh` glob and/or `rig-ci-scope.sh:CI_SUITES`) with
    proof it executed. A red-proof no runner runs is the class itself (B6).
  - Follow-on tickets for each contended existing gate it must extend — do NOT collide with the
    ~6 live owners of `preflight.sh`.

## Dependencies & Sequence

- Depends on: nothing. Startable immediately; Phase 1 is investigation and owns no contended file.
- Related, do NOT duplicate: `META-GATE-REDPROOF-REACHABLE` (runner-reachability), `WCI-CONTENTION-TEETH`
  (auto-ticket emit seam to reuse), `BOARD-WRITE-LOCK` (concurrency, different class),
  `LAND-GATE-RIG-SUITE` (C2 — rig merges not test-gated), `SCORECARD-BLOCK-HISTORY-RECLASSIFY` (B8 history).
- Blocks: nothing structurally, but every future gate inherits this substrate — the longer it waits,
  the more gates are built on ground already known to be unsound.
- Sequence: Phase 1 design + independent review → operator answers Q1/Q2 → Phase 2 → Phase 3.
- Evidence corpus: `/home/stack/charon-private/fleet/handoff-notes/` (38 artifacts from session
  agen-kolar — the audits, adversarial reviews and class scans that produced the instances above).
