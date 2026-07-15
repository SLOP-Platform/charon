repo: charon
tier: strong
difficulty: 2
work_class: ci-infra
branch: feat/gate-integrity-coverage
depends_on: GATE-INTEGRITY-A
real-dep: GATE-INTEGRITY-A — full `charon gate` green requires A's deterministic inert scan
  first (this ticket's accept step 1 asserts `charon gate` GREEN, which transitively runs
  check_inert_code.py; if A hasn't landed its determinism fix, that step is non-deterministic
  and this ticket's accept can't be judged reliably). Disjoint owns (no file collision) — this
  is an ordering/correctness prereq, not a merge-conflict-avoidance dep.
owns: src/charon/gate_runner.py, tools/check_gate_registry.py
note: |
  GATE-INTEGRITY sub-B (gate-coverage side). Split from the monolithic GATE-INTEGRITY (parallelizability
  gate refused it as splittable). Spec: fleet/state/S1-GATE-INTEGRITY-SPEC.md §1. Disjoint file-ownership
  from sub-A (inert side). depends_on GATE-INTEGRITY-A so the full `charon gate` is green (needs A's
  deterministic inert scan) before this ticket's accept is judged.
accept: |
  1. §1: add the 3 declared-but-unwired gates to `CHECKS` in gate_runner.py — `pytest`,
     `check-decisions` (tools/check_decisions.py), `render-review-log` (tools/render_review_log.py
     --check — MUST use --check; bare form mutates docs/REVIEW-LOG.md). `validate-board`/`charon-gate`
     stay excluded (fleet-external / self-referential).
  2. check_gate_registry.py: add ci-infra, no-rig-import to ALL_DOMAINS.

  ## Accept
  - `PYTHONPATH=src python3 -m charon.cli gate` → GREEN, and now actually RUNS the 3 newly-wired checks
    (verify they execute, not just that gate exits 0 — grep the run output for pytest/check-decisions/
    render-review-log lines).
  - `PYTHONPATH=src python3 -m pytest` → full suite green.

  ## Dependencies & sequence
  depends_on GATE-INTEGRITY-A (deterministic inert scan must land first so the full gate is green).
  Disjoint files from A → no two-writer hazard; A→B ordering only.
