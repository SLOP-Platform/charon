tier: standard
difficulty: 2  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: ci-infra
branch: feat/wire-mocklint-enforce
depends_on: TEST-HARDEN-CONTRACT, GATE-INTEGRITY-B
real-dep: TEST-HARDEN-CONTRACT (#92) landed Defect A (real anthropic wire-shape test) but scoped
  OUT Defect B (the enforcement). This ticket IS Defect B, split out per operator decision
  (merge A-only + hard follow-up). Rebase onto #92's squash-merge before starting.
real-dep: GATE-INTEGRITY-B — shared src/charon/gate_runner.py (GATE-INTEGRITY-B's step 1 adds
  pytest/check-decisions/render-review-log to CHECKS; land after it so this ticket's remaining
  DO-1/3/4 work — none of which still touches gate_runner.py per the 2026-07-13 WCI RECONCILE
  note below — never races GATE-INTEGRITY-B's CHECKS edit). Undeclared collision found + fixed per
  fleet/state/TOOL-AUDIT-COLLISION.md-adjacent board sweep (2026-07-13). (GATE-INTEGRITY decomposed
  2026-07-13 into -A/-B; this dep repoints to -B, which owns gate_runner.py.)
owns: src/charon/gate_runner.py, tools/check_test_patterns.py, tools/gates.json
accept: |
  `PYTHONPATH=src python3 -m charon.cli gate` invokes check_test_patterns.py AND a self-mirroring
  / fabricated-mock violation makes the gate EXIT NON-ZERO (hard error, reported like ruff/mypy).
  A test asserts: introduce a self-mirroring mock fixture -> `charon gate` returns non-zero
  (fail-on-revert: removing the gate wiring or downgrading rule (e) to warning makes that test GREEN
  when it should be RED). gates.json `test-patterns` entry matches reality (ci_step actually wired).

scope: |
  Defect B from PR #87/#92: tools/check_test_patterns.py (the self-mirroring/fabricated-mock linter)
  EXISTS with red-proof tests and a gates.json registration (ci_step:true) — but it is NEVER invoked
  by `charon gate` (not in gate_runner.CHECKS) or CI, so a self-mirroring mock committed today passes
  unnoticed. This is the exact false-green that got #87 rejected.

  DO (recommended approach — avoid the --strict trap):
    1. Make rule (e) [self-mirroring / fabricated-mock] a HARD ERROR in check_test_patterns.py
       directly — appended to `errors`, not `warnings` — so it fails WITHOUT requiring global
       `--strict`. (The tree has ~1019 pre-existing warnings under --strict; do NOT gate on those.)
       Keep the other rules as warnings unless trivially clean.
    2. Add check_test_patterns.py to gate_runner.CHECKS so `charon gate` runs it.
    3. Clean up the small number of EXISTING rule-(e) violators the new hard error surfaces
       (should be few — the reviewer noted ~4 files). If a legit exception exists, add an explicit,
       narrow allow-pragma the linter honors (documented), not a blanket downgrade.
    4. Tighten check_gate_registry.py so a gates.json entry with ci_step:true that is NOT wired into
       gate_runner.CHECKS is itself a gate failure (prevents future "registry claims coverage it
       doesn't deliver" — the bonus gap the reviewer found).

note: |
  Split from TEST-HARDEN-CONTRACT per operator decision 2026-07-10 (merge A-only + hard follow-up).
  Money-path-adjacent (test-integrity gate) — INDEPENDENT review before merge, fail-on-revert test
  required. Origin review packet: PR #92 REVIEW-PACKET (worktree charon-fleet-TEST-HARDEN-CONTRACT).

  WCI RECONCILE (2026-07-13, code-confirmed at charon origin/master af4a17c): DO step 2 landed as a
  SIDE EFFECT of PR #119 (gate-registry-complete/work-framework-wiring) — check_test_patterns.py IS
  now in gate_runner.CHECKS and DOES run in `charon gate` (confirmed: gate_runner.py:16). This ticket
  is NOT done: DO steps 1/3/4 are still open — tools/check_test_patterns.py:17-19 still documents rule
  (e) self-mirroring-mock as a WARNING only ("gates under --strict"; gate_runner.CHECKS invokes it
  WITHOUT --strict), so a fresh self-mirroring mock today still passes the gate. Remaining scope:
  promote rule (e) to a hard ERROR, clean up the ~4 pre-existing violators it will surface, and
  tighten check_gate_registry.py per DO-4. Do not mark done on step-2-only wiring.
