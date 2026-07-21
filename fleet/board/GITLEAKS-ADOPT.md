repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/gitleaks-adopt
depends_on: SEMGREP-CI-REQUIRED-CHECK
real-dep: SEMGREP-CI-REQUIRED-CHECK — genuine build/sequencing prereq, not merge-order preference. That
  ticket ESTABLISHES the reusable CI-required-check scaffold this ticket consumes: the charon-ci-runner
  workflow pattern, the branch-protection required-check wiring on BOTH repos, and the known-bad-fixture
  canary convention (>=1 finding or the gate is zero-work-green). gitleaks reuses that exact scaffold;
  building it before SEMGREP lands means building against an unshipped pattern. owns are DISJOINT
  (different check/workflow/fixture files) so this dep is JUSTIFIED here, not implied by file overlap.
owns: fleet/checks/gitleaks.sh, .github/workflows/gitleaks.yml, fleet/tests/gitleaks-canary.test.sh, fleet/tests/fixtures/gitleaks-known-bad.txt
serial_justified: The owned surfaces are ONE adopt-a-scanner unit: the workflow invokes the wrapper,
  the canary test asserts the wrapper flags the planted secret in the fixture. Splitting ships a
  half-wired scanner (workflow with no wrapper, or scan with no canary) — the zero-work-green defect
  this ticket guards against. Ship together.
accept: |
  UMBRELLA: KS31/KS32 tool-adoption sweep + KS13 (secret-scanning as a CI check). ADOPT the maintained
  gitleaks secret-scanner as a CI check on the charon-ci runner — do NOT hand-roll a regex secret
  scanner.

  DO (COMPOSE the maintained tool):
    (a) fleet/checks/gitleaks.sh — thin wrapper running `gitleaks detect`/`gitleaks git` over the diff,
        exit non-zero on any leaked-secret finding.
    (b) .github/workflows/gitleaks.yml — CI check on the charon-ci runner, reusing the SEMGREP-established
        required-check + branch-protection scaffold, on BOTH repos (product + rig).
    (c) KNOWN-BAD-FIXTURE CANARY (NON-NEGOTIABLE): fleet/tests/fixtures/gitleaks-known-bad.txt contains a
        planted fake secret gitleaks MUST flag; fleet/tests/gitleaks-canary.test.sh asserts >=1 finding —
        so a mis-configured/no-op scan can never print green (C1 zero-work-green defense).

  FAIL-ON-REVERT (fleet/tests/gitleaks-canary.test.sh — REQUIRED): wrapper on the known-bad fixture ->
  >=1 finding; neuter the config so it detects nothing -> finding count 0 -> canary test FAILS. Clean
  fixture -> 0 findings -> exit 0. [[gates-must-actually-run]]
scope: |
  Adopt maintained gitleaks as a merge-boundary CI secret-scan (KS13) on both repos via the charon-ci
  runner, reusing the SEMGREP required-check scaffold, with a known-bad-fixture canary asserting >=1
  finding. Queued behind SEMGREP. [[adopt-substrate-build-only-novel-slice]] [[gates-must-actually-run]]
  [[security-is-a-ratchet-gate]]
ds: |
  ## Dependencies & sequence
  depends_on: SEMGREP-CI-REQUIRED-CHECK — QUEUED behind it (see top-level real-dep: reuses the
    required-check + branch-protection + canary scaffold SEMGREP establishes). Becomes claimable when
    SEMGREP lands.
  concurrency: DISJOINT owns from SEMGREP and every other sweep ticket (its own check/workflow/fixture
    files). After SEMGREP lands it can run in parallel with BANDIT-ADOPT (also queued behind SEMGREP) —
    no shared files between them.
  wave: strong, second wave (after SEMGREP).
  repo: charon-private (rig) — branch here; workflow wired on both repos.
note: Created 2026-07-21 from the KS31/KS32 sweep (KS13 secret-scanning). Queued behind
  SEMGREP-CI-REQUIRED-CHECK.
