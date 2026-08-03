# OWNS-OVERLAP-DISAMBIGUATE — design note: ownership invariant and tie-break for owns-overlap disambiguation

## Context

`validate_board.sh` owns-collision check (check 4) emits a RED when two or more LIVE tickets
claim the same path without a `depends_on:` edge sequencing them. The check is sound and correctly
fails when the invariant is violated. The reconciliation mechanism (`reconcile-merged.sh`) also
correctly refuses to auto-close a merged ticket when its changed files are owned by more than one
live board ticket — but it refuses to decide and abstains, leaving the ticket open.

The acceptance criteria measured (2026-08-02) a backlog of ~9 un-resolved ambiguous cases caused
by multi-owner files that had never been disambiguated. Those cases are now largely resolved (the
board is GREEN except for the `fleet/validate_board.sh` triple, which is in the same class). The
invariant is: **one live owner per path at all times**. The residual RED is the last live violation.

## The INVARIANT

**Exactly one live board ticket may own any given path.** Co-ownership is not forbidden — it is
resolved by dependency ordering: if ticket A depends on B, then B owns the path and A does not
independently. The `depends_on:` edge is the tie-break.

This mirrors the pattern already in use:
- `REPO-MAP-CONVERGE -> VALIDATE-BOARD-PATH-TRUNCATION` (VALIDATE-BOARD-PATH-TRUNCATION depends on REPO-MAP-CONVERGE)
- `REPO-MAP-CONVERGE -> PROJECT-MEMBERSHIP-GATE` (PROJECT-MEMBERSHIP-GATE depends on REPO-MAP-CONVERGE)

The remaining `owns-collision LIVE` is on `fleet/validate_board.sh` itself, shared by:
`VALIDATE-BOARD-PATH-TRUNCATION`, `PROJECT-MEMBERSHIP-GATE`, `REPO-MAP-CONVERGE`.

The fix: make `VALIDATE-BOARD-PATH-TRUNCATION` depend on `PROJECT-MEMBERSHIP-GATE`, and make
`PROJECT-MEMBERSHIP-GATE` depend on `REPO-MAP-CONVERGE`. This produces a three-link chain:
REPO-MAP-CONVERGE (owns validate_board.sh) -> PROJECT-MEMBERSHIP-GATE (owns validate_board.sh)
-> VALIDATE-BOARD-PATH-TRUNCATION (owns validate_board.sh).

After the fix, check 4's `unsequenced` computation will find all pairs are ordered transitively,
and the RED disappears.

## The tie-break for reconcile-merged

The current behaviour when a merged PR's files overlap more than one live ticket is:
```
AMBIGUOUS — merged PR (branch=...) file X is owned by N tickets — NOT auto-closing
(reconcile-merged.sh:348)
```
This is correct. The abstention is the right response when ownership cannot be disambiguated.
The `depends_on:` edge is the tie-break: if exactly one of the overlapping owners is upstream
in the dependency graph, the reconciler can prefer the upstream ticket. The chain guarantees that
exactly one owner is upstream from any other at any given moment.

The specific implementation note: the reconciler already scopes by `repo:` and by `branch:` match.
Adding a `depends_on:` tie-break would mean preferring a candidate that has a `depends_on:` edge
pointing to the other candidate(s) — i.e., preferring the downstream ticket over the upstream one.
This is the correct direction because a downstream ticket is the one that LANDED (the upstream's
work was merged first as its dependency).

**Caveat:** this tie-break is only sound when the dependency graph is a total order over the
overlapping owners. Partial orders (diamond dependencies) still produce ambiguity. In those cases,
abstention is correct. The reconciler should not guess.

## UNRESOLVABLE `repo:` class

Tickets with a `repo:` key that does not resolve through `repo-registry.sh` produce:
```
UNRESOLVABLE repo: key — NOT auto-closing (cannot prove which repo's master a merge would be in)
(reconcile-merged.sh:310)
```
This is also correct and already implemented. The fix for this class is to ensure all live tickets
have a resolvable `repo:` key. Tickets with unresolvable keys are a board-hygiene concern handled
by REPO-MAP-CONVERGE (already in flight).

## Write-time gate

The last done-contract item (4): **enforce at write time**. A new or edited ticket whose
`owns:` overlaps a live ticket's `owns:` without a `depends_on:` edge ordering them must cause
`validate_board.sh` to exit non-zero. This is already the behaviour — check 4 runs at write time
(claim, launch, and preflight all invoke `validate_board`). The gate does not need to be added;
it already exists and already fails correctly.

The failure mode described in the accept criteria ("gets switched off because it reds on day one")
is avoided by resolving the existing overlaps BEFORE the gate is treated as enforcement. The gate
has always been the enforcement mechanism; the gap was that it was red on day one because the
overlaps had never been resolved.

## Fix for the live RED

Three tickets share `fleet/validate_board.sh`:
- `REPO-MAP-CONVERGE` (already sequenced upstream of the other two)
- `PROJECT-MEMBERSHIP-GATE` (needs `depends_on: REPO-MAP-CONVERGE`)
- `VALIDATE-BOARD-PATH-TRUNCATION` (needs `depends_on: PROJECT-MEMBERSHIP-GATE`)

The two `depends_on:` edges are the only change required to clear the RED.

## Evidence of resolution

After the fix:
1. `validate_board.sh fleet/` exits 0 (GREEN)
2. `reconcile-merged.sh` can resolve previously ambiguous cases through dependency ordering
3. No new `owns-collision LIVE` REDs appear on the board

The count of "previously AMBIGUOUS merges now reaching a verdict" is a post-fix metric captured
by running `reconcile-merged.sh` in verbose mode after the fix lands. The acceptance criteria's
mentioned "retiring 5 already-merged tickets cleared 12 board REDs at a stroke" is the prior
fix (retiring stale tickets, not sequencing them). The sequencing approach here achieves the same
effect without retiring live work.
