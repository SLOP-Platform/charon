# FN3-CURATION-PASS — review log

## Decision

Created an approval-gated curation pass (`curate.sh`) in
`~/build-rig/fleet/memory/`. Borrows the lifecycle-primitive
idea from mandalivia `/sleep`, Beads `bd compact`, and Cognee "forget" — a
scheduled/on-demand pass that DEDUPS near-identical notes, FLAGS conflicting
facts, and DECAYS unreferenced notes to archive/.

## Approach

- **DEDUP**: SHA-256 hash of normalised body (collapsed whitespace, lowercase).
  Same hash across multiple files → flagged for operator merge.

- **CONFLICT**: Same `name` frontmatter key but different body hashes →
  flagged for operator resolution.

- **STALE**: `last_referenced` frontmatter field compared against a threshold
  (default 30 days). Missing/malformed `last_referenced` also flagged. Stale
  notes are `--apply`-eligible for move to `archive/`.

- **Approval-gated**: NEVER silently deletes. Writes a PROPOSAL.md + TSV
  sidecar; operator inspects then runs `--apply` to execute moves.

- **--self-test flag**: Creates an in-memory fixture (1 duplicate + 1 stale
  note), runs curation, asserts both are flagged — FAIL-ON-REVERT gate.
  If the DEDUP or STALE logic were reverted, neither would be flagged (RED).

- **Consumes FN2's last_referenced**: The decay leg reads frontmatter
  `last_referenced`. Soft dep on bitemporal.py (uses frontmatter directly
  instead of BitemporalRecord — bitemporal.py is READ-ONLY; the curation
  pass never writes to it).

## Scope

- Owns: `~/build-rig/fleet/memory/curate.sh` (NEW + fixes)
- Self-test embedded as `--self-test` flag within curate.sh
- Review fragment: `docs/review-log/FN3-CURATION-PASS.md` (this file)

## Fail-on-revert

`curate.sh --self-test`:
1. Creates a fixture with two identical-body notes (dup-a.md, dup-b.md) and
   one stale note (stale.md, last_referenced=2025-01-01).
2. Runs curation against the fixture.
3. Asserts DEDUP and STALE are both flagged in PROPOSAL.md.
4. If either check were removed (e.g., no normalisation → different hashes
   for the same body; or stale-days threshold not respected) → the self-test
   fails (RED).

## Cross-reference

- FN1 (memory store): provides the markdown-with-frontmatter structure and
  `last_referenced` field that this pass consumes.
- FN2 (bitemporal decay): provides decay-weight semantics; curate.sh consumes
  `last_referenced` directly from frontmatter (read-only consumer).
- Together FN1 + FN2 + FN3 form a complete memory lifecycle: store → access
  tracking → curation.
