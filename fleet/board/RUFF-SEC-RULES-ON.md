repo: charon
tier: strong
priority: 1
difficulty: 3
work_class: ci-infra
branch: fix/ruff-sec-rules-on
owns: pyproject.toml, tests/test_lint_security_rules.py
serial_justified: One lint-config change plus the burn-down it forces; splitting ships a rule nobody can pass.
substrate: |
  ruff — ADOPT (already adopted, already running in CI). This ticket adds no tool: it ENABLES two
  rule families in the tool we already run. The security scanning question was previously answered
  by adopting standalone bandit (fleet/checks/bandit.sh), which is a DIFFERENT tool covering
  overlapping ground; ruff's S rules are the same checks inside the linter already on every file,
  at no extra runtime and no new dependency.
depends_on:
note: |
  REOPEN-equivalent — mint fresh rather than reopen, because the prior tickets were honestly done
  for their own scope.

  BANDIT-ADOPT and BANDIT-PREEXISTING-FINDINGS are both in fleet/state/done/ and
  fleet/board/archive/. They wired STANDALONE bandit at fleet/checks/bandit.sh. They never touched
  the ruff config.

  MEASURED 2026-08-01: pyproject.toml:52 is still `select = ["E","F","I","B","UP"]` — ruff's `S`
  (flake8-bandit) and `BLE` (blind-except) families are OFF. Turning them on surfaces 72 findings,
  including `shell=True` and bind-all-interfaces.

  This is why "is it ticketed?" is the wrong question and "does it FIRE?" is the right one: two
  security tickets closed green while 72 findings sat unreported in the linter we run on every
  file of every PR.
accept: |
  - `S` and `BLE` added to the ruff select list in pyproject.toml.
  - The 72 existing findings are either FIXED or explicitly baselined with a per-finding reason —
    a blanket noqa sweep is NOT acceptable and defeats the ticket.
  - Any genuine `shell=True` / bind-all-interfaces finding is FIXED, not baselined; those are the
    reason this ticket exists.
  - `ruff check src tests` is green at the end.
  - fail-on-revert test asserting the rule families are enabled, so removing them from the select
    list goes RED. Red-proof externally, report both counts.

## Dependencies & Sequence

- **depends_on: (none).**
- **Sequence: soon.** It is a security ratchet — every PR merged before it lands is unscanned by
  these rules.
- **Blocks / unblocks:** nothing blocks on it, but it is a merge-gate hardening and per the
  security-is-a-ratchet rule must never be weakened once on.
- **owns-collision:** `pyproject.toml` is shared config — check for in-flight tickets touching it
  and sequence rather than co-write.
