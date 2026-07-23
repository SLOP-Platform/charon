# CLAIM-LADDER-HEALTH review notes

## Decision: bash IFS delimiter for TSV

The initial implementation used tab (`\t`) as the field separator between awk and bash
`while read`, mirroring claim.sh's TSV format. This was silently broken: tab is an IFS
whitespace character, and bash collapses consecutive tabs into a single delimiter, so
empty fields (e.g. `parked=""`, `note=""`) were dropped and all subsequent fields shifted
by 2+ positions. Consequence: a ticket with no `parked:` and no `note:` was reported as
PARKED because the `read` placed `deps` into `parked` and `prio` into `note`.

**Fix:** changed the field separator from tab to pipe (`|`). Pipe is not IFS whitespace,
so consecutive `||` correctly produce empty fields. The sort command was updated from
`-t$'\t'` to `-t'|'` and the while-read uses `IFS='|'`.

## Decision: set -e failure in children computation

The `children=$(for cf in "$BOARD"/*.md; do ... done | wc -l)` pipeline failed under
`set -eo pipefail` because the `[ "$p" = "$id_lo" ]` inside the for loop returns 1 on
non-matching tickets — the normal case. With `pipefail`, the pipeline's exit code is the
for-loop's exit (1), and with `set -e`, the script exits.

**Fix:** added `|| true` at the end of the `[ ... ] && echo 1` (so non-match produces
exit 0 instead of 1) and `|| true` on `wc -l` (belt-and-suspenders). Also added explicit
`exit 0` at script end to suppress any lingering non-zero from the final `[ count -eq 0 ]`.

## Coverage

Every exclusion reason from claim.sh is surfaced:
- QUARANTINED (loop-guard marker with age/reason)
- CLAIMED (which droid + STALE flag if process is dead)
- SUBMITTED (marker timestamp + STALE flag if PR CLOSED/MERGED via gh)
- DONE
- PARKED (parked field or note: PARKED)
- BLOCKED (names each undone dep, flags claimed/submitted/mis-marked deps)
- TIER (ticket tier > checker tier)
- BOARD_RED (validate_board.sh failing blocks ALL claims)
- PARALLELIZABILITY-REFUSED (splittable + serial + unjustified)
