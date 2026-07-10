tier: economy
difficulty: 1  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: ci-infra
branch: chore/action-pin-policy
depends_on:
owns: .github/workflows/ci.yml, .github/workflows/heavy.yml, .github/workflows/release.yml, .github/workflows/windows-exe.yml
accept: ! grep -rEn "uses: (docker|actions/attest)[a-zA-Z0-9._/-]*@v[0-9]" .github/workflows/*.yml && grep -rq "uses: actions/checkout@v4" .github/workflows/*.yml
prompt: /home/stack/charon-private/fleet/board/briefs/ACTION-PIN-POLICY.md
scope: Fragility finding #3 / handoff next-action #7. Every `uses:` line across
  `.github/workflows/*.yml` is currently pinned to a full commit SHA with a trailing
  `# vX` comment (e.g. `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5  # v4`) —
  including GitHub's own first-party `actions/*`. The fragility sweep found this
  "overcomplicated, fails silently": a first-party SHA pin doesn't move when GitHub patches
  a tag, so Dependabot's SHA-pin tracking (see `CI-ACTION-BUMP-INVESTIGATION.md`) is doing
  the real work of following `v4`/`v5` anyway, and a stale/incorrect SHA comment silently
  decouples from the tag it claims to be. Adopt the operator-approved split: first-party
  `actions/*` (checkout, setup-python, upload-artifact) move to plain major-version tags
  (`@v4`, `@v5`, `@v4.4.3` -> `@v4`) since GitHub controls that trust boundary end-to-end;
  third-party actions (`docker/login-action`, `docker/build-push-action`,
  `actions/attest-build-provenance` — supply-chain-sensitive, non-GitHub-controlled or
  security-critical) keep strict full-SHA pins. Audit every `uses:` line in the four
  workflow files and convert per this split; leave a one-line comment on each converted
  line noting the policy (e.g. `# first-party major-tag policy`).
note: Standard review, mechanical. No depends_on — independently buildable; CI-WORKFLOW-POLICY-GATE
  will later enforce this same split as an automated gate, but does not block this ticket.
