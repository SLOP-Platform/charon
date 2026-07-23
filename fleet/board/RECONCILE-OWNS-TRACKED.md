repo: charon-private
tier: strong
difficulty: 3
priority: 1
work_class: rig-meta
branch: feat/reconcile-owns-tracked
owns: fleet/checks/reconcile-owns-tracked.sh, fleet/tests/reconcile-owns-tracked.test.sh
serial_justified: The check and its fail-on-revert test are one invariant — a tracking
  reconciler with no RED-on-revert fixture is itself the vanish-untracked class it detects.
  They land as one unit.
depends_on:
source: fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md §1.2 (design PR #178, RANK-0 LEAD)
work_class_note: rig-meta — durable-design-vanishes-untracked is a rig hygiene / integrity gate,
  no product surface. This is the literal class on the call-stack when the LEAD was filed (the
  fleet/state/* blanket .gitignore ate the design doc).
note: |
  §1.2 — the owns-tracked reconciler. desired-source = every ticket's owns: set (parsed from
  fleet/board/*.md + archive/*.md) ∪ the durable-design catalog under fleet/state/*
  (ANTI-CLOBBER-FIX-REPORT, BLAST-TIER-ENFORCEMENT-DESIGN, EVAL-REGISTRY, RULE-REGISTRY,
  ROADMAP, REVIEWS-stass-allie, … per §1.2 — the operator-confirmed set). actual-source =
  git ls-files (tracked) + git status --porcelain (untracked-on-disk) + git check-ignore
  (gitignored). Each file lands in exactly one bucket.

  REUSE-FIRST: compose git plumbing (ls-files / status --porcelain / check-ignore) and the
  board/owns: parser already used by validate_board.sh — do NOT re-implement owns: extraction.
  drift-algorithm = subset/schema-conformance (KS29 leg): every element of a known set
  (owned-paths ∪ durable-design catalog) MUST appear in another known set (git-tracked, or
  gitignored-WITH-a-matching `!` exemption).

  SELF-EATING DOGFOOD: the R-E fixture MUST reference THIS design doc
  (fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md) as its canonical example — it is gitignored
  by the fleet/state/* blanket rule and was force-added; the RED it produces is the desired
  signal, not a bug (§8 of the design). Every new file THIS v1 build adds must itself be
  owns:-tracked — the gate runs on itself (KS20).
revisions_baked_in: |
  REVISION-1 (fail CLOSED, #182): any owns: path whose git status the classifier cannot resolve
  to a known bucket (tracked / gitignored-with-exemption) defaults to RED (needs-attention), NEVER
  pass. R-D (untracked-on-disk → RED, action: git add), R-E (gitignored without a `!` exemption →
  RED, surfaces two surgical options: add `!` exemption OR move to a tracked-by-default location —
  the gate does NOT auto-edit .gitignore, it surfaces the choice), R-F (durable-catalog file in no
  ticket's owns: AND not gitignored → RED "who owns this?"). Absence of a positive tracked-proof
  is RED, not silent pass.
  REVISION-2 (timer-wireable today, #182): wireable now — standalone
  `bash fleet/checks/reconcile-owns-tracked.sh` (exit 0 clean / non-zero on RED). Designed for
  insertion into fleet/preflight.sh:841 scan chain, fleet/land.sh pre-condition, and
  fleet/foreman-cadence.sh `cadence` interval-gated timer (foreman-cadence.sh:87-102) — the
  overnight-untracked-doc drift class is precisely why the timer leg matters (caught at next tick,
  not next land). Wiring owned by RECONCILE-WIRING; not inert on merge (WIRING depends_on this).
accept: |
  - fleet/checks/reconcile-owns-tracked.sh: walks (owns: ∪ durable-design catalog), buckets each
    path via git ls-files / status --porcelain / check-ignore; emits R-D / R-E / R-F per above.
    Exit non-zero on any RED; exit 0 clean.
  - R-E surfaces BOTH surgical options and does NOT auto-edit .gitignore (owner of .gitignore is
    whoever edits it, not this gate).
  - fail-on-revert test (fleet/tests/reconcile-owns-tracked.test.sh): (a) a temp owns: path on
    disk but not in git ls-files → R-D RED, then git add → GREEN; (b) a path matched by a blanket
    gitignore with no `!` exemption → R-E RED (fixture cites the design doc's own situation);
    (c) a durable-catalog entry in no owns: → R-F RED. Revert the bucket logic → tests go RED.
  - Cite the stass-allie WLS-7 validation (implement-as-pattern is the sanctioned hand-roll).
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
scope: |
  Rig-only. Closes the durable-design-vanishes-untracked class (the fleet/state/* blanket-gitignore
  eating design-of-record). drift-primitive: subset/schema-conformance (KS29). No product change.
ds: |
  ## Dependencies & sequence
  Wave-1, no build prereq — independent of the other reconcilers (disjoint owns:; parallelizable).
  RECONCILE-WIRING depends_on THIS. Reuse validate_board.sh's owns: parser + git plumbing; do not
  rebuild owns: extraction.
