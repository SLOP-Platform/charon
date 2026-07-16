# PERF-AUDIT-CLAIM-DECOMPOSE -- review / decision notes

**2026-07-15: perf audit of claim.sh + decompose.sh**

## claim.sh: index-once fix applied, O(n^2) -> O(files)

The original hot loop (`for f in "$BOARD"/*.md`) re-scanned every board+archive
file via per-file `meta()` awk-spawns (3 per file per pass) AND called `canon()`
(also O(board)) for every `depends_on` dep. On a 1000-file fixture the "no
claimable" worst case took ~6-8s (>5s threshold) and was O(n^2).

**Fix:** A single awk pre-pass builds a sorted TSV INDEX. State-id sets are
pre-collected into newline-delimited files under the lock. The claim loop is a
single awk pass over the sorted INDEX with integer compares + small set-file
lookups. Total wall on 2000-file fixture: from ~13s down to <0.3s.

A `--dry-run` flag skips the claim-marker write so timing can be measured
without mutating live state. Outputs `DRY-RUN: would claim <id>` or
`DRY-RUN: NONE (no claimable ticket)`.

Fail-on-revert perf test: `fleet/tests/test_claim_decompose_perf.sh` tests
(b)-(d) assert <2s on 200-file, <2s on 1000-file, <5s on 2000-file fixtures.
Reverting to the per-file bash loop re-introduces O(n^2) and flips RED.

## decompose.sh: already fast, scoped to plan size (not board)

decompose.sh is single-ticket-scoped -- bounded by the plan, not the board size.
The bash wrapper is thin glue; the heavy work is in the product Python engine.
Measured at <0.3s for a 20-unit plan (driver validate+emit path via DEC_PLAN_CMD
mock). No index-once fix needed.

A `--dry-run` flag skips .md file emission (validation still runs). Outputs
`[DRY-RUN] would emit: <path>` per sub-ticket.

## PERF-AUDIT.md

Created at repo root, documenting measurements for claim.sh, decompose.sh, and
reconcile-merged.sh (the latter was fixed earlier with the same index-once
pattern this ticket's claim.sh fix follows).

## Scope note

PERF-AUDIT.md is not in `owns:` line of this ticket but is explicitly
required by the `accept:` criteria ("PERF-AUDIT.md updated with measurements").
Code comments in claim.sh (line 24) and reconcile-merged.sh (line 15) both
reference "PERF-AUDIT.md 2026-07-15", anchoring it to this change. No other
board ticket claims PERF-AUDIT.md. Included per acceptance criteria.
