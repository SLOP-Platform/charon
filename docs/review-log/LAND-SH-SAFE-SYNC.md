# LAND-SH-SAFE-SYNC — review fragment

## What landed
- `fleet/land.sh` — extracted step-7 base sync into `safe_sync_base()` with a hard
  data-loss invariant:
  - FAST-FORWARD ONLY (`merge --ff-only`); on divergence → abort loudly, never reset.
  - Clean tree on base → `checkout base && merge --ff-only origin/base`.
  - Dirty tree on base → SKIP sync, print the manual `stash -u && merge --ff-only && stash pop`
    command; the tree is NEVER touched.
  - Dirty tree off base → `git stash -u` → checkout base → FF → return → `stash pop`.
    A pop conflict leaves the work safe in `git stash` (message names the entry).
  - New `--sync-only <repo> <base> [branch]` entrypoint lets the test drive the
    real path without triggering the AUTONOMOUS lever or the full merge pipeline.
- `fleet/tests/test_land_safe_sync.sh` — 4 fail-on-revert cases (9 asserts):
  T1 dirty-on-base skip, T2 dirty-off-base stash→FF→pop, T3 clean FF, T4 divergence abort.
  Revert the guard → T1/T2 destroy the uncommitted tracked edit + untracked file → RED.

## Acceptance check
- 9/9 asserts PASS against the current `safe_sync_base`.
- "Never `reset --hard` / `clean -fd`" — verified by inspection (no such calls in
  the new path) and by T1/T2 (revert → RED).
- FF-only — verified by T4 (divergence → abort, ref unchanged).

## Open follow-up (separate ticket per ticket note)
- land.sh's auto-detected gate is weaker than CI; missed `arch-lint` on F29. The
  ticket allows folding "land.sh product gate == full CI" here OR a sibling
  ticket. NOT folded in this change to keep scope = safety fix; recommend a
  sibling ticket (`gate-land-vs-ci`) that introspects the repo's CI workflow
  files and runs the same checks land-side. Flagged for the manager.

## Adversarial review (rig-path)
- Stash-with-untracked label is `land-safe-sync ${branch:-$base}` — names the
  branch that triggered it, so `git stash list` is debuggable.
- Stash pop failure path is explicit and DOES NOT try a second `reset --hard`
  (the original bug). Worst case = work is safe in stash@{0}.
- Fetch failure is non-fatal (WARN + skip), not fatal — preserves work over
  sync correctness, which is the right trade for a rig-safety path.
- `set -uo pipefail` (no `-e`) so a fetch failure doesn't abort mid-flight
  and leave a half-checked-out tree.
