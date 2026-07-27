# ADVREVIEW-SW-PHASE0-GRADE-READ — dd28aed

Reviewer: ganner-rhysode (deepseek-v4-pro), 2026-07-26

## Verdict: MERGE

The fix correctly unblocks the read path. The `fallback_admit` flag is set but
never consumed in the grading loop — a gap worth a follow-up but not blocking
because the contract only requires admission, not flagging.

## Findings

| # | Severity | File:line | What |
|---|----------|-----------|------|
| 1 | NIT | `fleet/capability/grades.py:561-564,656-659` | `fallback_admit` is dead code. `_control_panel_for()` sets it but `_rows_for()` (:656-659) only reads `split_ok`. The product's `grade_refs` calls `_is_fallback_admit` separately to set `EvalRow.flagged=True` on fallback-admitted rows; the rig has no equivalent. All 64 live rows are currently fallback-admitted (0 `strong-control` rows in the scorecard) but the operator cannot distinguish them from controlled grades. |
| 2 | SHOULD-FIX | `fleet/capability/grades.py:379-407` | The `Grade` dataclass has no field for provisional/fallback status. The product's `EvalRow.flagged` / `Flag` literal conveys this; the rig's `Grade` cannot. Follow-up: plumb `fallback_admit` from the panel into `_rows_for()` and surface it on `Grade`. |

## Verified by RUNNING

- **FAIL-ON-REVERT**: Reverting the admission predicate (`git checkout dd28aed^ -- grades.py`) → test fails with exit 1 (split_ok=False + KeyError on missing `fallback_admit`). Re-applying the fix → exit 0, ALL PASS.
- **NON-VACUOUS**: Empty scorecard (0 rows) → `grade("glm-5.2", "money-path")` returns `None`. Verified by test execution, not reading.
- **Real scorecard (RUN)**: `minimax-m3-free` gets `grade().n=21, score=69.07, merge_pct=100.0%`. `glm-5.2` gets `n=9, score=40.17`. Before the fix, both would return `None`.
- **assign.py (RUN)**: `assign.py --candidates minimax-m3-free,glm-5.2 --work-class rig-meta --tier med` returns a grade; without the fix, no candidate would have scorecard data.

## Verified by READING

- **Port faithfulness**: The rig's fallback (`pass_n==0 AND fail_n==0` → `split_ok=True`) is structurally equivalent to the product's `split_ok` + `_is_fallback_admit` (zero control rows → admit). Both use the same trigger condition. Divergence: the product separates "was this a fallback?" into a second function; the rig embeds both in `_control_panel_for`. The core admission logic is faithful.
- **Data touch**: `git diff dd28aed^..dd28aed --name-only` → `fleet/capability/grades.py`, `fleet/capability/tests/test_grades_no_control_admit.py`. `fleet/model-scorecard.tsv` is untouched. Scorecard ownership (`bench-grader:bench-grader`) unchanged.
- **Admit-too-much scenario**: A single MERGE/100 BLOCK/0 row on an uncontrolled ref (no controls seeded) would give that model a perfect grade. This is the acknowledged cost of the fallback — the product's docstring warns "caller SHOULD flag as provisional/uncontrolled." The rig currently doesn't flag.
- **Partial-control integrity**: Verified — 2 `strong-control` rows on a ref → `split_ok=False`, `fallback_admit=False`, rows excluded. The fallback ONLY triggers on zero-control, never on 1–2 controls.

## Exit codes observed (mine, not theirs)

| State | Exit | First failure |
|-------|------|---------------|
| `dd28aed` (fix applied) | 0 | — |
| `dd28aed^` (fix reverted) | 1 | `split_ok is True via no-control→admit fallback` — got `False` |

(End of report - total 44 lines)
