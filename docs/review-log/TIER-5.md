# Build-rig claim path: data-backed tier ranks (preserve `flock` atomicity)

_Wave C · branch `feat/fleet-tier-claim` · depends on the `charon tier` CLI work
(merged, `charon tier ranks`)._
_owns: the build rig's work-claim script (single file)._

## Goal

De-hardwire the work-claim script's tier ranking: source ranks from `charon tier ranks`
(canonical `low/med/high` + legacy aliases, alias-folded), with the legacy
`opus/sonnet/haiku` table as fallback. The `flock`/claim-create path is untouched.

## Design anchors (DTC §"Build-rig consumption — preserve `flock` atomicity, HARD REQ #5")

- **Parse ranks ONCE, BEFORE `flock 9`, into a bash assoc array.** `rank()` becomes a
  pure-bash array lookup (microseconds) inside the locked loop. NEVER spawn Python under
  the lock — that was Stance A's contention regression. The `charon tier ranks` call and
  the array fill happen above `exec 9>"$LOCK"; flock 9`, so the critical section adds zero
  subprocesses.
- **Exact pattern from the DTC**, adapted only for `set -u` safety (see below):

  ```bash
  declare -A RANK; nrank=0
  if out="$(charon tier ranks 2>/dev/null)"; then        # "low 1\nmed 2\nhigh 3\nopus 3 ..."
    while read -r n r; do [ -n "$n" ] && { RANK["$n"]=$r; nrank=$((nrank+1)); }; done <<<"$out"
  fi
  [ "$nrank" -gt 0 ] || RANK=([opus]=3 [sonnet]=2 [haiku]=1)   # legacy, unchanged
  rank(){ echo "${RANK[$1]:-0}"; }
  exec 9>"$LOCK"; flock 9                                  # atomic claim path UNTOUCHED
  ```

- **`flock 9` test-and-set and per-ticket `claims/$id` create are byte-for-byte unchanged**
  (the script's `flock` line ~17 and the `printf ... > "$STATE/claims/$id"` line). `tiers.json` (via
  `charon tier ranks`) is read-only/idempotent → no new lock, no race.
- **`meta tier` still reads the ticket's raw label**; tickets may say `high` or still
  `opus` — the rank map alias-folds both to rank 3, so gating works either way. The
  own/lower string-compare passes (`ttier = TIER`) are pre-existing and left untouched; my
  change only swaps the rank *function*, not the claim semantics.

## Deviations from the verbatim DTC snippet (and why)

1. **`nrank` counter instead of `else`-only fallback.** Under `set -euo pipefail` (the
   script's mode) a `declare -A RANK` with no assigned elements is still treated as *unset*
   by bash 5.2, so referencing `${#RANK[@]}` trips `unbound variable`. I avoid touching the
   empty array: a plain integer counter (`nrank`) decides the fallback, and the legacy table
   is assigned when `nrank == 0`. This also makes the fallback fire if `charon tier ranks`
   *succeeds but emits nothing* (a strictly more robust superset of the DTC's
   command-failure-only fallback). `rank()` uses `${RANK[$1]:-0}` whose `:-` default is
   `set -u`-safe.
2. **Blank-line guard `[ -n "$n" ]`** in the read loop — skips any trailing blank line in
   the command output so it can't create a `RANK[""]` entry.

## Verification (manual claim/release; lock + ranking intact)

- `bash -n` on the work-claim script is clean; `git diff` shows the **only** change is the `rank()` block — the
  `flock`/claims-create lines are unmodified.
- **Legacy path** (the currently-installed on-PATH `charon` predates the `tier` subcommand →
  `charon tier ranks` exits 2 → fallback): an opus worker drains own (`A-opus`) then lower
  (`B-haiku`); a haiku worker never claims the opus ticket; `own-only` mode does not drop to
  lower; `claims/$id` records + `lock` file written as before.
- **Data-backed path** (shimmed `charon` emitting the real
  `low 1 / med 2 / high 3 / opus 3 / …` rows): a `high` worker drains rank-3 tickets then
  spills to a `low` ticket; a `low` worker (rank 1) never claims a rank-3 (`high`/`opus`)
  ticket; an alias-named `opus` worker folds to rank 3 and claims a rank-3 ticket. Ranking
  drains own→lower correctly; the lock path is intact.

## Commit / ownership note

The work-claim script lives in the **private build-rig repo** (a single shared working tree,
not per-worker worktrees; in the same wave, the worker-launcher ticket edits the launcher
script in that same tree). To avoid an index-lock race with wave-mates I did **not** commit
into that shared tree — the
verified edit is left as a working-tree change for the launcher/manager to snapshot, per the
existing build-rig snapshot pattern. This per-ticket review fragment is the only file
committed on the `feat/fleet-tier-claim` charon branch. The build-rig does not ship with the
Charon product, so nothing here touches Charon source or its gate.
