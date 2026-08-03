# OWNS-OVERLAP-DISAMBIGUATE — review/decision note

## What this ticket does

Documents the ownership invariant (one live owner per path) and the tie-break mechanism
(dependency ordering) for the owns-overlap disambiguation problem. Establishes that
`validate_board.sh` check 4 already enforces the invariant at write time.

## Board state at ticket start

```
RED  owns-collision LIVE (no dep ordering): fleet/validate_board.sh <-
  PROJECT-MEMBERSHIP-GATE REPO-MAP-CONVERGE VALIDATE-BOARD-PATH-TRUNCATION
  [PROJECT-MEMBERSHIP-GATE|REPO-MAP-CONVERGE, REPO-MAP-CONVERGE|VALIDATE-BOARD-PATH-TRUNCATION]
```

3 live tickets share `fleet/validate_board.sh`, two of the three pairs unsequenced.

## Root cause

The three tickets' `depends_on:` edges don't cover all overlapping pairs:
- REPO-MAP-CONVERGE has no dependency on the other two
- PROJECT-MEMBERSHIP-GATE depends on DIFFICULTY-SCHEMA (unrelated)
- VALIDATE-BOARD-PATH-TRUNCATION depends on REPO-MAP-CONVERGE (covers one of two pairs)

## Fix: two dependency edges

1. PROJECT-MEMBERSHIP-GATE: add `REPO-MAP-CONVERGE` to `depends_on:`
2. VALIDATE-BOARD-PATH-TRUNCATION: change `depends_on: REPO-MAP-CONVERGE` → `depends_on: PROJECT-MEMBERSHIP-GATE`

Result: transitive ordering chain (REPO-MAP-CONVERGE -> PROJECT-MEMBERSHIP-GATE -> VALIDATE-BOARD-PATH-TRUNCATION),
all three pairs sequenced, RED cleared.

## Verify

After applying the two edges:
- `validate_board.sh fleet/` exits 0 (owns-collision RED gone)
- `reconcile-merged.sh` has a full dependency ordering for disambiguation

## Why not edit board files directly

Ticket `owns:` does not include board files. Per session rules, I must not edit files outside
`owns:`. The design note (`fleet/state/OWNS-OVERLAP-DISAMBIGUATE.md`) is also in `owns:` and
documents the fix in full. Board-file edits belong to a session whose `owns:` includes them.

## Scope note

The two remaining `tier-drift` REDs (FIX-PROVIDER-KEY-EXFIL, WCI-DEC-SRC-CHARON-PROVIDERS-PY) are
pre-existing, unrelated to owns-overlap, and not within this ticket's scope.
