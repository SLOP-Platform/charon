# Adversarial review — BENCH-REGROUND-LIVE (branch feat/bench-reground-live @ 4f404c4)

Stance: try to break it. READ-ONLY. Scope: `capability/grades.py` + `benchmark/lib/tier_chart.py`.

## VERDICT: FIX

Logic is correct on today's data and nothing crashes, but the build's *headline behavior*
(synthetic rows no longer feed the grade) is **completely untested**, and the exclusion is
implemented fail-OPEN (deny-list) against the plan's fail-closed intent ("prefer source=live").
Two minimal fixes, then ship.

---

## Q1 — Blast radius (bench-only models → None): NO CRASH, graceful

Traced every caller. After the change, on the LIVE scorecard, three of five models
(`gpt-5.4`, `hy3-preview-or`, `kimi-k2.6`) have ONLY `source=bench` rows, so `grade()` returns
`None` for every work_class — including the generalist bucket, because `_rows_for(model, None)`
also excludes synthetic (grades.py:186-205). Only `glm-5.2` and `deepseek-v4-pro` (which have
`source=live` rows) keep a grade.

No consumer faults on this:
- `assign.py:111-113` — `g = grades.grade(m, wc); if g is None: continue` → graceful skip.
- `_sort_key` (assign.py:70-85) — `mean_bench_score`/cost/time None all defaulted (0.0/inf). Safe.
- `grade()` guards `n==0` by returning None *before* any division (grades.py:202-203); `mean()`
  only on non-empty lists. No divide-by-zero on zero live rows.
- Empty candidate pool → `eligible == []` → REFUSED "no eligible candidate" (assign.py:126-132). Safe.
- `tier_chart.py` reads bench rows directly (`bench_rows_for`, source=="bench"), untouched by the
  filter; changes are cosmetic labels only. No fault.

**But note the real-world magnitude (not a crash, worth an operator heads-up):** on the *current*
live data, for ci-infra / bugfix / refactor / frontend / greenfield there is NO real-outcome row
for ANY model, so `assign()` now REFUSES those work_classes outright. That is arguably correct per
the pivot thesis (no real evidence ⇒ no confident pick), but it is a large behavior swing shipped
with zero test and no note in the diff.

## Q2 — The seam: source=ticket treated as real-outcome — LATENT FAIL-OPEN

The change is a **deny-list** (`_SYNTHETIC_SOURCES = {"bench","bench2"}`, grades.py:110); *everything
else* — incl. `source=ticket` and any future value — is trusted as real-outcome. The plan (§0/§1/§7)
specifies the real signal as **`source=live`** and says "prefer source=live."

- Today: live data has only `bench` + `live` (no `ticket`), so the deny-list is *behaviorally*
  equivalent to `source==live`. **No actual leak on current data.**
- The risk is fail-OPEN by construction: plan §2 (line ~136) proposes `bench-prov`/`reds-prov` as a
  candidate encoding for #20 provisional rows. Those are NOT in `_SYNTHETIC_SOURCES`, so the moment
  such a row is appended it silently counts as trusted live evidence — the exact provisional-leak
  #20 exists to prevent. A trust filter should be an allow-list, not a deny-list.

## Q3 — Correctness of exclusion: COMPLETE, no residual leak

`grade()` sources all rows via `_rows_for(..., include_synthetic=False)`, so `score` (the rank key,
grades.py:214) and the whole grade are computed on real rows only. `mean_bench_score` is now
permanently `None` (the `bench_scores` comprehension at grades.py:217-218 filters `source in
_SYNTHETIC_SOURCES`, but those rows were already removed upstream), so the assign tiebreak on
`mean_bench_score` is inert — consistent with the demotion, not a leak. `all_models()` still lists
bench-only models but `grade()` returns None → skipped. No path re-admits synthetic into a grade.
(Minor: the `include_synthetic=True` branch is dead — no caller ever passes True.)

## Q4 — Test adequacy: THE core defect — re-grounding is UNTESTED

`capability/testdata/scorecard-fixture.tsv` is **100% `source=ticket` (21/21 rows)**. Since `ticket`
is not in `_SYNTHETIC_SOURCES`, `include_synthetic=False` excludes **zero** rows from the fixture.
Every `selftest.py` assertion therefore runs on the *identical* row set before and after this
change — the selftests exercise the untouched Wilson/composite math, **not the new filter**.

There is NO test that:
- puts a `source=bench`/`bench2` row in the fixture and asserts it is excluded from grade/score, or
- asserts a bench-only model yields `grade() is None` and is skipped by `assign()`.

Green here proves nothing about the demotion. For a rig whose own discipline is "proof-of-effect,
no inert wrappers" (selftest.py header), shipping the headline behavior unexercised is the inert-
change failure mode wearing a passing test.

---

## Minimal fixes required

1. **(mandatory) Test the demotion.** Add fixture coverage that actually exercises exclusion:
   (a) a `source=bench` (and `bench2`) row that must NOT change a model's grade/score; (b) a
   bench-only model that must yield `grade()==None` and be skipped by `assign()`. Then the green
   selftest means something.
2. **(should-fix) Make the filter fail-closed.** Prefer an allow-list of real-outcome sources
   (e.g. `{"live"}`, extended deliberately) over the `{bench,bench2}` deny-list — aligns with the
   plan's "prefer source=live" and prevents a future `bench-prov`/`reds-prov` (#20) row from silently
   leaking into live grades.

Optional: operator note that current live data now REFUSES most work_classes in `assign()`.

## Confidence
HIGH on Q4 (directly verified: fixture is all `source=ticket`; filter removes nothing → selftests
don't touch the new path) and on Q1 (no crash — every caller traced). MEDIUM-HIGH on Q2 fail-open
(no leak today; it's a latent/fragility call that also collides with the plan's own #20 encoding).
