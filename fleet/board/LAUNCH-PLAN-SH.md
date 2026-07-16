tier: strong
difficulty: 2
work_class: ci-infra
branch: feat/launch-plan-sh
repo: charon-private
parent: LAUNCH-PLAN-GATE
depends_on:
owns: /home/stack/charon-private/fleet/launch-plan.sh, /home/stack/charon-private/fleet/tests/launch-plan.test.sh
note: |
  Manually decomposed sub-ticket of LAUNCH-PLAN-GATE (fleet/decompose.sh's plan_decomposition
  engine was unavailable 2026-07-15 — whole model pool 429/exhausted). Disjointness verified by
  hand: this ticket owns only launch-plan.sh + its own test file; STALE-CHECK-SH (sibling) owns
  the unrelated stale-check.sh + its own separate test file — the two tools share no code path,
  no shared state, and the parent ticket itself says "make stale-check.sh standalone."
accept: |
  MECHANIZE the manager-side pre-launch discipline that today is a RULE (MANAGER-OPERATING-RULES §3)
  and keeps needing reminders: decompose -> right-model -> monitor.
  fleet/launch-plan.sh [ticket ...] (default: all READY tickets from the board): for each candidate it
  COMPOSES the existing tools — never reimplements them:
    1. parallelizability-gate (fleet/checks/parallelizability-gate.sh): REFUSE to plan a splittable-but-
       undecomposed ticket (difficulty>=M AND >1 owned surface, no serial_justified) — tell the operator
       to run fleet/decompose.sh first. This is a hard gate, not advisory.
    2. assign.py (fleet/capability/assign.py <ticket>): pick the best model for the ticket's work_class+
       tier; carry the rationale. A REFUSED (blocked/D&S) ticket is dropped from the launchable set with
       its blockers shown.
    3. CONTEXT-FIT FILTER (v1 mechanical): drop any candidate model whose declared max_context cannot hold
       the unit's estimated context (est-tokens). Read per-model context caps from the roster/catalog
       (fleet/state model caps or gateway config max_context). Leave a documented hook `# v2: empirical
       work_class fitness from dogfood (see task work-context-fitness)` for the quality-fit layer — do NOT
       build v2 here.
    4. GROUP into collision-free WAVES by depends_on + owns (no two planned tickets in the same wave write
       the same file). Emit, per wave, per ticket: the tier, the assign.py-picked model (NAMED), and the
       exact operator tab command (fleet-droid.sh <tier> --wait 3 --retries 10) + the ticket it will claim.
  Output is a plain-text wave plan (matches report.sh style), consumable by the operator to open tabs.
  FAIL-ON-REVERT (fleet/tests/launch-plan.test.sh): (a) a splittable-undecomposed fixture ticket is
  REFUSED by launch-plan (revert the gate -> it plans anyway -> test fails); (b) a ticket with a
  work_class+tier plans with a NAMED model from assign.py; (c) a model whose max_context < the unit's
  est-tokens is filtered out. Hermetic (stub assign.py / board fixtures; no network).
scope: |
  Manually-decomposed single-domain sub-ticket of LAUNCH-PLAN-GATE (fleet/decompose.sh).
