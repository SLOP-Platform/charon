tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: ci-infra
branch: feat/ci-workflow-policy-gate
depends_on:
owns: tools/check_workflows.py, tools/gates.json, tests/test_check_workflows.py
accept: PYTHONPATH=src python3 -m pytest tests/test_check_workflows.py -q
prompt: /home/stack/charon-private/fleet/board/briefs/CI-WORKFLOW-POLICY-GATE.md
scope: Fragility finding #8. The fragility sweep found CI workflow policy "split across
  comments not executable" — the action-pin split (ACTION-PIN-POLICY), the Windows-smoke
  fragility class, and packaging-trigger scoping each exist today only as prose/comments a
  human has to remember to re-apply on every new workflow edit, with no automated gate
  catching drift. Add one new gate, `tools/check_workflows.py`, parsing every
  `.github/workflows/*.yml` (stdlib `yaml`-free — hand-parse `uses:`/`on:`/`run:` lines the
  same lightweight way `tools/check_boundary.py` scans `src/`, since the privileged tool
  chain stays stdlib-only) and enforcing THREE checks: (1) action-ref policy — every
  first-party `actions/*` `uses:` line MUST be a bare major-version tag (`@vN`), every
  non-`actions/*` (`docker/*`, `actions/attest-*`, any third-party) `uses:` line MUST be a
  full 40-char commit SHA; (2) reject fragile Windows smoke patterns — flag any
  `Start-Process` usage in a `run:` block (the known-fragile async-launch-then-poll pattern
  that already caused rot on `windows-exe.yml`, per HANDOFF-2026-07-04-v2 finding #2); (3)
  require a `paths:` filter under `on: push:`/`on: pull_request:` for any workflow that
  builds/packages the product (`release.yml`, `windows-exe.yml`, `heavy.yml`'s
  `modeA-isolation`/`image-smoke` jobs) so a docs-only change never triggers a full package
  build. Register the gate in `tools/gates.json` (id `workflow-policy`, `ci_step: true`,
  `red_proof: tests/test_check_workflows.py`) following the existing entries' shape (see
  `boundary-check`/`ruff-lint` rows). Per AGENTS.md Structural Rule 3 ("every new gate added
  to tools/ must land with its red-proof test in tests/ in the same commit"), write
  `tests/test_check_workflows.py` with fixture workflow YAML strings that are deliberately
  BAD (major-tag third-party action, `Start-Process` in a run block, missing `paths:` on a
  packaging workflow) and assert the gate rejects each one, plus a GOOD fixture the gate
  accepts — the red-proof must fail before the gate logic exists and pass only once it's
  correct, per the standard "prove the gate actually gates" rule.
note: Standard review. No depends_on — independently buildable; the gate is proven against
  FIXTURE workflow YAML (owns is disjoint from ACTION-PIN-POLICY's `.github/workflows/*.yml`,
  so this ticket must not itself run the gate against the live workflow files). Do NOT wire
  `workflow-policy` into the CI pipeline (or add it to the repo's own pre-commit gate run)
  until ACTION-PIN-POLICY has merged — the live `.github/workflows/*.yml` still has
  first-party actions SHA-pinned today, which this gate's action-ref check would reject.

