repo: charon-private
tier: 4
work_class: rig-meta
difficulty: 4
status: done
branch: feat/substrate-first-gate-fresh
owns: fleet/checks/substrate_first_gate.py, fleet/checks/substrate-first-gate.sh, fleet/tests/substrate-first-gate.test.sh, fleet/checks/requirements.txt
substrate: N/A
substrate-novel: >-
  PyYAML was ADOPTED as the frontmatter parser (see the PyYAML row in
  fleet/state/EVAL-REGISTRY.md and the pinned install in fleet/checks/requirements.txt and
  .github/workflows/rig-ci.yml) — that is the commodity ~70% and is adopt-first in action.
  The genuinely novel slice this ticket builds is the decision-time build-vs-adopt RULE
  ENGINE: a diff-scoped gate that fires the substrate question at ticket creation or change
  and cross-checks the named tool against the consult-first EVAL-REGISTRY (exact tool match,
  alignment classification, evidence-link resolution, and same-change provenance). No external
  tool covers that combination — check-jsonschema, yamllint, JSON Schema and pre-commit were
  each evaluated and rejected for this scope (rows in EVAL-REGISTRY) because a declarative
  validator expresses at most four of the gate's fourteen rules and none of the registry
  cross-check rules that carry its actual weight.
note: >-
  Recovered by net-diff re-derivation onto current master from the stranded branch
  feat/substrate-first-gate-v2 (base drift dropped; only the gate + its wiring brought).

# SUBSTRATE-FIRST GATE — force the prior build-vs-adopt question at DECISION time

Mechanizes the operator TOP directive [[adopt-substrate-build-only-novel-slice]]: adopt
commodity substrate, hand-roll only the novel ~30%. The doctrine and a consult-first
EVAL-REGISTRY rule both existed on 2026-07-19 and both failed, because they were asserted at
SESSION level and nothing fired at DECISION level. On 2026-07-19 a ticket framed as
"Option A (patch) vs Option B (redesign)" — both BUILD options — was answered in that shape,
dispatching ~900 LOC of bespoke machinery without the substrate question ever being asked.

This gate fires when a board ticket is created or changed. It is DIFF-SCOPED — CI runs the
hard `check` only on tickets that appear in the PR diff, so existing tickets are grandfathered
and never retroactively red. `scan`/`retrofit` modes are advisory (rc 0). The frontmatter is
parsed with an ADOPTED, pinned PyYAML rather than the v1 hand-rolled 285-line sed/case/awk
parser that an adversarial review defeated nine ways (five of them parser-class defects a real
parser does not have) — replacing that commodity parser with PyYAML is itself adopt-first.

## Acceptance

- Diff-scoped decision-time firing: hard `check` runs per-changed-ticket via
  fleet/checks/rig-ci-scope.sh (`_check_ticket`), never over the whole board; existing tickets
  are not retroactively red.
- Fail-on-revert: fleet/tests/substrate-first-gate.test.sh red-proofs every detection path and
  the nine adversarial evasions (S1-S9) — 47 cases, run in CI via the allowlist.
- Wired-in-CI: added to CI_SUITES and invoked from rig-ci-scope.sh `board` (per-ticket `check`
  + PR-level `pr-has-ticket`); the runner installs the pinned parser from
  fleet/checks/requirements.txt.
- PyYAML adopted + pinned (6.0.3), fail-closed if absent; the adoption is recorded as an aligned
  EVAL-REGISTRY row.

## Dependencies & Sequence

- Depends on: fleet/state/EVAL-REGISTRY.md (the consult-first registry the gate cross-checks
  against) and fleet/checks/rig-ci-scope.sh (the CI firing layer). Both already on master.
- Sequence: the PyYAML EVAL-REGISTRY row is the record of the adopted parser; in a real CI run
  a ticket that CITES a registry row it also adds in the same PR is refused by the same-change
  provenance rule, so any tool eval row must land in a precursor change ahead of the ticket that
  cites it. This ticket cites no registry row (substrate: N/A), so it is unaffected.
- No file collisions: owns four files absent from master; wiring edits are additive.
