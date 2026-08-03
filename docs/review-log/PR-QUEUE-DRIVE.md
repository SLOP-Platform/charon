# PR-QUEUE-DRIVE — review/decision log, 2026-08-02

## What this lane did

Scanned all 25 open PRs on Nnyan/charon-private. Applied adversarial review to all
that passed CI (green checks or mergeable=clean), with the two defect-shape checks
from the ticket spec:
- Shape 1: grep diff for the mechanism any safety claim asserts
- Shape 2: run test suite with the change reverted

## Key findings

### #317 (CI_SUITES_CANARY) — BOUNCED, defect shape 1
The review-log claims "non-blocking canary" but `cmd_canary` (which returns 0 regardless
of suite failures) is NEVER CALLED from any CI workflow. `rig-ci.yml` invokes only
`syntax|board|suites|tests`. A non-blocking mechanism that never runs cannot make
any claim non-blocking. The safety property ("non-blocking") is asserted, not implemented.

### #334 (loop-guard reason wire) — BOUNCED, defect shape 2
`loop-guard-reason-wire.test.sh` mocks only `loop-guard.sh`, never `fleet-droid.sh`.
In the current branch, 3 of 6 call sites in `fleet-droid.sh` still lack `--reason`.
Suite passes identically on branch and with `fleet-droid.sh` reverted — it cannot
distinguish the fixed from unfixed state. Confirmed by running both ways.

### #360 (sync-opencode-models.sh) — BOUNCED, defect shape 1
`fleet/sync-opencode-models.sh:1` comment states "never force-pushes, never deletes
remotely, only writes to models/declared". Grep of the script for `force|push|delete|rm.*remote`
returns zero matches. The safety guarantee is prose.

### #346 (reviewer-tab-pool) — BOUNCED (BLOCKED-ON), known defects
`CHARON-AUTHOR-DROID:` marker has no producer. Measured 0 of 16 open PRs carry it.
B1 blocks all 16 PRs. Five defects from prior review remain (done marker on infra
failure, missing B1 in cmd_review, base64 regression, queue_gen unlocked, missing flock).
Producer needs to be in submit.sh/land.sh — outside this PR's scope.

### #371 (WLS-SPIKE) — BOUNCED (BLOCKED-ON), owns breach
`.gitignore` hunk adds `!fleet/state/judgment/` — that file is owned by
`MARKER-PROOF-MECHANIZE` (live p0). The hunk is also not load-bearing for this
PR (docs are already tracked in the branch). Secondary: `--push-only` stand-down in
`fleet-droid.sh:1729-1742` fires BEFORE bridge-connect, so it stands down on a bridge
it never attempted.

### #342 (EVAL-REGISTRY) — BOUNCED (BLOCKED-ON)
Aligned-row regression (drift reintroduced on rows already stamped `aligned`), zero
executed trials for new candidates, schema issues. Requires human operator.

### #343 (BRIDGE-MIGRATE-DROID-CLIENT) — BOUNCED (BLOCKED-ON)
Correct direction (2/7 proxy.py shellers migrated), but receive path calls an
opencode API endpoint that doesn't exist in the current session-ctl.sh surface.

## BLOCKED-ON PRs requiring human action

| PR | Blocker |
|----|---------|
| 320 | Eval-only, no wire — no action from this lane |
| 342 | Human operator needed (aligned-row regression, no trials) |
| 343 | opencode side fix (endpoint doesn't exist) |
| 346 | submit.sh/land.sh needs CHARON-AUTHOR-DROID producer |
| 371 | `.gitignore` owner conflict + `--push-only` stand-down order |

## LANDED without action

- #384 (board-hygiene): non-draft, mergeable=clean, just housekeeping
- #340 (gate-registry extraction): refactor, no safety claims, mergeable=clean
- #116 (ft-limits): old branch, mergeable=dirty, no conflicts with master
