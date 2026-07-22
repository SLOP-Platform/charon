repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/bandit-adopt
depends_on: SEMGREP-CI-REQUIRED-CHECK
substrate: bandit — adopt — maintained best-in-class Python SAST; ships only the thin wrapper plus required-check workflow plus fail-on-revert canary (the novel slice); net-new danger-pattern coverage the rig lacks; the KSF product-core don't-wrap verdict is a different (stdlib) scope. [[adopt-substrate-build-only-novel-slice]]
real-dep: |
  SEMGREP-CI-REQUIRED-CHECK — genuine build/sequencing prereq, not merge-order preference. That
  ticket ESTABLISHES the reusable CI-required-check scaffold this ticket consumes: the charon-ci-runner
  workflow pattern, branch-protection required-check wiring on BOTH repos, and the known-bad-fixture
  canary convention. bandit reuses that exact scaffold; owns are DISJOINT (different check/workflow/
  fixture files) so this dep is JUSTIFIED here, not implied by file overlap.
owns: fleet/checks/bandit.sh, .github/workflows/bandit.yml, fleet/tests/bandit-canary.test.sh, fleet/tests/fixtures/bandit-known-bad.py
serial_justified: |
  The owned surfaces are ONE adopt-a-SAST unit: the workflow invokes the wrapper, the
  canary test asserts the wrapper flags the planted insecure pattern in the fixture. Splitting ships a
  half-wired SAST (workflow with no wrapper, or scan with no canary) — the zero-work-green defect this
  ticket guards against. Ship together.
accept: |
  UMBRELLA: KS31/KS32 tool-adoption sweep + KS13 (Python SAST as a CI check). ADOPT the maintained
  bandit Python SAST as a CI check on the charon-ci runner — do NOT hand-roll a Python security linter.

  DO (COMPOSE the maintained tool):
    (a) fleet/checks/bandit.sh — thin wrapper running `bandit -r`/diff-scoped over the product Python
        tree (src/charon/...), exit non-zero on findings at/above the configured severity.
    (b) .github/workflows/bandit.yml — CI check on the charon-ci runner, reusing the SEMGREP-established
        required-check + branch-protection scaffold. bandit is a PRODUCT (Python) SAST — wire it on the
        product `charon` repo (and rig where Python exists); mirror SEMGREP's both-repos posture.
    (c) KNOWN-BAD-FIXTURE CANARY (NON-NEGOTIABLE): fleet/tests/fixtures/bandit-known-bad.py contains a
        planted insecure pattern bandit MUST flag; fleet/tests/bandit-canary.test.sh asserts >=1 finding —
        so a mis-scoped/no-op scan can never print green (C1 zero-work-green defense).

  FAIL-ON-REVERT (fleet/tests/bandit-canary.test.sh — REQUIRED): wrapper on the known-bad fixture ->
  >=1 finding; neuter the config/scope so it scans nothing -> finding count 0 -> canary test FAILS.
  Clean fixture -> 0 findings -> exit 0. [[gates-must-actually-run]]
scope: |
  Adopt maintained bandit Python SAST as a merge-boundary CI check (KS13) via the charon-ci runner,
  reusing the SEMGREP required-check scaffold, with a known-bad-fixture canary asserting >=1 finding.
  Queued behind SEMGREP. [[adopt-substrate-build-only-novel-slice]] [[gates-must-actually-run]]
  [[security-is-a-ratchet-gate]]
ds: |
  ## Dependencies & sequence
  depends_on: SEMGREP-CI-REQUIRED-CHECK — QUEUED behind it (see top-level real-dep: reuses the
    required-check + branch-protection + canary scaffold). Becomes claimable when SEMGREP lands.
  concurrency: DISJOINT owns from SEMGREP, GITLEAKS-ADOPT and every other sweep ticket (its own
    check/workflow/fixture files). Runs in parallel with GITLEAKS-ADOPT after SEMGREP lands.
  wave: strong, second wave (after SEMGREP), parallel with GITLEAKS-ADOPT.
  repo: charon-private (rig) — branch here; the SAST workflow targets the product Python tree.
note: Created 2026-07-21 from the KS31/KS32 sweep (KS13 Python SAST). Queued behind
  SEMGREP-CI-REQUIRED-CHECK.
