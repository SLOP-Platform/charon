repo: charon
tier: economy
priority: 0
difficulty: 3
work_class: ci-infra
branch: feat/scanner-relocate
depends_on:
owns: .github/workflows/bandit.yml, .github/workflows/gitleaks.yml, .github/workflows/semgrep.yml, .github/scripts/
serial_justified: |
  The three scanners are one relocation, not three. They share a single new home
  (.github/scripts/), a single set of adapted path-scoping rules, and one ordering constraint
  that spans all of them — the workflows must be OBSERVED green on a real PR before any of the
  three contexts is added to branch protection, because a required check that has never run
  blocks every PR forever. Splitting them into three tickets would create three independent
  chances to add a context ahead of its first run.
substrate: N/A
substrate-novel: |
  NO TOOL IS ADOPTED HERE. bandit 1.9.4, gitleaks 8.21.2 and semgrep 1.161.0 are already adopted
  and already running. This ticket only MOVES the enforcement point. The novel slice is the
  path-scope adaptation from the rig tree to the product tree and the rule-set triage that keeps
  the gates from reding on legitimate product code.
source: |
  OPERATOR DECISION D-013 (fleet/state/DECISIONS.md, 2026-08-04), plus D-016 for the runner
  constraint.
note: |
  OPERATOR DECISION D-013, verbatim: "Move them. Tools that do nothing should be moved to where
  it makes sense. NO need to ask me about that."

  MEASURED: semgrep/gitleaks/bandit have 371-384 green runs on the rig repo and block nothing —
  that repo is on a free plan and its branch-protection endpoint returns 403, so no check there
  can EVER be required. The product repo HAS protection but requires only ["gate"].

  SCOPE
  1. Port the three wrappers + their fail-on-revert canaries + the semgrep ruleset + the
     known-bad fixtures into the PRODUCT repo under .github/scripts/ (CI-only, not product code,
     not linted/typechecked as product source, and NOT a rig directory).
  2. Adapt the scan scope from the rig tree to the product tree.
  3. Add three workflows that run on pull_request, HARD-PINNED to ubuntu-latest per D-016 (the
     product repo is PUBLIC; a self-hosted runner there lets a fork's PR execute code on the
     hardware that runs the gateway).
  4. Only AFTER each check has been observed producing a real conclusion on a real PR, add
     "bandit", "gitleaks", "semgrep" to the required contexts on master.

  ⛔ DO NOT set the CI_RUNNER variable on the product repo.
  ⛔ DO NOT create a fleet/ directory in the product or import rig code.
  ⛔ DO NOT touch tools/check_security.py — its overlap with bandit/gitleaks is a separate,
     unmade operator decision.

  DONE CONTRACT
  a. Each of the three canaries passes locally against the pinned tool version.
  b. Each gate is OBSERVED RED: a mutation makes the wrapper exit 1, and restoring makes it exit
     0. A gate nobody has seen fail is not proven.
  c. Fail-closed is preserved: a shallow checkout (unresolvable merge-base), a missing tool, a
     zero-rule config, and a zero-file scan all exit non-zero.
  d. The product gate (python3 -m charon.cli gate) is GREEN.

## Dependencies & Sequence

- **depends_on: (none). IMMEDIATELY ELIGIBLE.** Nothing blocks it and it blocks nothing.
- **owns-collision: NONE.** All owned paths are new files under .github/scripts/ plus three new
  workflow files. No live ticket declares .github/workflows/bandit.yml, gitleaks.yml or
  semgrep.yml, and .github/scripts/ does not exist yet.
- **Explicitly NOT owning tools/check_security.py.** The product's hand-rolled scanner overlaps
  bandit (shell=True, eval/exec) and gitleaks (secrets in source) on src/. Consolidating them is
  a separate operator decision that has not been made; touching it here would smuggle that
  decision in under a relocation.
- **Sequence: the required-contexts step is STRICTLY LAST**, after a real green run is observed
  on a real PR. Adding a context that has never reported blocks every subsequent PR forever.
