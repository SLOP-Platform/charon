# PERF-AUDIT -- 2026-07-15

Systematic timing of fleet hot-loop scripts against growing board size.
Threshold: any path >5s or O(board-size) requires an index-once fix
(pattern: single pre-pass index + O(1) lookup, same as reconcile-merged.sh).

## claim.sh

**Pre-fix (origin/master): O(n^2) in board size.**
Hot loop re-scanned every board+archive file via per-file `meta()` awk-spawns
(3 per file per pass: parked / note / tier) and called `canon()` (also O(board))
for every `depends_on` dep. On a 1000-file fixture the "no claimable" worst case
took ~6-8s (already >5s threshold).

**Fix: index-once (PERF-AUDIT-CLAIM-DECOMPOSE).**
- ONE awk pass reads every board+archive file once, emitting a TSV row per ticket
  (file, id, tier, rank, parked, note, depends_on).
- State-id sets pre-collected into per-bucket newline-delimited files under the lock.
- Claim loop is a SINGLE awk over the sorted INDEX: integer compares + small set-file
  lookups. No bash-per-iteration overhead, no per-dep canon, no per-file `[ -e ]` fork.
- A `--dry-run` flag was added so timing can be measured without mutating live state.

**Measurements** (2000-file fixture, economy tier, both mode, no-claimable worst case):
  Pre-fix: ~13s (O(n^2))
  Post-fix: <0.3s

**Perf test:** `fleet/tests/test_claim_decompose_perf.sh` tests (b)-(d) assert
claim.sh on 200/1000/2000-file fixtures finishes well under 2s/5s thresholds.
Reverting the index-once fix re-introduces O(n^2) and flips the tests RED.

## decompose.sh

**Status: already fast (<0.3s for a 20-unit plan).**
decompose.sh is single-ticket-scoped (bounded by the plan, not the board size).
The bash wrapper is thin glue; the heavy work is in the product Python engine
(`decompose_surface.change_surface` + `decompose_planner.plan_decomposition`).
A `--dry-run` flag was added for non-mutating timing.

**Measurement** (20-unit plan, DEC_PLAN_CMD mock, driver validate+emit path):
  <0.3s

**Perf test:** `fleet/tests/test_claim_decompose_perf.sh` test (e) asserts
decompose.sh on a 20-unit plan finishes <2s (generous threshold for the
driver-only path). The test uses DEC_PLAN_CMD to mock the engine.

## reconcile-merged.sh

**Fixed earlier** (PERF-AUDIT.md reference in the file itself). Same index-once
pattern: single awk pre-pass for branch/owns indexes, O(1) lookup per PR.
