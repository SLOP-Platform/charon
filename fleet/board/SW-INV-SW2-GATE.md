repo: charon
tier: strong
difficulty: 4
work_class: tests
priority: 1
branch: feat/sw-inv-sw2-gate
depends_on: SW-IDENTITY-FOLD, SW-STATIC-LEGS-RETIRE
real-dep: SW-IDENTITY-FOLD — TRUE build/correctness prereq despite disjoint owns
  [[disjoint-owns-not-no-dependency]]. Assertion 2 of this gate asserts the identity-folding CONTRACT
  that SW-IDENTITY-FOLD defines (which variant spellings fold, which deliberately do not). Written
  first, it pins the pre-fix table and goes RED-then-rewritten the moment the anchor lands — the test
  would be authored against behaviour that is about to change, i.e. throwaway work that also hides
  the regression it exists to catch.
real-dep: SW-STATIC-LEGS-RETIRE — TRUE build/correctness prereq despite disjoint owns. Assertion 3
  ("no pool member exists that catalog discovery did not produce") IS that ticket's post-condition.
  Before it lands, 175 hand-pinned legs are present and legitimate, so the assertion is FALSE by
  construction and could only be written as a vacuous or inverted check.
dep-kind: build
owns: tests/test_switchboard_inv_sw2.py
serial_justified: |
  ONE invariant and its executable proof. INV-SW2 is a single release-blocking property of the whole
  selection path; a gate that asserts half of it asserts nothing.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  The run IS a graded sample: record it into fleet/model-scorecard.tsv with the work_class above.
  One checkout, one agent — its OWN worktree, never a shared checkout.
  Reviewer != builder: this is the gate that guards a money/routing path.
source: |
  Operator decision 6, 2026-07-26 (manager session kit-fisto), after asking whether the Switchboard
  would be "fully tested and functional" once the convergence wave lands. Answer was no: every wave
  ticket proves its own effect ONCE, and nothing continuously asserts the system invariant.
note: |
  ## WHAT IS MISSING
  ADR-0011 (Accepted) states: "A NEED that dead-ends with capable providers still available is a
  release-blocking defect (INV-SW2), not a transient." Nothing in the tree asserts that. The
  convergence wave fixes the KNOWN instances (fp4 identity split, static legs); it does not stop the
  NEXT one. Roadmap R44 `dogfood-gate` and R45 `inert-startup-check` are both still unbuilt, so there
  is no e2e merge-gate asserting an observable routing effect at all.

  This ticket is R44 for the Switchboard specifically. Read the R44 ticket before starting and EXTEND
  it if it already provides a dogfood harness — do not stand up a second one (anti-accretion).

  ## THE LIVE INSTANCE THIS WOULD HAVE CAUGHT
  2026-07-26: a request for `minimax-m2.5` returned `all providers exhausted` while Together — funded,
  unparked, advertising `MiniMaxAI/MiniMax-M2.5-FP4` — sat reachable and idle, stranded behind a
  missing `fp4` alternation in one regex. Two dead legs were offered; a live one was invisible. No
  test, gate, or alarm fired. The operator found it by reading container logs.

  ## THE GATE MUST ASSERT (all three)
  1. **No false exhaustion.** For a model whose pool contains >= 1 provider that is funded, unparked,
     not cooled and not rate-limited, a NEED for that model MUST NOT terminate in
     `all_providers_exhausted`. Drive the failure legs to 402/429 deliberately and prove the live leg
     is still selected.
  2. **Identity folding holds end-to-end.** Every variant spelling the live catalog advertises for one
     model resolves to ONE routable pool id — asserted through the ROUTING path, not by calling the
     normalizer directly. A unit test on `_normalize_model_id` is SW-IDENTITY-FOLD's job; this is the
     integration claim.
  3. **Discovery is the sole source of membership.** No pool member exists that catalog discovery did
     not produce (the post-condition of SW-STATIC-LEGS-RETIRE).

  ## ANTI-THEATER (the gate exists to prevent theater; it must not become it)
  - Assert OBSERVABLE effects. A mocked pool proving a mocked router is exactly the failure this
    ticket exists to prevent. Use the real selection path with injected upstream responses.
  - NON-VACUOUS: zero providers, zero models, or an empty catalog is RED, never a silent pass.
  - The gate must be WIRED — registered where the merge gate actually runs, not a file that exists and
    is never invoked. An unwired gate is an inert gate [[gates-must-actually-run]].
  - FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on every verification path.
accept: |
  DONE-CONTRACT (observable, by EXECUTION):
  - The three assertions above implemented in `tests/test_switchboard_inv_sw2.py` and GREEN.
  - RED-PROOF BY EXECUTION, one per assertion: re-introduce each defect (drop `fp4` from the suffix
    table; re-add one hand-pinned leg; mark the only live provider exhausted) and show the gate goes
    RED naming the specific violation. **Report all exit codes** — green run AND each deliberately
    broken run. Three green assertions you never made fail are three assertions of nothing.
  - Prove the gate is INVOKED by the merge gate: paste the gate output showing this test running, not
    just a passing pytest.
  - `PYTHONPATH=src python3 -m charon.cli gate` GREEN and `PYTHONPATH=src python3 -m pytest -q` GREEN.
  - State explicitly what you proved by RUNNING vs by READING, and which git ref you measured on.

## Dependencies & sequence

- **Depends on: SW-IDENTITY-FOLD (build), SW-STATIC-LEGS-RETIRE (build).** Assertion 2 asserts the
  identity contract the anchor defines; assertion 3 asserts the post-condition STATIC-LEGS-RETIRE
  creates. Writing either before those land pins behavior that is about to change.
- **Runs LAST in the wave** — it is the wave's proof, not a member of it.
- **Concurrency safety:** owns one NEW test file; no live ticket owns it. If wiring the gate requires
  editing a registration file owned elsewhere, STOP and report rather than co-writing.
- **Do NOT duplicate:** read roadmap R44 `dogfood-gate` and R45 `inert-startup-check` first. If R44
  provides a harness, extend it. Two dogfood harnesses is the rig-as-product anti-pattern.
