# BENCHMARK-V2-REVIEW — adversarial audit of the v2 SCORING MATH

Reviewer role: adversarial, math-only. Read-only pass over
`BENCHMARK-V2-DESIGN.md` §4, grounded against `lib/grade_state.py`,
`lib/tier_chart.py`, `lib/sections.sh`, `model-scorecard.sh`, and the live
`model-scorecard.tsv`. No code changed, nothing pushed.

Verdict at bottom: **SHIP-WITH-FIXES** (two must-fix math defects; one is a
make-or-break design hole).

---

## The math as designed (restated to attack)

Per section S, per metric X∈{tokens,time,cost} (lower better):

```
percentile(M,S,X) = 100 * #{m≠M in F : value(m)>value(M)} / (|F|-1)
EFF_PCT           = Σ w[X]·percentile / Σ w[X]   over available X, w={3,2,1}
modifier          = (EFF_PCT-50)/50 * 5          ∈ [-5,+5]
adjusted          = clamp(raw + modifier, 0,100)
section_total     = min(adjusted,89) if capped-while-failing else adjusted
```

F = the set of `source=bench2` rows that have a non-`"-"` value of X for
section S. Composite = mean of section_total over S1..S6. Tier cuts
90/75/60/50 unchanged. v1 (`source=bench`) rows keep the old raw-mean formula.

---

## 1. Moving-field non-reproducibility — **HIGHEST-LEVERAGE, real defect, HIGH**

The percentile is defined relative to F, and **the design never freezes F.**
§7 spends a whole paragraph freezing the *section sample* per "season" so two
models are comparable — and then leaves the *efficiency percentile field*
completely unfrozen. This is the crux, and it is unresolved.

There are only two possible implementations and **both are broken**:

- **(a) Recompute live** (tier_chart/efficiency.py recomputes percentile over
  the current full field every time it renders): then a model's already-
  recorded score **changes retroactively** every time a later model joins the
  field. A model can move Strong→Frontier (or the reverse) *without being re-
  run*. Cross-time comparison and "a row means what it meant when written" both
  break. Non-reproducible.
- **(b) Freeze at append** (Phase 2 order in §8 — "call efficiency.py before
  `model-scorecard.sh append`" — implies this): the number is stable, but it
  was computed against whatever partial field existed *at that instant*. The
  first v2 model is judged against |F|=0–1; the tenth against |F|=9. Two rows
  both tagged `bench2`, both feeding the same tier ladder and the same
  `rank_in_tier` leaderboard, were scored **against different reference
  populations**. The number is frozen but its *meaning* is not — the worst of
  both worlds.

The design is silent on which of (a)/(b) it is, so it ships as whichever the
implementer happens to pick — a coin-flip between "scores mutate" and "scores
incomparable." Everything downstream (composite, tier, rank, and therefore the
build-model choice this benchmark exists to inform) inherits the defect.

**Concrete:** glm-5.2 (very cheap/fast in the live TSV) benchmarked first,
alone → |F|<2 → modifier 0 everywhere (§2). Five slower models run later.
Under (a) glm-5.2 now has a field, tops every metric, silently gains ≈+5 on
several sections → composite jumps a tier with zero new work. Under (b)
glm-5.2 is permanently frozen at 0 modifier while every later model gets the
full ±5 swing — penalized for running first.

**Fix (required):** freeze the efficiency field to the **same season** used
for section sampling (§7). EFF_PCT for a `bench2` row is computed once, against
the frozen set of models in that season, and is never recomputed later.
Models in different seasons are *not* placed in one percentile field, and the
leaderboard must segregate or label by season. State explicitly in §4.2 that F
is the season cohort, not "all bench2 rows ever."

## 2. Small-field degeneracy + a tie-percentile math error — **real defect, HIGH**

Two distinct problems compound here.

**2a. N is tiny in practice and the modifier is bipolar at small N.** With
|F|=2, the denominator |F|−1 = 1, so every per-metric percentile is exactly 0
or 100 — never intermediate. The "bounded gentle nudge" degenerates into a
full-swing ±(weighted) coin flip decided entirely by which of two models
happened to be faster/cheaper. First-ever model: modifier 0 (no field);
second model: full-swing. Identical correctness, opposite outcomes:

> A (first) S4 raw 87, no field → 87 → **Strong**.
> B (second) S4 raw 87, beats A on all three metrics → EFF_PCT 100 →
> +5 → 92 → **Frontier**.
> Same correctness (87). B outranks A on a Frontier label purely because A had
> the bad luck of an empty field. Run-order, not merit.

**2b. The tie formula does NOT center ties at 50 — it floors them at 0.** §4.2
claims "count strictly-worse only, so a 3-way tie all score the same mid
percentile." **False.** With strictly-worse-only, a 3-way tie has
#{strictly worse}=0 → percentile = 0, the *bottom*, not the *middle*. The
claim contradicts its own formula. Consequences:

- Two genuinely equal-efficiency models both get pulled toward −5, not left at
  0. Ties are penalized, not neutral.
- §4.3's flat-sub reasoning is wrong for the same reason: a field with
  *identical* cost (every model $0 on a flat-sub route) gets cost-percentile
  **0** for everyone, not 50. The doc says this "contributes zero
  differentiation, no special case needed" — but 0≠neutral. Same-for-everyone,
  yes, so relative ranking within that field is unchanged, but the *absolute*
  EFF_PCT is dragged down ≈ (1/6)·(50/50)·5 = **0.83 composite pts** for the
  whole field vs a field whose cost differentiates. Because the modifier is
  absolute and feeds an absolute tier cutoff, that shift is real, not cosmetic.

**Fix (required):** use a mid-rank percentile that centers ties/uniform fields
at 50: `percentile = 100·(#worse + 0.5·#tie_excluding_self)/(|F|−1)`, or the
Hazen/average-rank form. And set a **minimum field size** (recommend |F|≥4 or
≥5) below which the modifier is 0 for the whole section — N=2/3 percentiles are
too unstable to feed a tier decision. Fix the §4.2 comment to describe what the
formula actually does.

## 3. Missing-metric renormalization — **partly-mitigated, real residual, MEDIUM**

Renormalizing weights over *available* metrics keeps EFF_PCT in [0,100] and
does not systematically bias a token-less model higher or lower *in
expectation* — that part is sound. Two real residuals remain:

- **Different meaning, not different level.** tokens is the trustworthy axis
  the design wants to dominate (weight 3). A model that reports tokens is
  judged 50% on that axis; a model missing tokens is judged 100% on
  time+cost — the *less* trustworthy pair (cost is explicitly called routing-
  dependent). So two models get modifiers built from different metric sets and
  different meanings, then compete on one leaderboard. Comparability erosion,
  subtler than §1 but same family.
- **Transition reality bites the dominant axis first.** Per the design's own §2
  finding, tokens are *not captured yet* and even after Phase 1 are best-effort
  (`snapshot_usage() -> ... | None`). If early `bench2` rows carry `tokens="-"`,
  the tokens percentile field is empty → tokens drops out → weights renorm to
  time:cost 2:1 → early v2 efficiency is **cost-heavy**, i.e. dominated by the
  single least-trustworthy metric the whole design set out to de-emphasize.
  For the first season or two, v2 "efficiency" ≈ time+cost, the opposite of
  intent.
- **Cross-source contamination guard exists but is untested.** §4.2 correctly
  restricts F to `bench2` rows (v1 rows have no tokens and a shorter row, and
  must never share a percentile field). This is *specified* but there is **no
  self-test named** to enforce it, and `model-scorecard.sh` still has
  `VALID_SOURCE="live bench"` and `cmd_append` `$# -ge 12` — the `bench2`
  enum + tokens column are unbuilt, so nothing yet prevents an implementer from
  reading a mixed field. Add a golden asserting a v1 row never enters a v2
  percentile field.

**Fix:** gate v2 scoring on tokens actually being present for the field (if the
season's tokens field is empty, either don't ship v2 efficiency that season or
label it "time+cost only"); add the cross-source-isolation self-test.

## 4. ±5 magnitude vs correctness — **real defect at composite level, MEDIUM-HIGH**

Per-section the claim holds: ±5 can't carry a bad answer. But the tier decision
is on the **composite mean of 6 sections**, and there the full efficiency swing
is −5→+5 = **10 points**, which is wider than the gap between a mid-Strong and
Frontier. Worked inversion:

> Model P: true section-mean 87 (Strong), uniformly best efficiency → +5 →
> composite 92 → **Frontier, ranked above Q**.
> Model Q: true section-mean 91 (Frontier), uniformly worst efficiency → −5 →
> composite 86 → **Strong**.
> Q is genuinely *more correct* (91 vs 87) yet ranks below P. A 4-point
> correctness lead is overturned by the 10-point efficiency swing.

So efficiency **can** flip the tier ordering of two models whose correctness
differs by up to ~10 composite points. §4.4's "cannot manufacture a tier jump
on its own merit" is true per-section, false per-composite. This is exactly the
"subtly-wrong normalization misranks models → misleads build-model choice"
failure mode.

Note the v1 chart *already* uses efficiency the safe way: `rank_in_tier`
(tier_chart.py:145) tie-breaks **within** a tier by mean time_s, so a faster
model wins only at equal tier — efficiency never crosses a tier boundary. v2
abandons that safety by folding efficiency into the score itself.

**Fix (recommended):** either (i) shrink MODIFIER_MAX to ±3 (max composite
swing 6, still can flip a genuine coin-toss, much harder to overturn a real
correctness gap), and/or (ii) keep the v1 posture — apply efficiency only as an
explicit within-tier tie-breaker at near-equal correctness, not as a term added
to the score. (ii) preserves "correctness dominates" by construction.

## 5. Anti-cheat ordering — **cap holds; a correlated-gaming hole remains, MEDIUM**

The `min(score,89)`-after-modifier ordering is correct: a capped-while-failing
section with raw 88 +5 → 93 → min(93,89)=89, still barred from MERGE. Good, and
the timeout case (raw 0, worst percentile → −5, clamp 0) falls out right. No
objection to the ordering.

The residual is **not** ordering, it's **correlation**: efficiency rewards doing
*less* (fewer tokens = better tokens percentile), and the graders are
independently known-gameable (`GRADER-REVIEW.md` caught S2 scoring 100 on inert
code and S6 scoring 75 on a hardcoded solution). A model that slips a minimal
inert/hardcoded solution past a weak grader *also* burns the fewest tokens — so
it is **double-rewarded**: it passes the grader AND tops efficiency. Efficiency
is positively correlated with the grader's own blind spot rather than
independent of it, so it *amplifies* grader gaming instead of being orthogonal
to it. The modifier can also reward terseness over thoroughness inside the
passing band (a 92-correct terse solution → 97 can outrank a 95-correct thorough
one → 95).

**Fix:** gate the *positive* modifier behind `gate==pass AND score==100` (only
provably-fully-correct work earns an efficiency bonus; the penalty side can
still apply broadly), so "fewer tokens" can never be a reward for under-doing a
partially-graded task. Also reconsider whether cost belongs at all (see §6),
since $0-flat-sub cost is a routing artifact a model can "win" without being
efficient.

## 6. Tiering impact of mixing bench2 with v1 — **real defect, MEDIUM-HIGH**

Today `bench_rows_for` (tier_chart.py:72) and `rank_in_tier` (:136) filter
`source=="bench"`, so v2 rows are invisible until Phase 2 branches them — good,
they don't silently pollute the current chart. The defect appears **after**
Phase 2 if the leaderboard is allowed to mix:

- `rank_in_tier` builds one tier list. If it includes both `bench` (pure-
  correctness composite) and `bench2` (correctness ± up to 5 efficiency)
  models, a v2 model that reached Frontier on **87 correctness + 5 efficiency**
  is ranked *alongside and can outrank* a v1 model that reached Frontier on
  **≥90 pure correctness**. The operator reading "Frontier #1" cannot see that
  #1 got there on efficiency and is actually the *less correct* model — the
  exact mislead this benchmark must not produce.
- §4.5 asserts the label "doesn't get cheaper," then in the same paragraph
  concedes a v2 Frontier only needed to be "correct AND at-or-above-median
  efficiency." 87-correct is **not** 90-correct: the Frontier bar is lowered by
  up to 5 correctness points for v2 rows. The claim contradicts itself.

**Fix (required):** never rank/pivot `bench` and `bench2` composites in one
list. Segregate the leaderboard by source (and by season, per §1), and label
tiers with their formula ("Frontier·v2 (incl. efficiency)" vs "Frontier·v1").
If a single cross-formula ranking is ever wanted, rank on **raw correctness
composite** and show efficiency as a separate annotated column — do not let the
efficiency-adjusted number be the sort key across formulas.

---

## Single highest-leverage math risk

**§1 — the efficiency percentile field is never frozen.** It is the make-or-
break property the brief flagged, and the design leaves it undefined: the score
is relative to a field that grows over time, with no season-pin (even though §7
pins the section sample for exactly this reason). Depending on the unspecified
compute-timing it either mutates recorded scores retroactively (a) or freezes
each row against an inconsistent partial field (b). Compounded by the §2 tie
math error (percentiles floor at 0 instead of centering at 50) and small-N
bipolarity, the advertised "bounded, reproducible ±5 nudge" is in fact neither
bounded-in-meaning nor reproducible. Fix §1 (freeze the field to the season
cohort) and §2 (mid-rank percentile + minimum field size) and the rest of the
math becomes sound and shippable.

---

## VERDICT: SHIP-WITH-FIXES

Must-fix before any `bench2` row is written or ranked:
1. **§1** Freeze the efficiency percentile field to the season cohort; define
   compute-timing so scores are computed once and never mutate.
2. **§2** Mid-rank percentile that centers ties/uniform fields at 50; enforce a
   minimum field size (≥4) below which modifier=0.

Strongly recommended:
3. **§4** Shrink to ±3 or make efficiency a within-tier tie-breaker (v1 posture)
   so a real correctness gap can't be overturned at composite level.
4. **§6** Never mix `bench`/`bench2` (or cross-season) composites in one
   leaderboard; label tiers by formula.
5. **§5** Gate the positive modifier behind `score==100` so terseness can't
   reward under-doing a gameable grader; reconsider dropping cost entirely.
6. **§3** Add the cross-source-isolation self-test; don't ship token-weighted
   efficiency in a season whose tokens field is empty.

The skeleton (correctness-dominant, bounded, cap-after-modifier ordering) is
sound; the normalizer underneath it is not yet reproducible or tie-correct.
