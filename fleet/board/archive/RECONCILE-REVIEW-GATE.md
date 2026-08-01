repo: charon-private
tier: strong
difficulty: 3
priority: 1
work_class: rig-meta
branch: feat/reconcile-review-gate
owns: fleet/checks/reconcile-review-gate.sh, fleet/tests/reconcile-review-gate.test.sh
serial_justified: The check and its fail-on-revert test are one invariant — the review-gate axis
  and the fixture proving it BLOCKS an unreviewed hot-path change are inseparable; a review gate
  with no revert test is the norm-but-unenforced class it exists to close.
depends_on:
source: fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md §2.1 + §2.2 (design PR #178, RANK-0 LEAD)
work_class_note: rig-meta — the folded review-gate axis (declared-review-required vs
  review-actually-happened) + the fail-closed taxonomy. Rig integrity; folds BLAST-TIER
  Consumer A. Grading consumer (Consumer B) is PARKED (§2.3, empty grade substrate — not a dep).
note: |
  §2.1 — the review-gate axis, folded as an axis of the same engine. desired-source = every change
  in the reconcile window whose blast_tier ≥ hot-path. For v1 the BLAST-TIER substrate
  (src/charon/blast_tier.py) is designed-but-unbuilt, so use the ticket `tier:` field + a
  path-pattern fallback as the proxy — the fallback is REMOVED once the substrate lands (do NOT
  build the substrate here; land the path-pattern fallback). actual-source =
  docs/review-log/<id>.md (operator-merged fragment) + fleet/state/reviewed/<id> machine marker
  (reviewed_sha / author_model / reviewer / verdict / findings). drift-algorithm =
  content-hash/checksum (KS29 leg): the recorded reviewed_sha MUST equal the merge commit sha;
  the reviewer MUST NOT be the author model (or MUST be the operator).

  REUSE-FIRST: reuse the ReviewerCircuitBreaker (src/charon/failover.py:73-142) for the doom-loop
  (R-L review→fix→review-not-closed) case — do NOT hand-roll a loop detector. Reuse the
  fleet/state/reviewed/<id> marker convention already referenced by RECONCILE-BOARD-PR-DONE's
  adjudication ledger (shared marker shape, disjoint files).
revisions_baked_in: |
  REVISION-1 (fail CLOSED, #182) — THIS is the taxonomy home (§2.2). The old tier=path-pattern map
  was gameable (an unknown src/charon/new.py matched nothing → tier 0 → no review). Fail closed:
  any path/work_class the classifier does not recognize is treated as tier = max(recognized,
  hot-path). Concretely: unknown src/charon/*.py → hot-path (higher inside forwarder/proxy_server/
  api/router/capability/balance/meter/billing/egress/keys/secret/acl prefixes); unknown work_class
  → hot-path; unknown docs/ or fleet/ → tier 0. This is the K8s admission-controller posture:
  deny on unrecognized policy, do not deny on absence. RED conditions: R-J (≥hot-path change with
  NO review-log fragment AND no reviewed/<id> marker at merge sha → BLOCK), R-K (fragment present
  but reviewed_sha ≠ merged sha → BLOCK, "re-review at HEAD"), R-L (verdict=FIXES with no
  follow-up review → BLOCK, doom-loop via ReviewerCircuitBreaker). Absence-of-review is BLOCK,
  never silent pass.
  REVISION-2 (timer-wireable today, #182): wireable now — standalone
  `bash fleet/checks/reconcile-review-gate.sh` (exit 0 clean / non-zero on BLOCK). Designed for
  insertion into fleet/preflight.sh:841 scan chain, fleet/land.sh pre-condition (this is the
  BLOCK point — an unreviewed hot-path change must not advance to merge), and
  fleet/foreman-cadence.sh `cadence` timer (foreman-cadence.sh:87-102) — all exist today. Wiring
  owned by RECONCILE-WIRING; not inert on merge (WIRING depends_on this).
accept: |
  - fleet/checks/reconcile-review-gate.sh: classifies each in-window change to a blast tier
    (fail-closed taxonomy above; tier: + path-pattern proxy pre-substrate); for ≥hot-path,
    verifies docs/review-log/<id>.md AND fleet/state/reviewed/<id> with reviewed_sha == merged sha
    and reviewer ≠ author model. Emits R-J / R-K / R-L. Exit non-zero on any BLOCK; exit 0 clean.
  - The fail-closed taxonomy is the module-level rule (§2.2): unrecognized path/work_class →
    hot-path, proven by a test fixture. The path-pattern fallback is clearly marked
    remove-when-substrate-lands.
  - Reuses ReviewerCircuitBreaker (failover.py:73-142) for R-L — no new loop detector.
  - fail-on-revert test (fleet/tests/reconcile-review-gate.test.sh): (a) a ≥hot-path change with no
    marker → R-J BLOCK, then add a matching-sha marker → GREEN; (b) marker with stale sha →
    R-K BLOCK; (c) an UNKNOWN src/charon/*.py path → classified hot-path (fail-closed) → requires
    review; revert the fail-closed default → the test goes RED (proving absence≠pass).
  - Cite the stass-allie WLS-7 validation (implement-as-pattern is the sanctioned hand-roll).
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
scope: |
  Rig-only (folds BLAST-TIER Consumer A). Does NOT depend on grades.py (grading consumer parked,
  §2.3 — not a circular dep). drift-primitive: content-hash/checksum + staleness-probe-TTL (KS29).
  No product change.
ds: |
  ## Dependencies & sequence
  Wave-1, no build prereq — the BLAST-TIER substrate is NOT built here (path-pattern fallback +
  fail-closed taxonomy land in this check). Independent of the other reconcilers (disjoint owns:;
  parallelizable). RECONCILE-WIRING depends_on THIS. Reuse ReviewerCircuitBreaker + the reviewed/
  marker convention; do not rebuild.
