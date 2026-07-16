repo: charon
tier: hygiene
difficulty: 3
work_class: ci-infra
branch: fix/workflow-policy-backfill
depends_on:
owns: .github/workflows/ci.yml, .github/workflows/heavy.yml, .github/workflows/release.yml, .github/workflows/windows-exe.yml
serial_justified: the accept requires ONE policy decision (bare-tag vs SHA-pin for first-party
  actions) reconciled and applied IDENTICALLY across all 4 workflow files before check_workflows.py
  is wired into gate_runner.py — splitting per-file risks two workers reconciling the policy
  differently; the ticket's own ds note also flags it must run before/alongside any other
  workflow-touching ticket to avoid clobbering the same 4 files.
accept: |
  GATES-MUST-ACTUALLY-RUN backfill (src/charon/gate_runner.py, feat/gate-registry-complete): 5 gates were
  registered in tools/gates.json but never invoked by `charon.cli gate`. 4 of 5 (check_no_rig_import.py,
  check_arch.py, check_security.py, check_test_patterns.py) passed clean on first real run and are now wired
  into gate_runner.py CHECKS. The 5th — tools/check_workflows.py (workflow-policy gate) — FAILS on first real
  run with 18 violations across all 4 workflow files, never caught before because the gate never executed:
    - actions/checkout, actions/setup-python (ci.yml:29-30,69-70; heavy.yml:25-26,58,86-87; release.yml:42-43,
      71,121) and actions/upload-artifact (windows-exe.yml:45) are pinned to full 40-char commit SHAs with a
      trailing `# vN` comment; check_workflows.py's policy requires first-party actions/* to be a BARE
      major-version tag (@vN), full-SHA pinning reserved for third-party actions (docker/*, attest-build-provenance).
    - release.yml:19 and windows-exe.yml:12 — packaging-triggering `on.push` has no `paths:` filter, so a
      docs-only change would fire a full package/release build.
  Do NOT mechanically bulk-edit: SHA-pinning first-party actions is a deliberate supply-chain hardening pattern
  used consistently across every workflow in this repo (see release.yml's SLSA-provenance commentary) — decide
  FIRST whether the checker's policy (bare-tag for first-party) or the workflows' current practice (SHA-pin
  everywhere) is actually correct, reconcile whichever is wrong, THEN wire tools/check_workflows.py into
  gate_runner.py's CHECKS list and confirm `charon.cli gate` stays green.
scope: |
  Reachability-audit follow-on (gate_runner.py CHECKS vs tools/gates.json registry). Scoped to the
  workflow-policy gate only — the other 4 backfilled gates are already wired and green on
  feat/gate-registry-complete. This ticket exists so wiring the 5th gate isn't silently dropped once the
  branch merges.
ds: No dependents found yet. Should run before/alongside any other CI-workflow-touching ticket (owns 4
  workflow files) to avoid clobbering; otherwise launch anytime.
