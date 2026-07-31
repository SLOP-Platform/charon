repo: charon-private
tier: strong
difficulty: 2
priority: 0
work_class: rig-meta
branch: feat/handoff-gate-nonbypassable
owns: fleet/land.sh, fleet/checks/rig-ci-scope.sh
depends_on: RECONCILE-WIRING
real-dep: RECONCILE-WIRING shared fleet/land.sh GATE_PARTS surface — merge-order so the conditional
  handoff-check.sh wiring COMPOSES with (does not clobber) the reconciler wiring RECONCILE-WIRING adds
  to land.sh. rig-ci-scope.sh half (public-product CI backstop) is independent.
source: scratchpad HANDOFF-FAILURE-RCA.md §3 + §5.3 (luminara-unduli stale-handoff RCA, PR #203)
note: |
  handoff-check.sh (the one gate built specifically for handoff accuracy) NEVER RAN on the botched
  07-23 handoff because the change was landed via the generic fleet/land.sh path, whose charon-private
  GATE_PARTS is validate_board.sh only (land.sh:288-304) — it does not know SESSION-HANDOFF-*.md files
  are special. CI (rig-ci-scope.sh) also never runs handoff-check.sh (grep "handoff" => zero hits).
  So the sanctioned normal merge path is a general-purpose escape hatch for ANY hand-edited handoff.
accept: |
  - fleet/land.sh: when the changed-file set for a land includes fleet/SESSION-HANDOFF-*.md, append
    `handoff-check.sh <file>` to GATE_PARTS UNCONDITIONALLY (mirror the existing per-repo GATE_PARTS
    pattern — reuse, no new gate mechanism). A land carrying a handoff edit that fails handoff-check.sh
    must be BLOCKED.
  - fleet/checks/rig-ci-scope.sh (+ rig-ci.yml if needed): add a PR-changed-scoped invocation of
    handoff-check.sh on any changed fleet/SESSION-HANDOFF-*.md, so a merge is blocked even if a session
    skips BOTH end-session.sh and land.sh's local gate. Fail-closed: unverifiable => RED, never GREEN.
  - fail-on-revert test: a fixture SESSION-HANDOFF file that handoff-check.sh flags is REFUSED by
    land.sh when in the changed set, and PASSES land when the handoff file is clean/unchanged; revert
    the GATE_PARTS append → the refusal disappears (test goes RED).
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — edits load-bearing land.sh + CI
    scope; manager gates, PR does NOT merge on the builder's self-report. Fix root cause, not symptoms;
    any pre-existing red touched is fixed or ticketed, never stepped around.
scope: |
  Close the land.sh + CI bypass so handoff-check.sh is non-bypassable for any commit touching a
  handoff file, regardless of landing path. REUSE handoff-check.sh as-is; do not rebuild it.
ds: |
  ## Dependencies & sequence
  Wave-1, no build prereq. Disjoint owns from HANDOFF-NAME-ALLOCATOR (that edits new files +
  end-session.sh:176/handoff.sh; this edits land.sh + rig-ci-scope.sh) — parallelizable. Prioritize
  alongside NAME-ALLOCATOR: the bypass is a general escape hatch, not unique to this incident.
