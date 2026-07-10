# Adversarial review — BENCH-AGGREGATE-N (#16)

Branch `feat/bench-aggregate-n` @ da61356 · worktree `/home/stack/charon-private-wt-aggn` · READ-ONLY

## VERDICT: FIX (one minimal 2-line fix) — otherwise sound

Confidence: **high**. Aggregation math, invariant preservation, and the close_season
fold-in are correct and the revert-detection tests are real (verified empirically).
One real correctness bug in the tie-*ranking* logic (low blast radius: smoke chart only).

---

## Finding 1 (FIX) — non-transitive tie CHAINING collapses distinguishable models into one rank
`fleet/benchmark/lib/tier_chart.py:331-333`

Competition ranking compares each candidate only to the **immediately-preceding**
candidate (`prev = candidates[i-1]`). Statistical ties are non-transitive, so this
chains: with A~B and B~C but A≁C, all three inherit rank 1.

Empirically reproduced (3 models, all tier "Strong", each band ±4.53):
- A comp=89, B comp=82, C comp=76 → A-B gap 7 and B-C gap 6 are each within the
  combined band (~9), but A-C gap **13 > 9** → `_composites_tie(A,C)=False`.
- Yet `_rank_in_tier_v1_internal` returns **A=1, B=1, C=1, tied=True for all**.

So model C — genuinely weaker than A beyond the noise band — is reported rank-#1
"TIE" with A. This falsifies the module's own documented contract ("a sub-band gap
is a tie, not a rank"): here a *super-band* gap is rendered as a tie. The new
acceptance test only exercises a 2-model case (which is genuinely tied), so it does
not catch the 3-model chaining.

Blast radius is LOW: this is the DEMOTED smoke rank (synthetic S0–S6, human-facing
display in `render()` only). It does NOT feed capability grades or `assign()`
(`scores_tie` in grades.py is exposed but unused by assign; ties never affect tier —
tier is off the mean composite). Still a known-wrong result that contradicts the
stated invariant, so fix before merge.

**Minimal fix** — tie against the current tie-group LEADER, not the neighbour, so a
group can't drift past its own band:
```python
    ranks = []
    leader = None
    for i, c in enumerate(candidates):
        if i == 0:
            ranks.append(1); leader = candidates[0]
        elif _composites_tie(c["composite"], c["band"], leader["composite"], leader["band"]):
            ranks.append(ranks[-1])          # tie stays anchored to the group leader
        else:
            ranks.append(i + 1); leader = c  # new group starts
```
With this, the case above yields A=1, B=1, C=3 (C no longer spuriously tied to A).
Recommend also adding a 3-model chaining assertion to `aggregate_n_checks`.

---

## Verified OK

- **Tie/aggregation correctness (rest):** N=1 → band `None` (never faked 0), contributes
  0 to ties; `score=='-'` skipped; ties never affect tier (tier = mean composite),
  so a weaker model cannot be tie-lifted into a higher tier. Single-outlier band
  inflation is inherent to CI-on-stddev, acceptable.
- **Invariant preservation (concern 2):** grades.py aggregates over rows already gated
  by `real_only` (source ∈ {live}) AND `stage==active` (`_rows_for`, grades.py:349-351);
  tier_chart aggregates only `source=="bench"` + `_stage=="active"`. No synthetic/
  provisional leak into the live grade path.
- **Test adequacy / revert claim (concern 3):** REAL, not tautological. Simulated the
  last-wins revert: S1 mean 78.3→last-row 60 flips tier Strong→Capable, giving 4 genuine
  failures (score_n, score_mean, tier=="Strong", tied). Values differ, not just shape.
  Full capability selftest passes on-branch.
- **close_season fold-in (concern 4):** correct + inert. `_stage` reads col[15], lockstep
  with tier_chart; filter applied after the `<13` guard, before the bench2 filter. No
  bench2 provisional rows exist today, so behavior is unchanged.

## Out of scope / pre-existing
- `run_selftests.py` reports 4 S6 failures — all `Cannot find module .../node_modules/jsdom`
  (node grader env gap), unrelated to this Python diff. Pre-existing; not introduced here.
