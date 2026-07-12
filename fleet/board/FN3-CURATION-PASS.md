tier: economy
difficulty: 2
work_class: ci-infra
branch: feat/fn3-curation-pass
depends_on: FN1
owns: /home/stack/charon-private/fleet/memory/curate.sh
accept: |
  A scheduled/on-demand CURATION pass over the memory store (BORROW mandalivia `/sleep` + Beads `bd compact` +
  Cognee "forget"). It:
  - DEDUPS near-identical notes (content hash / embedding similarity),
  - FLAGS conflicting/contradicting facts for resolution,
  - DECAYS unreferenced-in-N-days notes to `archive/` (using FN2's last_referenced).
  APPROVAL-GATED: proposes edits/moves for operator approval — NEVER silently deletes.
  FAIL-ON-REVERT: a test fixture with one duplicate + one stale note → the pass flags the dup and proposes
  archiving the stale one; revert the logic → neither is flagged (red).
scope: Rig-only; approval-gated (no silent data loss). Runs on a cheap/local model or pure-heuristic where possible.
ds: After FN1 (needs the store). Independent of FN2 except it consumes FN2's last_referenced for the decay leg —
  soft dep, can stub. Owns a NEW file (`curate.sh`) → no owns-collision.
