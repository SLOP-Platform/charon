repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 1
branch: fix/auto-done-on-merge-miss
depends_on:
owns: fleet/reconcile-merged.sh, fleet/tests/auto-done-on-merge.test.sh
substrate: N/A
substrate-novel: |
  The rule is "a ticket whose PR is MERGED must not remain in `submitted`" — a reconciliation
  between OUR board's lifecycle states and GitHub PR state. No external tool models this board.
  The GitHub-side half (query merged PRs) is already served by the adopted `gh` CLI and
  `fleet/gh-cache.sh`; reuse them, do not re-implement PR querying.
serial_justified: |
  ONE reconciliation rule and its proof that it actually fires.
source: |
  Found 2026-07-31 (session tott-doneeta) — the OPERATOR spotted it, not the rig. After PR #289
  merged (9253547), ORPHAN-CLAIM-FORENSICS sat at `submitted` with an empty `done` marker. The
  manager had already reported "GATE 1 closed" on the strength of the merge.
note: |
  ## FACTS (verified 2026-07-31)
  - PR #289 merged at `9253547`; `fleet/state/submitted/ORPHAN-CLAIM-FORENSICS` = 2026-07-31T23:07:34Z
    and `fleet/state/done/ORPHAN-CLAIM-FORENSICS` = ABSENT.
  - **F2 `auto-done-on-merge` is marked ✅ Done on the roadmap** ("close tickets when PRs merge").
    It did not close this one. The ticket only reached `done` because a human noticed and the
    manager then ran `done.sh` by hand.
  - CLASS: **fake-green** (corpus #1, ~15 incidents) — a gate believed to work because it is
    marked Done, never observed actually firing. Compounded by self-report: the manager announced
    GATE 1 closed without checking the board state it claimed to have closed.

  ## THE REAL QUESTION (answer it before writing code)
  Do NOT assume the mechanism is broken and rewrite it. FIRST establish which of these is true:
    1. it never runs (no firing layer / not wired into a cadence),
    2. it runs but cannot see this case (e.g. only matches by `branch:`, and the PR merged under a
       different branch name, or it only scans certain states),
    3. it runs, sees it, and declines for a reason that is correct but silent.
  The fix differs completely per branch. `fleet/done.sh` ALREADY implements verified-close logic
  with four acceptance routes (--merged-sha ancestor / merged PR for `branch:` / merged PR
  touching `owns:` / explicit --override). If the gap is only that nothing CALLS it on a cadence,
  the fix is a wire, NOT new closing logic. Reuse `done.sh`; do not fork its verification.

  ## SCOPE
  - Determine and record which of 1/2/3 above is the actual cause, with evidence.
  - Close the gap at the narrowest point that fixes the CLASS.
  - **A ticket in `submitted` whose PR is merged must become `done` WITHOUT human noticing** — and
    if it cannot be auto-closed, it must be LOUD (surfaced by preflight/board), never silent.
    Silence is what let this one sit.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline (stub the gh surface — do NOT hit the live API in tests):
    a. ticket in `submitted` + its PR MERGED -> becomes `done` with merge-proof in the marker.
       Revert the wire and this goes RED (proves it FIRES, not merely that it exists).
    b. ticket in `submitted` + PR still OPEN -> stays `submitted`, untouched.
    c. ticket in `submitted` + PR merged under a DIFFERENT branch name than `branch:` -> still
       resolved (via the owns-touching route) or LOUDLY surfaced — never silently skipped.
    d. ANTI-OVER-BLOCK: a `claimed` ticket with no PR is untouched.
  Then run it against the real board and show what it closes or explains.

D&S — Deps & Sequence:
  - Depends on: nothing. Touches the reconcile surface, not land.sh.
  - Related: RECONCILE-BOARD-PR-DONE (DONE) covers adjacent ground — READ IT FIRST; this may be a
    gap IN that work rather than new work. If so, say so and re-scope rather than building twice.

## Scope correction (2026-08-01, saba-sebatyne)

The original `owns:` named `fleet/checks/reconcile-board-pr.sh` — a NEW 74-line file added by
PR #339. That file was a REINVENTION and it never fired: nothing invoked it, confirmed not by grep
but by the rig's own detector, `fleet/checks/reconcile-gate-wired.sh`, which reported
`R-G: DECLARED BUT NOT FIRED (built-but-inert) — RED — reconcile-board-pr.sh`. A ticket created to
fix built-but-inert work produced another instance of it.

The mechanism ALREADY EXISTED and was ALREADY WIRED: `fleet/reconcile-merged.sh`, invoked first in
every `preflight.sh` scan (:1033). #339 re-implemented a strictly weaker copy — single-repo,
GraphQL, no creation-PR guard, no ambiguity refusal.

ACTUAL ROOT CAUSE: `reconcile-merged.sh` was REPO-BLIND. `REPO_SLUG` was derived once from the
product checkout's origin (`SLOP-Platform/charon`), and the merged-PR query only ever asked that
repo. The board is multi-repo — **196 `repo: charon-private` tickets vs 75 product** — so every rig
ticket was structurally unreachable: its PR merges in `Nnyan/charon-private`, which the reconciler
never queried. Verified live: `Nnyan/charon-private#358` merged 19:31:39Z and was missed, requiring
a hand-written done marker. Contributing cause: an exhausted GraphQL quota rendered as `"clean"`
(fail-open).

Owns is therefore corrected to the file that actually needed fixing. `reconcile-board-pr.sh` is
REMOVED by this ticket, and the meta-gate is clean of it after removal.

Also fixed in passing — third sighting of this class today: `IFS=$'\t' read` COLLAPSES runs of
tabs (TAB is IFS-whitespace), so an empty column shifted `pr`/`slug` left and silently disabled
both fail-closed guards while looking correct. Rows now read on `\037`.

Corrected assumption: `_lib.sh`'s `verify_merged` is ALREADY repo-aware (H1/H2, 2026-07-18,
`VERIFY_MERGED_REPO` / `CHARON_FLEET_REPO` seams). The "hardcodes the product repo" warning that
circulates in handoffs is STALE — the fix relies on it rather than working around it.
