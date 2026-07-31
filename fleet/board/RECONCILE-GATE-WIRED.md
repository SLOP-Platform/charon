repo: charon-private
tier: strong
difficulty: 3
priority: 0
work_class: rig-meta
branch: fix/reconcile-gate-wired-v2
owns: fleet/checks/reconcile-gate-wired.sh, fleet/tests/reconcile-gate-wired.test.sh
serial_justified: The check and its fail-on-revert test are one invariant — a meta-gate that
  detects built-but-inert checks must ship with the fixture proving it goes RED when a check is
  unwired; the two are inseparable.
depends_on:
source: fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md §1.3 (design PR #178, RANK-0 LEAD)
work_class_note: rig-meta — the wired-but-never-run / built-but-inert meta-gate (the literal
  GATE-GAP-LEDGER row on tools/check_catalog_case_quant.py). Rig integrity, no product feature.
note: |
  PRIORITY BUMPED 1->0 (2026-07-23, P0 mint wave): fleet/state/META-TOOL-WIRED-AND-WORKING.md's
  adopt-first verdict names landing this stranded detector (branch feat/reconcile-gate-wired,
  commit d603494, "detector, no wire") the SINGLE HIGHEST-LEVERAGE action in the whole
  built-but-not-wired class — the meta-tool that detects built-but-inert code is ITSELF
  built-but-inert. No duplicate ticket was minted for "land it" (KSF-VENDOR-GATES, this same
  wave, depends on this ticket conceptually per that doc's adoption-plan step order, not via a
  hard owns-overlap depends_on since the files are disjoint) — this IS that ticket, priority-
  aligned instead of forked. [[detection-ticketed-never-built]]
  §1.3 — the gate-declared-vs-actually-wired reconciler. desired-source = every gate/check/rule
  declared in fleet/checks/*.sh + *.py, tools/check_*.py + *.sh (cross-repo product suite),
  RULE-REGISTRY.tsv rows with status ∈ {ACTIVE,ENFORCED}, and EVAL-REGISTRY.md rows with
  verdict=ADOPT + non-empty enforced_in. actual-source = the set actually executed by a real
  firing layer: rig side = fleet/preflight.sh:841 scan dispatch, fleet/land.sh, fleet/validate_board.sh,
  fleet/hooks/pre-*.sh; product side = .github/workflows/*.yml run: steps + native
  branch-protection required-checks (strongest signal).

  REUSE-FIRST: this is the SAME shape as the rule-coverage meta-gate
  (tools/check_gate_registry_execution.py / PR #119) and fleet/checks/rule-coverage.sh — compose /
  extend that cross-reference machinery, do NOT rebuild the declared↔fired join. drift-algorithm =
  graph-reachability (KS29 leg): declared nodes MUST be reachable from the firing-layer root
  (preflight / land.sh / CI); wired-but-never-reached is the RED. Static-grep the firing-layer
  source for each declared check's basename (allow known-wrapper aliases, e.g. gitleaks.sh →
  gitleaks). The product-side ground truth is cross-repo (/home/stack/code/charon); the rig side
  is in-tree.
revisions_baked_in: |
  REVISION-1 (fail CLOSED, #182): a declared check whose firing status cannot be positively
  proven defaults to RED (assumed inert), NEVER pass. R-G (declared but in NO actual-source →
  built-but-inert RED, "wire into <layer> at <location>"), R-H (fired but NOT declared →
  "declare this" RED, catches ad-hoc load-bearing snippets), R-I (declared+fired but only on a
  master-gated path while reconciling a feature branch → deploy-context-blind RED with the
  context-of-validity annotation). An unrecognized firing layer is treated as "does not fire"
  (closed), not "assume it fires."
  REVISION-2 (timer-wireable today, #182): wireable now — standalone
  `bash fleet/checks/reconcile-gate-wired.sh` (exit 0 clean / non-zero on RED). Designed for
  insertion into fleet/preflight.sh:841 scan chain, fleet/land.sh pre-condition, and
  fleet/foreman-cadence.sh `cadence` interval-gated timer (foreman-cadence.sh:87-102) — all exist
  today. NOTE (honest seam, per REVISION-2): the PRODUCT-side firing ground truth (native
  GitHub required-checks) is only machine-checkable on the product repo /home/stack/code/charon;
  when that checkout is unavailable the check runs rig-side-only and reports the product axis as
  UNVERIFIED (fail-closed: UNVERIFIED ≠ GREEN), it does NOT skip silently. Wiring owned by
  RECONCILE-WIRING; not inert on merge (WIRING depends_on this).
accept: |
  - fleet/checks/reconcile-gate-wired.sh: builds (declared-set, fired-set), computes set-diff,
    emits R-G / R-H / R-I per above; reuses the rule-coverage.sh / check_gate_registry_execution.py
    cross-reference where it already covers a subset. Exit non-zero on any RED; exit 0 clean.
  - Product-repo-absent path reports UNVERIFIED for the product axis (fail-closed), never a
    false-GREEN.
  - fail-on-revert test (fleet/tests/reconcile-gate-wired.test.sh): (a) a fixture tools/check_*.py
    (or fleet/checks/*.sh) declared-but-invoked-nowhere → R-G RED, then add its invocation to a
    fixture firing layer → GREEN; (b) a load-bearing shell snippet fired but unregistered →
    R-H RED. Revert the reachability walk → tests go RED.
  - Cite the stass-allie WLS-7 validation (implement-as-pattern is the sanctioned hand-roll).
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
scope: |
  Rig-only detector (product axis read-only cross-repo). Closes the built-but-inert class.
  drift-primitive: graph-reachability (KS29). No product change (does not auto-wire — auto-wiring
  is a product change, not a drift check).
ds: |
  ## Dependencies & sequence
  Wave-1, no build prereq — independent of the other reconcilers (disjoint owns:; parallelizable).
  RECONCILE-WIRING depends_on THIS. Reuse rule-coverage.sh / check_gate_registry_execution.py;
  do not rebuild the declared↔fired cross-reference.
