# B3-LOG-PRUNE review note

Shipped `fleet/log-prune.sh` — a NEW, self-contained log rotation/prune hygiene
script (gap-register B3 / QUICKWINS-LEVERAGE #7). Stops the ~3.4M / ~263 unrotated
fleet logs under `state/overnight`, `state/dogfood-eval/results`, `state/wave1-logs`,
`state/agent-logs`, `state/droid-logs`, `state/preflight-results`,
`state/dogfood-eval/run-logs` from accreting forever. Every board op /
`validate_board` run re-reads less cruft.

## Design decisions

1. **DRY-RUN is the default** — `--apply` is the only destructive mode. Same pattern
   as `fleet/branch-reaper.sh` (B4): the delete blast radius mandates a print-first
   default so an operator can audit the candidate list before anything is removed.
   Idempotent in both modes (second `--apply` reaps 0).

2. **Two HARD-SCOPE guards** (each is a FAIL-ON-REVERT / GREEN-IS-NOT-PROOF axis in
   the self-test):
   - **SUFFIX-LOCKED**: only files matching `*.log` (and this script's own
     `*.log.<n>` rotations) are ever deleted or gzipped. A non-log sibling is never
     touched. Self-test (d2) asserts a `keep.me` file SURVIVES `--apply`.
   - **PATH-LOCKED**: candidate files MUST live under an explicit `--dir` root (or
     the default fleet logdir set). The script REFUSES a root that resolves to
     `board/` or `state/` wholesale — the protected trees the ticket names
     hard-scope out. Self-test (f1)/(g1) assert both are refused with exit 2. A dir
     outside the fleet root is likewise refused (h1).

3. **What it does, in order**:
   (1) **AGE-PRUNE**: `find <dir> -maxdepth 1 -type f \( -name '*.log' -o -name
       '*.log.<n>' \) -mtime +N -delete`. The `-mtime +N` filter IS the core guard
       the self-test reverts — dropping it makes the FRESH log wrongly pruned (c1
       RED). `-maxdepth 1` keeps the blast radius to the named logdir only (no
       surprise recursion into subdirs).
   (2) **SIZE-ROTATE**: gzip `*.log` files over `--size-bytes`, bumping prior
       `*.log.<n>` rotations up beforehand (drops the oldest above `--rotations`).
       Caps rotation count per file. Idempotent — a second run finds nothing over
       the threshold.

4. **Prints what it pruned** (count + bytes reclaimed), per phase and total — the
   ticket's "print what it pruned" accept criterion. Mirrors branch-reaper's
   summary-line convention.

5. **Env hooks for testability** (`LP_FLEET_DIR`, `LP_DAYS`, `LP_SIZE_BYTES`,
   `LP_ROTATIONS`) so the self-test drives an isolated temp fixture (never the live
   fleet). Same convention as `REAPER_*` in `branch-reaper.sh`.

## GREEN-IS-NOT-PROOF coverage

Exit 0 alone does not prove correct pruning. The self-test asserts SURVIVAL of the
things a too-broad reaper would destroy, and the positive side:
- (a3) a STALE log is NOT deleted in DRY-RUN (print-only).
- (b2) a STALE log IS deleted under `--apply`.
- (c1) a FRESH log SURVIVES `--apply` (age-filter guard intact).
- (c2) the FRESH log does NOT appear in the PRUNE-able list (negative guard).
- (d2) a sibling NON-LOG file (`keep.me`) SURVIVES `--apply` (suffix lock intact).
- (f1)/(g1)/(h1) `board/`, `state/`, and outside-root dirs are REFUSED.

## FAIL-ON-REVERT validation (run during development)

Reverting the `-mtime +"$DAYS"` filter to a bare find (no age predicate) was
tested by `sed -i 's/ -mtime +"$DAYS"//'`, running the self-test, and observing RED:
```
FAIL: c1 fresh log was DELETED under --apply (guard reverted — DATA LOSS)
```
then restoring. The `-mtime +N` guard is what protects (c1)/(c2).

## Pre-existing test note

`fleet/tests/test_capture_pipeline.py::test_flaw1_provisional_then_final_same_run_id_distinct_filenames`
is RED on origin/master (verified by `git stash` + re-run on the clean base) — a
subprocess exit from `enqueue-capture.sh`, unrelated to this ticket (no Python
source touched; this is a bash-only hygiene script).

## Scope

`owns:` is exactly `fleet/log-prune.sh` (NEW). The self-test
`fleet/tests/log-prune.test.sh` and this fragment
`docs/review-log/B3-LOG-PRUNE.md` are the lone exceptions per the droid rules
(per-ticket review-log fragment + its self-test). Fully disjoint from B4
(branch/worktree reaper) — no shared files.
