tier: standard
work_class: ci-infra
branch: feat/wire-mocklint-enforce
depends_on: TEST-HARDEN-CONTRACT
real-dep: TEST-HARDEN-CONTRACT (#92) landed Defect A (real anthropic wire-shape test) but scoped
  OUT Defect B (the enforcement). This ticket IS Defect B, split out per operator decision
  (merge A-only + hard follow-up). Rebase onto #92's squash-merge before starting.
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
