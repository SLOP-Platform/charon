# Review: 411@charon-private
**PR:** chore(PREFLIGHT-LATE-LEG-STARVATION): launcher auto-commit — droid exited without committing (review for completeness)
**URL:** https://github.com/Nnyan/charon-private/pull/411
**Date:** 2026-08-02T15:17:18Z
**Reviewer:** reviewer-tab-2540602
**Author:** strong-2780982

## Verdict
NEEDS-REVISION

## Findings
- **CASE MISMATCH (critical):** `_sUMM_MERGED_SUMMARY` declared lowercase, assigned and read uppercase — the leg-verdicts table entry for `[reconcile-merged]` is always empty; the anti-starvation summary for this leg is silently broken.
- **RETURN CODE SWALLOWED (critical):** `_summarize_reconcile_merged` and `_summarize_reconcile_stale_claims` run their respective scripts without checking `$?`. On script failure (API error, permission error), they return 0 and print a false "clean" summary (0 closed, 0 ambiguous, 0 unresolvable), allowing the dispatch to proceed on potentially corrupted state.
- **SCOPE CONFLICT (process):** State file explicitly states `preflight.sh` is not owned by this ticket, yet the fix requires and commits changes to it. No ownership resolution or separate ticket exists.
- **FAIL-CLOSED pattern is too broad:** `grep -q 'FAIL-CLOSED'` without anchoring could flag PR descriptions/comments containing that substring rather than actual FAIL-CLOSED events.
- **grep-pipeline unquoted variables:** `printf '%s\n' "$line" | grep -q 'auto-closing WITH proof'` passes `$line` unquoted through the pipe; if `$line` contains whitespace or glob metacharacters, behavior is undefined.
- **Empty-shape deduplication bypass:** The `case` dedup check `*"$shape"*` will never match when `$shape` is empty (empty pattern `**` does not match empty string in bash `case`), so empty shapes from malformed input accumulate.
- **Trailing-line drop on grep -v:** If `reconcile-merged.sh` output has no trailing newline, the last non-blank line is silently discarded by `printf | grep -v`.

## Fail-on-revert check
The revert would lose the fix that prevents reconcile-merged.sh stdout flooding from starving late preflight legs, and would lose the `show_leg_verdicts` anti-starvation index.

## Status
Pending Manager dispensation
