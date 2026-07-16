# RECONCILE-HELD-MARKERS — Review Log

## Ticket
RECONCILE-HELD-MARKERS: backfill `merged:<sha>` proof on 33 HELD markers, repo-aware, batched.

## What was done
- **`fleet/reconcile-held-markers.sh`** (~180 lines): new script that backfills `merged:<sha>`
  onto `state/done/*` markers whose proof is missing or only PR-numbered. Idempotent, network-
  tolerant, batched (one `gh pr list` per distinct repo, not per marker). Default repo=charon
  for pre-`repo:`-schema tickets (the majority of the 33 HELD backlog).

- **`fleet/tests/reconcile-held-markers.test.sh`** (~190 lines, 13 tests): FAIL-ON-REVERT suite
  covering every backfill branch + the perf invariant (batched lookup, stub `gh` records
  invocations; assert == 2 for 2 repos and < 10 for 10 markers).

## Backfill branches (one per test)
- **(a)** HELD with date-only + merged PR in fixture -> backfilled; verify_merged passes OFFLINE
  (the local sha-ancestry path; the whole point of this script — local proof, no `gh` call).
- **(b)** HELD with date-only + NO merged PR -> UNCHANGED + listed in needs-action.
- **(c)** Already carries `merged:<sha>` -> UNCHANGED (idempotent guard).
- **(d)** Has `merged:#<pr>` (PR-number proof only) -> UPGRADED to `merged:<sha>` so future
  verify_merged takes the offline local path; today it falls to network which can rate-limit
  or be slow during a full-board sweep.
- **(e)** Unknown `repo:` (no slug map) -> UNCHANGED + listed; do NOT silently archive.
- **(f)** Batched lookup: 10 markers across 2 repos -> exactly 2 `gh pr list` calls (regression
  guard against the O(markers * network) antipattern that the perf-audit fixed in
  done.sh / reconcile-merged).
- **(g)** Orphan marker with NO board file at all -> processes without `set -u` error; lists
  with default `repo=charon branch=n/a`.

## Key decisions
- **HELD = "no local sha proof"** (date-only, empty, or `merged:#<pr>`), not strictly "what
  retire-done currently HELDs". This is a SUPERSET of retire-done's HELD set — markers retire-
  done can currently network-verify also get upgraded to local proof (faster + robust to
  rate-limits). The script is harmless on already-verified markers because the upgrade is
  a strict superset proof (`merged:<sha>` is stronger than `merged:#<pr>`).
  In production: 75 markers upgraded (16 PR-only + 59 empty with merged PRs), 28 still HELD
  (no merged PR found), 5 HELD per retire-done but unresolvable (short sha not in master;
  pre-existing issue, out of scope).

- **One `gh pr list --state merged` per distinct repo** (batched, not per-marker): mirrors the
  perf fix in `reconcile-merged.sh` and `done.sh`. Pre-group markers by `repo:` from board
  files; fan out one query per group; map (repo, branch) -> merge sha in memory.

- **`RECONCILE_HELD_DONE_DIR` / `RECONCILE_HELD_BOARD_DIR` env hooks**: let isolated tests
  target a fresh `state/done` and `board/` without shipping the live fleet/state. Mirrors
  the `RECONCILE_MERGED_SRC` / `DONE_CHARON_REPO` hook pattern used by sibling scripts.

- **`RECONCILE_HELD_DRY_RUN=1`**: prints what would be rewritten but writes nothing — for
  the operator eyeball pass before letting the script mutate real markers. Already used in
  the developer's acceptance test against the live state (75 backfills identified cleanly).

- **Network-tolerant by design** (no gh -> 0 backfills, all listed as needs-action, exit 0):
  preflight can call this safely; never blocks the gate.

- **`set -uo pipefail` + `repo=""` initialization** in the per-marker loop: needed because a
  marker with NO board file would leave `repo` unbound under `set -u`. The fix is one line
  and (g) asserts the regression doesn't return.

- **Per-repo slug map is explicit** (charon -> SLOP-Platform/charon, charon-private ->
  Nnyan/charon-private): adding a new repo is a deliberate, visible act. The accept criteria
  for RECONCILE-HELD-MARKERS pairs with DONE-SH-REPO-AWARE — both ship the same slug map and
  need to be kept in sync if a new repo is ever added.

## Open follow-ups (NOT in this ticket's scope)
- 5 markers (EVAL-GRADER-PROVISION, EVAL-LATENCY-GATE, EVAL-TAXONOMY-ALIGN, LEG-PREFLIGHT-
  CANARY, REVIEWER-DOGFOOD-REDS) carry a 7-char short sha (`merged:38af193` etc.) where the
  sha is NOT an ancestor of origin/master. Pre-existing; needs a separate "find the real sha
  for this short hash" fix (out of scope — done.sh's --merged-sha accepts a full 40-char
  sha, not a 7-char abbreviation).

- 1 marker (INC-401-FAILOVER) has a non-standard prose body ("done at 2026-07-08 ...");
  is_held_marker correctly classifies it as HELD; gh lookup returns no merged PR; listed
  as needs-action. Operator can decide override vs backfill-by-hand.
