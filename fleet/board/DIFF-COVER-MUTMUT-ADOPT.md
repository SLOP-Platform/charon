repo: charon-private
tier: strong
difficulty: 3
priority: 0
work_class: ci-infra
branch: feat/diff-cover-mutmut-adopt
owns: /home/stack/code/charon/.github/workflows/ci.yml,
  /home/stack/code/charon/tools/diff_cover_gate.sh,
  /home/stack/code/charon/tools/mutmut_diff_gate.sh,
  /home/stack/code/charon/pyproject.toml,
  /home/stack/code/charon/tools/gate_runner.py,
  /home/stack/code/charon/tests/test_diff_cover_mutmut_gate.py
real-dep: KSF-VENDOR-GATES owns /home/stack/code/charon/tools/gate_runner.py already (registering
  its 5 new KSF gates); this ticket adds two MORE entries to the same CHECKS registration —
  sequenced after it to avoid a parallel-edit collision on the same file, and per the META-TOOL
  doc's adoption-plan step order (pin diff-cover/mutmut as required-checks after the KSF gates
  land).
depends_on: KSF-VENDOR-GATES
source: fleet/state/META-TOOL-WIRED-AND-WORKING.md Layer 2 "EXERCISED-WITH-OBSERVABLE-EFFECT —
  for NEW PRODUCT CODE" + "Adoption plan" steps 3-4. Read-only research, EVAL-REGISTRY rows
  proposed (diff-cover, mutmut) are README/docs confidence — NOT run in that research session;
  run a fixture trial as part of this ticket's own build, per AP-12 (executed-before-adopt).
work_class_note: ci-infra — pins two new required-checks into the PR gate; this is CI/gate
  infrastructure, not a product feature.
note: |
  The genuine open gap the source doc identifies: KSF's redproof + gate_contract's min-work-units
  prove "exercised-with-effect" for GATES, but NOTHING proves it for new PRODUCT code lines —
  "new module lands with no exercising test" is undetected today. diff-cover (patch-coverage:
  every new/changed line must be executed by the test run, or the check fails) is the cheap,
  fast half; mutmut scoped to the diff (`--paths-to-mutate=<changed files>`, full-tree mutation
  is too slow to gate a solo repo) is the assertion-strength half (a surviving mutant == a test
  that can't fail). Both are un-evaluated candidates per the source doc (README-confidence only)
  — this ticket's OWN first step is the executed trial the source doc calls for, not a blind
  adopt. cosmic-ray REJECTED vs mutmut (heavier config/session model, distributed-runner
  oriented, overkill for one box) — re-confirmed, do not re-litigate.
  [[use-free-tiers-to-their-limits]]
accept: |
  - EXECUTED TRIAL FIRST (per AP-12, not a blind adopt): run diff-cover against a real Charon PR
    diff with intentionally-uncovered new lines -> confirm it fails the check; add the covering
    test -> confirm it passes. Run `mutmut --paths-to-mutate=<the same changed files>` against a
    fixture with a deliberately-weak assertion (a test that passes regardless of the mutated
    line's behavior) -> confirm a surviving mutant is reported; strengthen the assertion ->
    confirm the mutant is killed. Capture both transcripts in this ticket's PR description.
  - tools/diff_cover_gate.sh: wraps `diff-cover` off `coverage.py` XML + the git diff against the
    PR's base — fails the check if any new/changed line is unexercised.
  - tools/mutmut_diff_gate.sh: computes the changed-files set from the git diff, runs
    `mutmut --paths-to-mutate=<that set>` scoped to the diff only (never full-tree in the PR gate
    — full-tree runs nightly instead, out of scope here), fails if any mutant survives.
  - tools/gate_runner.py: register both as CHECKS entries (extends KSF-VENDOR-GATES' edit to the
    same file — land after it, not in parallel).
  - .github/workflows/ci.yml: add both as required-check steps.
  - fail-on-revert test (tests/test_diff_cover_mutmut_gate.py): (a) a fixture diff with an
    unexercised new line -> diff_cover_gate.sh RED; add the test -> GREEN; (b) a fixture diff with
    a surviving mutant -> mutmut_diff_gate.sh RED; strengthen the assertion -> GREEN. Revert
    either fix -> RED again.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — edits the load-bearing
    tools/gate_runner.py CHECKS registration + adds new required-checks to the merge-blocking CI
    spine; manager gates, PR does NOT merge on the builder's self-report.
scope: |
  Diff-scoped coverage + mutation gates only. Full-tree nightly mutmut is explicitly out of
  scope (a separate cadence ticket, not required to make the diff-gate real). Does not touch
  KSF-VENDOR-GATES' 5 vendored gates or fleet/checks/reconcile-gate-wired.sh.
ds: |
  ## Dependencies & sequence
  depends_on KSF-VENDOR-GATES (shares tools/gate_runner.py — real build/correctness prereq,
  marked above). Last step in the META-TOOL adoption-plan sequence for this wave.
