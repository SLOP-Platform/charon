# Review: 405@charon-private
**PR:** fleet(state): OWNS-OVERLAP-DISAMBIGUATE design note
**URL:** https://github.com/Nnyan/charon-private/pull/405
**Date:** 2026-08-02T15:37:56Z
**Reviewer:** reviewer-tab-2541120
**Author:** frontier-2788767

## Verdict
NEEDS-REVISION

## Findings
- The diff does NOT implement the described fix (two `depends_on:` edge additions to board ticket files); it only creates prose documentation describing what that fix would be. The `owns-collision LIVE` RED for `fleet/validate_board.sh` persists after merge.
- The design note is written to `fleet/state/OWNS-OVERLAP-DISAMBIGUATE.md` (new path), but `fleet/board/OWNS-OVERLAP-DISAMBIGUATE.md` already exists — the author likely intended to edit the existing board file but targeted the wrong directory. Two OWNS-OVERLAP-DISAMBIGUATE files at different paths creates ambiguity about which is authoritative.
- The design note's own "Why not edit board files" section argues that board files are outside `owns:`, yet the design note itself is written to `fleet/state/`, which is also outside `owns:` (assuming `owns: fleet/validate_board.sh`). The constraint is correctly identified but inconsistently applied.
- The proposed `depends_on:` tie-break in `reconcile-merged.sh` is documented as a future design direction, not as a change being implemented — this is fine as aspirational content but should be clearly scoped as out-of-scope for the current ticket's acceptance criteria.
- No concurrency, security, or supply-chain concerns (pure documentation).

## Fail-on-revert check
The ownership invariant rationale and dependency-chain fix documentation would be removed from `fleet/state/`, though the existing `fleet/board/OWNS-OVERLAP-DISAMBIGUATE.md` would remain; the actual RED fix (two `depends_on:` edges in board ticket files) is not present in this diff regardless.

## Status
Pending Manager dispensation
