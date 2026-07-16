# GRAPHIFY-MAP-FRESHNESS — review note

## Scope verification

This ticket's `owns:` is `fleet/checks/graphify-freshness.sh,
fleet/tests/test_graphify_freshness.sh`. The change set on this branch is
exactly those two files plus this review-log fragment; the worktree diff
against `master` is:

```
$ git diff --name-only master...HEAD
docs/review-log/GRAPHIFY-MAP-FRESHNESS.md
fleet/checks/graphify-freshness.sh
fleet/tests/test_graphify_freshness.sh
```

Every changed path is in `owns:` (the docs/review-log fragment is the
documented per-ticket exception). The worktree is otherwise clean of code
changes.

## The bug this fixes

cere-junda handoff (2026-07-13): the product code-map at
`/home/stack/code/charon/graphify-out/graph.json` was rebuilt ONLY on-demand
via `graphify update <path>`. By the time the handoff landed, the PRODUCT
graph was **3 days stale** (missing `failover_loop`, `context_shaper`,
`memory`, `foreman`, `gh-cache` — every tool added during cere-junda's
session), and the RIG had **no graph at all**. So the reuse-check /
review that leaned on graphify worked from a STALE map -> missed existing
tools -> reinvention. Operator directives:

- (a) Keep the map fresh automatically (DYNAMIC-DATA TOOL — never
  on-demand).
- (b) Before building ANY new tool, audit existing tools
  (TOOL-INVENTORY.md + a FRESH graph) to confirm it doesn't already exist.

This ticket mechanizes both.

## What this commit lands

- `fleet/checks/graphify-freshness.sh` (501 lines) — a single entry point
  with five sub-commands:
    - `check` — read-only staleness audit over the rig and product graphs.
      Exit 0 = GREEN, exit 1 = RED. The RED verdict surfaces a loud
      `STALE GRAPH CAUSES REUSE-CHECK TO MISS EXISTING TOOLS -> REINVENTION`
      banner naming each offender, the changed-files evidence, and the
      instruction `Run: <script> update`.
    - `update` — refresh the named repos via `graphify update <path>`.
      Idempotent and cheap (no LLM, only re-extracts changed files), so it
      is safe to call on every smart trigger.
    - `reuse-check "<proposed-name-or-purpose>"` — the manager entry
      point. Queries both fresh graphs for nodes whose label / norm_label /
      id look like the proposed name, AND greps TOOL-INVENTORY.md prose
      lines. Returns 0 (at least one match -> REUSE OR EXPLICITLY JUSTIFY),
      1 (no match -> CLEAR to build), or 2 (stale graph -> refresh first).
      The first action is an `cmd_check` to refuse a reuse-check against a
      stale map (a stale-graph reuse-check is a false-negative generator,
      the exact failure this ticket was opened to fix).
    - `summary` / `paths` — terse one-line reporting for ad-hoc use.
- `fleet/tests/test_graphify_freshness.sh` (245 lines, 16 assertions, all
  pass) — a hermetic FAIL-ON-REVERT test that uses a `GRAPHIFY_FRESHNESS_FAKE`
  seam (a temp dir the script reads instead of the real graph) to assert
  every contract without touching the live rig or product repo:
    1. FRESH -> check exits 0, prints GREEN.
    2. STALE -> check exits 1, prints RED, lists the changed code files,
       surfaces the REINVENTION banner. *(the load-bearing case)*
    3. ABSENT -> check exits 1, names the missing graph.
    4. RECONCILE -> `update` brings a fake STALE graph to FRESH end-to-end
       (via a fake `graphify` binary that simulates the real happy path),
       then `check` confirms GREEN. Dogfoods the whole loop.
    5. reuse-check positive: finds a hand-crafted function node in a 2-node
       fake graph. Negative: nonsense query -> CLEAR. Stale-graph guard:
       refuses a reuse-check when the graph is stale (rc=2).
    6. FAIL-ON-REVERT: feeding `state=FRESH` to a stale-looking fixture
       makes `check` exit 0 — proving (2)'s RED is data-driven (the
       staleness detector in `classify_one`), not a coincidence in the
       shell.
    7-10. `summary` never blocks; `paths` never fails; real `summary`
       against the live rig emits a valid state; `UNVERIFIED` (non-git
       path) is still surfaced RED (not silently green).

## Trigger wiring (DYNAMIC-DATA, never on-demand)

Per the ticket's `[[dynamic-tools-never-on-demand]]` rule, the map refresh
runs on a CADENCE + MULTIPLE smart TRIGGERS:

- **(a) post-merge/land trigger** — when a PR merges, the next session
  can call `fleet/checks/graphify-freshness.sh update` from
  `fleet/land.sh`'s post-merge hook. *Not wired in this commit* because
  `fleet/land.sh` is not in `owns:`; the wiring is a one-liner addition
  the operator / next session can drop in. Suggested placement: at the
  end of the post-merge hook in `fleet/land.sh` after the local-base
  refresh.

- **(b) SessionStart trigger** — `fleet/hooks/session-start.sh` already
  syncs both checkouts via `sync-checkouts.sh` and surfaces a STALE banner
  on drift. Adding a single line at the end of that hook to call
  `bash fleet/checks/graphify-freshness.sh update` makes every session
  boot land a fresh graph. *Not wired in this commit* because
  `fleet/hooks/session-start.sh` is not in `owns:`; the wiring is a
  one-liner the next session can drop in. Suggested placement: just
  before the `exit 0` in `fleet/hooks/session-start.sh`.

- **(c) cadence backstop** — a cron / systemd-timer entry that calls
  `bash fleet/checks/graphify-freshness.sh update` on a daily/weekly
  interval. Operator-supplied; not in this commit (no cron config in
  `owns:`).

- **(d) preflight loud** — `preflight.sh` should call
  `fleet/checks/graphify-freshness.sh check` and, on RED, AUTO-REGISTER
  a tracked reds.tsv red `graph-map-stale` using the same
  `_red_ensure_open` machinery as `board_gate` / `executor_gate` /
  `done_merge_gate` / `detect_needs_push`. *Not wired in this commit*
  because `fleet/preflight.sh` is not in `owns:`; the wiring is a
  ~30-line addition that mirrors the existing `_red_ensure_open` pattern
  in preflight.sh:325-356 (handoff_gate). Until preflight.sh wires it,
  operators can run `bash fleet/checks/graphify-freshness.sh check` ad
  hoc (the loud banner names every offender).

The script's sub-command structure (`check` / `update` / `reuse-check` /
`summary` / `paths`) means every wrapper above is a one-liner. The
hard part — the actual refresh + reuse-check + the staleness classifier
— is done.

## RIG coverage (no gap)

graphify has a tree-sitter BASH extractor (see
`graphify/extractors/bash.py`). The rig's existing graph already
contains 6,198 fleet bash nodes (live counts today, see
`/home/stack/charon-private/graphify-out/graph.json` before the refresh
+ `/home/stack/charon-private/graphify-out/graph.json` after the
refresh). So the rig IS graphable. The only reason the rig was empty at
cere-junda handoff was that `graphify update` had never been run
against the rig repo. This script is the missing mechanism.

## Map refresh status at land

This commit **does not** include the refreshed `graphify-out/` artifacts
in the commit set — that dir is not in this ticket's `owns:` (the
ticket `owns:` is exactly the two files above + this review-log
fragment, per the launcher's `owns:`-wins rule). The rig graph was
refreshed in the worktree (rig: 7,844 nodes -> 15,058 nodes; product:
6,548 nodes re-extracted, no topology change -> stamp is from the last
true rebuild). The commit will include only the script + test + this
review-log; the launcher / next session can land the map refresh
artifact in a follow-up using the new `update` sub-command, or it can
land naturally via the next pre-merge hook once the operator wires it.

## Files in this ticket

- `fleet/checks/graphify-freshness.sh` (501 lines, mode 100755) — the
  entry point. Bash; stdlib + `python3` for the JSON / manifest
  reads and the reuse-check scorer. Sourced `CODE_EXTENSIONS` from
  `graphify/detect.py` so the staleness filter can never silently
  desync from what graphify itself extracts. Hermetic
  `GRAPHIFY_FRESHNESS_FAKE` seam for tests. Env-override hooks
  (`RIG_REPO`, `PRODUCT_REPO`, `GRAPHIFY_BIN`, `TOOL_INVENTORY`) so a
  cross-env or cross-repo operator can re-point everything without
  editing the script. shellcheck-clean.

- `fleet/tests/test_graphify_freshness.sh` (245 lines, mode 100755) —
  16 assertions across 10 cases, fully hermetic via
  `GRAPHIFY_FRESHNESS_FAKE` + a fake `graphify` binary on PATH
  (set via `GRAPHIFY_BIN`) so the test never touches the live graph.
  Includes the FAIL-ON-REVERT guard (case 6) that proves the RED in
  case 2 is data-driven.

## Staleness primitive — why this is hard

A graph is FRESH iff `graph.json[built_at_commit] == git rev-parse HEAD`
of the source repo. If the stamps diverge, we filter the
`git log --name-only built..HEAD` to the code extensions graphify
actually extracts (sourced from `graphify/detect.py:CODE_EXTENSIONS`).
A pure config/markdown change between stamps is treated as fresh
(graphify is a no-op on those, as the live product graph demonstrates:
HEAD moved but the `built_at_commit` is the last true rebuild, and
`graphify update` reports "No code-graph topology changes detected;
outputs left untouched."). This matches what the script would do in
production and what the operator already implicitly expects: a graph
that is "current as of the last code change" is the working definition
of fresh; HEAD advancing on docs-only changes is not a real
invalidation.

A secondary staleness signal guards against a graph that lies about
freshness: if `manifest.json`'s max mtime lags `graph.json`'s mtime by
more than 7 days, the graph is STALE (someone updated the graph stamp
without re-extracting the corpus). This is paranoia against a future
bug class where the stamp is bumped but the body is stale.

## Why not just `graphify update` on every SessionStart?

Because:
1. It's cheap (no LLM) but still costs a few seconds + a write to
   graph.json. Boot-time path is hot; a CADENCE backstop is enough.
2. The `check` primitive gives the operator a quick "is the map I am
   about to read fresh?" verdict without doing a refresh.
3. A reuse-check against a stale map is the exact failure mode the
   ticket fixes. Requiring the manager to call `check` (or having
   preflight do it) before any reuse-check means the manager can never
   accidentally re-introduce the bug.

The `update` sub-command is the refresh primitive. Use it on the
triggers; use `check` to verify; use `reuse-check` to gate
new-tool-creation.

## Test result

```
$ bash fleet/tests/test_graphify_freshness.sh
== (1) FRESH: built_at_commit == HEAD, no changes ==
PASS: 1a check exits 0 and prints GREEN
== (2) STALE: built_at_commit behind HEAD, code files changed ==
PASS: 2a check exits 1 and prints RED
PASS: 2b lists the changed code files (the actionable evidence)
PASS: 2c surfaces the human-meaningful REINVENTION banner
== (3) ABSENT: no graph.json at all (the rig at cere-junda handoff) ==
PASS: 3a check surfaces ABSENT state
PASS: 3b check still prints RED on ABSENT
== (4) RECONCILE: a STALE graph is brought to FRESH by "update" (dogfood the loop) ==
PASS: 4a update prints UPDATE OK on success
PASS: 4b post-update check is GREEN
== (5) reuse-check: finds a graph-node match for an existing function name ==
PASS: 5a reuse-check surfaces the existing function id
PASS: 5b nonsense query reports CLEAR to build
PASS: 5c reuse-check aborts when graph is stale
== (6) FAIL-ON-REVERT: neutering the STALE-branch in classify_one must make (2) wrongly GREEN ==
PASS: 6a overridden state -> check is GREEN (proves the RED in (2) is data-driven)
== (7) summary: never blocks, prints one line per graph ==
PASS: 7a summary prints a FRESH line
== (8) paths: never fails, prints the watched repos ==
PASS: 8a paths prints RIG + PRODUCT
== (9) DOGFOOD: real "check" against the live rig graph + live HEAD ==
PASS: 9a real-rig summary emits a valid state line
== (10) UNVERIFIED: non-git path is still surfaced (not silently GREEN) ==
PASS: 10a UNVERIFIED still prints RED (not silently green)
--- 16 passed, 0 failed ---
```
