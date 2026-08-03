# PREFLIGHT-LATE-LEG-STARVATION — Review Log

## Problem
`reconcile-merged.sh` prints one line per merged PR. With hundreds of recent
merges, this floods stdout with hundreds of lines before the detector legs run.
A 200s-capped preflight never reached `detect_stranded_work` (line 884) or any
later leg. The cadence verdict was unreachable — a built-but-inert gate.

## Solution
1. **`_summarize_reconcile_merged()`**: runs `reconcile-merged.sh` once,
   collapses output to `{N} auto-closed, {N} ambiguous, {N} unresolvable` plus
   distinct shapes. Replaces hundreds of per-PR lines with one verdict line.
2. **`_summarize_reconcile_stale_claims()`**: same treatment.
3. **`show_leg_verdicts()`**: printed at the END of the dispatch regardless of
   upstream volume — an index pointing to each leg's verdict in the output.
   No leg can ever be starved by another's output.

## Decisions
- Ran `reconcile-merged.sh` exactly once in `_summarize_reconcile_merged` and
  stored the result in `_SUMM_MERGED_SUMMARY`. `show_leg_verdicts` reads the
  captured variable, not a re-execution (re-execution would mutate done state).
- The leg-verdicts summary is purely informational (references lines already
  printed) — it does not change exit codes.
- `ruff check fleet/preflight.sh` fires 2600 errors because it tries to parse
  bash as Python. `bash -n` confirms correct syntax. The codebase has no
  Python code in fleet/ so no lint tool is wired for shell files there.

## Fail-on-revert verification
With the fix reverted, the raw `bash reconcile-merged.sh` floods stdout before
the detectors, confirming the starvation. With the fix, `_summarize_reconcile_merged`
produces a compact 1-3 line summary regardless of merge volume.
