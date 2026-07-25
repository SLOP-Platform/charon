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
depends_on: KSF-VENDOR-GATES, GATE-REENTRANCY-GUARD
real-dep: GATE-REENTRANCY-GUARD is a HARD build prereq for F4 below — the recursion this ticket's
  diff-cover gate triggers (pytest -> test_gate_contract -> the gate -> pytest -> ...) is fixed as a
  CLASS by that ticket's branch (fix/gate-reentrancy-guard @ 2b6d2ad, product repo). Owns are
  disjoint on paper (that ticket owns src/charon/gate_runner.py + tools/gate_contract.py +
  tests/test_gate_contract.py; this one owns tools/gate_runner.py + the two new gate scripts), which
  is exactly why the dep must be declared explicitly: F4 cannot be fixed here without the guard
  landing first. Added 2026-07-24 from the review below.
review: fleet/state/reviews/DIFF-COVER-MUTMUT-REVIEW-agen-kolar.md — VERDICT: DO-NOT-LAND, 3 CRITICAL
  + 4 HIGH + 2 LOW. The fix list is reproduced in `fix_list:` below; it is REQUIRED reading before
  claiming, and its ORDER is the reviewer's, not negotiable.
fix_list: |
  ## DO-NOT-LAND fix list (reviewer's order — F4 FIRST)
  Branch feat/diff-cover-mutmut-adopt is BUILT but was reviewed DO-NOT-LAND. Whoever claims this
  ticket fixes these BEFORE any land attempt. Do not re-derive them; all were observed by execution.

  1. F4 — CRITICAL — UNBOUNDED RECURSION. **Nothing else matters until the gate stops invoking a
     pytest run that re-invokes the gate.** tests/test_gate_contract.py runs every tools/-rooted
     gate in gates.json as a subprocess; tools/diff_cover_gate.py runs the whole pytest suite under
     coverage, so `pytest -> test_gate_contract -> diff_cover_gate.py -> coverage run -m pytest ->
     ...` never terminates on any branch WITH a diff (master short-circuits on no-diff, which is why
     the builder's master-only trial missed it). Observed twice: depth 3 and still growing at ~300s.
     Blast radius is the WHOLE repo — ci.yml's `pytest -q -n auto` and `charon gate` both recurse,
     so every PR burns its full 20-minute slot on the shared 4-LOM runner and dies by timeout.
     >>> DEPENDS ON `fix/gate-reentrancy-guard` (ticket GATE-REENTRANCY-GUARD) LANDING FIRST — that
     branch is the class fix (a re-entrancy guard). Do NOT hand-roll a second guard here. The
     reviewer's own options were: guard env var, deselect the new gates from test_gate_contract's
     parametrization, or have diff-cover consume an XML produced by the existing CI test step
     instead of running its own pytest — the landed guard is the first of these, generalized.
  2. F1 — CRITICAL — FAKE-GREEN #1: an unresolvable base ref makes BOTH gates silently exit 0.
     Check the `git diff` return code; unresolvable base or git error => NON-ZERO exit. Add
     `fetch-depth: 0` to ci.yml and pass the PR base ref explicitly.
  3. F2/F3 — CRITICAL + HIGH — FAKE-GREEN #2: a no-op mutmut run passes, because the pass signal is
     an ABSENCE rather than a positive killed count. Use `if mutated is None or mutated == 0:` to
     fail; check `results_result.returncode`; assert a POSITIVE killed count via `mutmut results
     --all` instead of trusting the absence of surviving mutants.
  4. F5 — HIGH — pyproject.toml (a tracked SSOT) is rewritten IN PLACE; an abnormal exit leaves it
     corrupted. Scope with `mutmut run <glob>` instead of rewriting pyproject.toml, or operate on a
     scratch copy of the tree.
  5. F7 — HIGH — the mutmut gate cannot currently pass on this repo AT ALL: make mutmut's sandbox
     able to import the repo before this becomes a required check.
  6. F6 — HIGH — diff-cover measures only `src/`, so every new line in `tools/` and `tests/` is
     invisible to it. Either extend coverage scope to `tools/`, or drop `tools/`/`tests/` from the
     work-unit count so WORK-UNITS stops overstating what is checked.

  Also noted (LOW/NIT, not blocking): F8 the diff-cover gate does not terminate and `.coverage` is
  not gitignored; F9 `_STATUS_LINE` matches any `key: value` line; F10 `min_work_units: 0` satisfies
  the anti-vacuity ratchet with prose.
  RE-REVIEW REQUIRED after the fixes — the original verdict stands until a reviewer (!= builder)
  clears it by execution.
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
