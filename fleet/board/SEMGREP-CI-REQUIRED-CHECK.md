repo: charon-private
tier: strong
difficulty: 4
work_class: ci-infra
substrate: Semgrep — adopt — maintained SAST/policy engine is the established substrate; this ticket ships only the novel thin slice (a git-tracked ruleset + a wrapper that sets exit-code semantics for a merge-blocking required check + a fail-on-revert canary). No hand-rolled linter/parser. [[adopt-substrate-build-only-novel-slice]]
branch: feat/semgrep-ci-required-check
depends_on:
owns: fleet/checks/semgrep.sh, .github/workflows/semgrep.yml, fleet/semgrep-rules/charon-policy.yml, fleet/tests/semgrep-canary.test.sh, fleet/tests/fixtures/semgrep-known-bad.py
serial_justified: |
  The owned surfaces are ONE adopt-a-tool unit, not independent builds: the workflow
  (semgrep.yml) invokes the wrapper (semgrep.sh) which runs the ruleset (charon-policy.yml) against the
  known-bad fixture, and the canary test asserts that whole chain finds >=1. Splitting them ships a
  half-wired gate (a workflow with no wrapper, or a rule with no canary) — the exact zero-work-green
  defect this ticket exists to prevent. Ship together.
accept: |
  UMBRELLA: KS31/KS32 tool-adoption sweep (thin adapters over best-in-class; Charon uses only ~3 of
  ~15 maintained tools). This is the Layer-D authority tier from the meta-gate deep-dive
  (scratchpad/DEEPDIVE-METAGATE.md §3 Layer D; EVAL-REGISTRY.md "Semgrep | ADOPT" row 2026-07-21):
  the only enforcement that is server-side, un-bypassable, and runs on the diff regardless of which
  harness (Claude Code OR opencode OR any gateway-driven worker) produced it.

  ADOPT Semgrep as a CI REQUIRED-CHECK on BOTH repos — product `charon` AND rig `charon-private` —
  under branch protection on the pending `charon-ci` self-hosted runner. This is ADOPT-the-tool, NOT
  hand-roll: wire the maintained Semgrep engine + a small git-tracked ruleset, do not build a bespoke
  linter.

  SCOPE (read carefully — this is the on-plan / policy BACKSTOP, NOT the key-exfil security invariant):
    - Semgrep here enforces on-plan / policy / convention rules at the merge boundary. It is the
      "verify a gate EXECUTED, not just CI green" authority tier ([[gates-must-actually-run]]).
    - It does NOT carry the provider-key-exfil security invariant — that is owned by the egress proxy
      (Stripe Smokescreen + docker-native egress denial, see FIX-PROVIDER-KEY-EXFIL / DEEPDIVE-SECURITY).
      Do not conflate the two; do not weaken the egress design to "let Semgrep handle it".

  DO (COMPOSE the maintained tool; do not rebuild):
    (a) fleet/checks/semgrep.sh — thin wrapper that runs `semgrep --config fleet/semgrep-rules/`
        (and the relevant registry packs) over the diff, exit non-zero on any finding.
    (b) .github/workflows/semgrep.yml — required status check, runs on the `charon-ci` runner, wired
        on BOTH repos. Under branch protection so exit 1 BLOCKS merge on either repo.
    (c) fleet/semgrep-rules/charon-policy.yml — the git-tracked policy ruleset (start minimal;
        on-plan/convention rules, NOT the egress invariant).

  KNOWN-BAD-FIXTURE CANARY (NON-NEGOTIABLE — no zero-work green): fleet/tests/fixtures/semgrep-known-bad.py
  contains a snippet the ruleset MUST flag. fleet/tests/semgrep-canary.test.sh asserts the wrapper
  reports >=1 finding on that fixture. A ruleset that matches nothing looks identical to a clean tree
  (the C1 zero-work-green failure mode) — the canary is what proves the gate actually EXECUTED.

  FAIL-ON-REVERT (fleet/tests/semgrep-canary.test.sh — REQUIRED):
    (1) CANARY FIRES: run the wrapper on the known-bad fixture -> >=1 finding (RED-on-that-file).
        Delete/neuter the rule that catches it -> finding count drops to 0 -> the canary test FAILS.
    (2) CLEAN PASSES: run on a clean fixture -> 0 findings -> exit 0.
  So a vacuous ruleset can NEVER print OK.
scope: |
  Adopt maintained Semgrep as a merge-blocking CI required-check on both repos (product + rig) via the
  pending charon-ci runner + branch protection, enforcing on-plan/policy/convention rules (NOT the
  key-exfil invariant, which the egress proxy owns). Ship with a known-bad-fixture canary asserting
  >=1 finding so the gate cannot go zero-work-green. Layer-D authority tier of the meta-gate design.
  [[gates-must-actually-run]] [[adopt-substrate-build-only-novel-slice]] [[security-is-a-ratchet-gate]]
  [[reviews-use-our-own-tools]]
ds: |
  ## Dependencies & sequence
  depends_on: (none) — this is the FIRST tool-adoption ticket in the KS31 sweep and the authority tier
    the others reuse. GITLEAKS-ADOPT and BANDIT-ADOPT are QUEUED behind THIS ticket (they reuse the
    required-check + branch-protection + canary scaffold it establishes on the charon-ci runner).
  wave: strong. Land first, then release the queued scanner-adoption tickets.
  concurrency: runs alone on its owned surface (new files: fleet/checks/semgrep.sh,
    .github/workflows/semgrep.yml, fleet/semgrep-rules/, fleet/tests/semgrep-canary.test.sh + fixture).
    No shared-file collision with any live ticket.
  blocked-by-infra: needs the `charon-ci` self-hosted runner pool ready to host the required check
    (open question 3 in DEEPDIVE-METAGATE §4). If the runner is not yet up, land the wrapper + canary
    + workflow file and enable the branch-protection required-check the moment the runner is live.
  repo: charon-private (rig) — the ticket + branch live here; the workflow is wired on BOTH repos.
note: Created 2026-07-21 from the KS31/KS32 tool-adoption sweep (EVAL-REGISTRY.md Semgrep ADOPT row;
  scratchpad/DEEPDIVE-METAGATE.md §3 Layer D). Meta-gate authority tier — un-bypassable merge boundary
  covering every harness (Claude Code, opencode, gateway workers). NOT the key-exfil invariant.

landed: PR #141 — Semgrep adopted as on-plan policy backstop; manager-verified canary 8/8 (fail-on-revert); diff-scoped, CI_RUNNER var for charon-ci-when-live
