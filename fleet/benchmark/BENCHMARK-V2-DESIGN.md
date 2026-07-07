# BENCHMARK-V2-DESIGN — design/ADR for the model-benchmark harness, v2

Status: DESIGN ONLY — no harness code touched to produce this document.
Scope: `fleet/benchmark/` (this repo) — build-rig only, does not ship with
the Charon product (see `product-vs-build-rig-boundary` memory).
Author: design-first architect pass, 2026-07-06, grounded by reading
`bench.sh`, `run.sh`, `run-many.sh`, `lib/grade_state.py`, `lib/charon_cost.py`,
`lib/sections.sh`, `lib/tier_chart.py`, `model-scorecard.sh`,
`model-scorecard.tsv`, `README.md`, `GRADER-REVIEW.md`, `selftest/`, and the
live `runs/gpt-5.4/` + `runs/deepseek-v4-pro/` artifacts.

---

## 1. Findings — is the snapshot wiring real or leftover?

**Verdict: REAL, live, and currently in use. Not a one-off.** Both
`bench.sh` (current driver) and `run.sh` (legacy, still shares state)
write `runs/<model>/<section>/{worktree,meta.json}` as part of the normal
prepare→grade path, not as a side effect of some abandoned experiment.

**Exact code that writes it** — `bench.sh::prepare_section()` (identical
logic duplicated in `run.sh::prepare_section()`):

```bash
worktree="$(python3 "$STATE_PY" init "$model" "$section" "$timebox")"
rm -rf "$worktree"
mkdir -p "$worktree"
( cd "$fixture" && tar cf - --exclude node_modules --exclude dist --exclude __pycache__ --exclude .pytest_cache . ) \
  | ( cd "$worktree" && tar xf - )
```

`$STATE_PY init` is `lib/grade_state.py::cmd_init()`, which computes
`worktree = RUNS/model/section/worktree` and writes `meta.json` right next
to it (`state_dir()` → `RUNS / model / section`, `worktree = d / "worktree"`).
So every section a model attempts gets a real, fixture-derived, model-edited
working tree on disk, plus a `meta.json` that today already carries:

```json
{"model","section","start_ts","timebox_sec","attempts","finalized","worktree",
 "cost_start_usd","cost_method",
 "final_score","final_time_s","final_corrections","final_cost_usd"}
```

(verified against the live `runs/gpt-5.4/S3/meta.json` — real values, not
placeholders: `final_score: 75`, `final_time_s: 27.6`, `final_cost_usd:
"0.065585"`). The two populated model directories (`gpt-5.4`,
`deepseek-v4-pro`, dated 2026-07-06, matching today) are real completed
7-section runs whose rows are also present in `model-scorecard.tsv` —
confirmed end-to-end, not stale.

**What's genuinely missing (the real gap, not a fabricated one):**

1. **No per-run timestamping.** State is keyed by bare `model` name only
   (`RUNS/<model>/<section>/`). A second benchmark of `gpt-5.4` overwrites
   the first model's worktrees/meta.json in place — there is no run
   history, only "the last run for this model." v2's timestamped-run
   requirement is a real, unbuilt delta (§3 below), not something already
   done under a different name.
2. **The grader's own JSON output (`{"score","gate","reason"}`) is never
   saved to disk** — it's read once by `do_grade`/`grade_section`,
   projected into the TSV row, and discarded. Only the *derived* fields
   (`final_score`, `final_time_s`, etc.) survive in `meta.json`. Anything
   that wants to re-review a run later (the initiative judge, §5) needs
   this saved too.

## 2. Findings — where is time_s/cost_usd/corrections captured, and are tokens captured?

- **`time_s`**: `lib/grade_state.py::cmd_record()` — `elapsed = now -
  meta["start_ts"]`, wall-clock, computed fresh at every `grade` call.
  Real, deterministic, already correct.
- **`cost_usd`**: `lib/charon_cost.py::snapshot_cost_usd()` reads Charon
  gateway's `GET /charon/status` → `usage.cost_usd` (global cumulative) or,
  when `CHARON_BENCH_SESSION_ID` is wired, `GET /charon/cost?session=<id>`
  (isolated). `grade_state.cmd_init` snapshots it as `cost_start_usd`;
  `cmd_record` snapshots again and diffs via `charon_cost.delta_str()`.
  Real, but **best-effort and routing-dependent** — exactly why the
  operator wants tokens weighted above cost for v2 (a flat-sub route like
  NanoGPT reports ~$0 regardless of how much work the model actually did).
- **`corrections`**: `cmd_record`'s `attempts` counter, capped at
  `CORRECTIONS_CAP = 3`, incremented on every `gate != pass` round. Real.
- **Tokens: NOT captured today, despite being available in the same API
  response.** `charon_cost.py`'s own docstring says the gateway's
  `/charon/status` returns `{"usage": {"tokens_in", "tokens_out",
  "cost_usd"}}` (line 8) and `/charon/cost` returns `{"session",
  "tokens_in","tokens_out","cost_usd"}` (line 184's comment) — but
  `snapshot_cost_usd()` only ever pulls out `body["usage"]["cost_usd"]` /
  `body["cost_usd"]`; `tokens_in`/`tokens_out` are read off the same JSON
  body and thrown away. `grade_state.py` has no `tokens_start`/token-delta
  field anywhere, and `model-scorecard.tsv`'s schema (`README.md`'s
  "Ledger mapping" + the header comment in the TSV itself) has no `tokens`
  column at all. **This is a real, small, well-localized gap**: the data
  is one field away in an endpoint the harness already calls — no new
  network integration needed, just read two more keys and thread them
  through the same snapshot/diff/save path `cost_usd` already uses.

## 3. Findings — supporting context that shapes the design below

- **Composite today** (`lib/tier_chart.py` docstring + code): S0 is a
  pass/fail sanity gate, excluded from scoring. Composite = **unweighted
  mean of S1..S6's scores**. Tier ladder: Frontier ≥90, Strong 75-89,
  Capable 60-74, Basic 50-59, No Tier <50 (mirrors the per-section MERGE/
  FIXES/BLOCK bands, just splitting FIXES in two). Efficiency columns
  (`time_s`,`cost_usd`,`corrections`) are appended to the TSV and
  aggregated separately by `model-scorecard.sh render`'s "EFFICIENCY mean"
  block, but **never enter the score or the tier** — exactly as the task
  brief describes v1.
- **Anti-cheat cap**: if a section hits `CORRECTIONS_CAP` while still
  failing, `grade_state.cmd_record` hard-floors `final_score =
  min(score, 89)` — it can never land in MERGE. Any v2 scoring change
  MUST preserve this invariant (§4.1 below specifies exactly how).
- **A real adversarial grader-review process already exists and already
  found real bugs**: `GRADER-REVIEW.md` is a live Opus-reviewed audit of
  `graders/*` that caught S2 being gameable to a perfect 100 with fully
  inert code, and S6 scoring an inert/hardcoded solution 75 (FIXES) when
  it should BLOCK. This is precisely the review discipline the growing-
  library design (§6) needs to reuse for curating new candidate sections
  — it doesn't need to be invented, just pointed at new candidates too.
- **Self-test pattern already exists and generalizes cleanly**:
  `selftest/goldens/sN/{golden,inert,...}/` + `selftest/run_selftests.py`
  already implements "100-golden / 0-inert (+ named adversarial cases)"
  per grader — e.g. `s2/{golden,inert,dodge-mocked,inert-feature,
  hardcoded-honest-test}`, `s6/{golden,inert,scope-violation,
  inert-hardcoded,golden-vanilla,golden-svelte}`. This is the exact shape
  a new candidate section's self-test should be authored in (§6.2).
- **`model-scorecard.sh cmd_append`** currently hard-requires exactly the
  existing 12 positional fields (`$# -ge 12`, note absorbs the remainder)
  and validates `source` against `VALID_SOURCE="live bench"`. Any new
  column (tokens) or new source tag (`bench2`) is an additive schema
  change to this file, not a breaking one — `run-many.sh`'s own TSV reader
  already only reads `cols[:13]`, so appending a 14th column is safe for
  existing consumers.

---

## 4. ADR — benchmark-v2 scoring math

> **Revision note (2026-07-06):** this section is amended in place per
> `BENCHMARK-V2-REVIEW.md`'s adversarial pass (verdict: SHIP-WITH-FIXES).
> What the review confirmed sound is kept verbatim in spirit: efficiency
> stays **folded into the score** (not reverted to a pure within-tier
> tiebreak), the anti-cheat `min(...,89)`-**after**-modifier ordering is
> unchanged (§4.5, confirmed correct), and the `tokens:time:cost = 3:2:1`
> weighting is unchanged (§4.4). Four defects are closed below: the never-
> frozen field (§4.2, HIGH), the tie-floors-at-0 + small-N bipolar bug
> (§4.3, HIGH), the composite-level tier-flip (§4.6a, MED-HIGH), and
> bench2/v1 ladder mixing (§4.6b, MED-HIGH).

### 4.1 Design goal (restated precisely)

Correctness must **dominate**. Efficiency must be **bounded**, **relative
to the field** (not absolute — an 80s section isn't "slow" in the
abstract, only slow *relative to what other models did on that same
section*), and weighted **tokens > time > cost**, because cost is the
least trustworthy signal (routing-dependent; a flat-sub gateway route can
report near-$0 for a model that burned 5x the tokens of its peers). Two
more properties are now made explicit because the review showed the
original draft under-specified them: the field a model is judged against
must be **reproducible** (§4.2) — a recorded score must never change
value after the fact — and the fold-in must be **tier-safe at the
composite level** (§4.6a), not just per-section.

### 4.2 Season-frozen efficiency field (closes Review §1 — HIGH, make-or-break)

Reproducibility is the load-bearing property of this whole subsystem:
once a `bench2` row's `section_total` is written, it must never change
value again, *and* it must have been computed against a field that every
other model in the same cohort saw identically. The original draft left
this ambiguous between two options and the review showed **both are
broken**: recompute-live mutates already-recorded scores retroactively;
freeze-at-append compares different rows in the same field to
different-sized partial fields (frozen in *value*, not in *meaning*).
This revision picks a third option that satisfies both halves at once.

**The field = the season cohort, frozen at season close, computed once,
in one batch.** Reuse the season id §7 already defines for section-set
sampling (`2026-W28`-style calendar-week id) as the *same* partition key
for the efficiency field — one season, one section-set, one efficiency
field, by construction (§7 already guarantees every model benchmarked in
a season faces the identical section set, so "the field for section S in
season Y" and "the cohort of models benchmarked in season Y" are one and
the same set).

Mechanics:

1. **While the season is open**, a `bench2` row records `raw` (grader
   score — deterministic, immediate, unaffected by any of this),
   corrections/cap status, and the raw usage metrics (tokens/time/cost)
   the moment the section is graded, exactly as today. `section_total`
   and `modifier` are **not computed yet** — the row is written with
   `section_total: null, status: "provisional (season <id> open)"`.
   `tier_chart`/`model-scorecard render` display provisional `bench2`
   rows using `raw` alone, clearly labeled "provisional" — never a
   guessed or partial modifier.
2. **At season close** (the calendar boundary §7 already defines, e.g.
   week-end, or an explicit `bench.sh season close <season_id>` operator
   command for an early/manual close), a single batch job
   (`lib/close_season.py`) runs exactly once: it reads every `bench2` row
   tagged with that season id, and for each section `S` computes the
   cohort `C(S,season) = {models with a bench2 row for S in that season}`
   (identical set for every `S` in the season, per §7). It then computes
   `EFF_PCT`, `modifier`, and `section_total` for **every row in that
   cohort using that one snapshot**, writes them back, and flips `status`
   to `"final (season <id> closed <ts>)"`.
3. **After close, the season is immutable.** No later event — a new model
   joining a *new* season, a retroactive backfill, a re-render — ever
   recomputes a closed season's rows. A newly-run model always lands in
   whichever season is currently open; it can never join, and therefore
   can never perturb, a season that has already closed.
4. **Cross-season comparison is a separate, explicit concern**, not part
   of the scoring math: closed seasons each stay individually valid and
   individually reproducible; §4.6b defines how the tier ladder/
   leaderboard handles multiple seasons (never silently pooled into one
   field).

This directly resolves the (a)/(b) dilemma the review named: it is not
"recompute live" (a closed season's field is never touched again), and it
is not "freeze at partial append" (every model in the cohort is scored
against the exact same, *complete* cohort — nobody is compared to a field
a fraction the size of what a later model in the same season sees).

**Bootstrap case:** the first-ever `bench2` season has no prior seasons to
compare against — that's fine, and not a special case: it closes with
whatever cohort ran during it, same as any other season. If that first
cohort is small (see §4.3b), the modifier is 0 for everyone in it — a
plain, principled "not enough data yet" outcome, not an error.

### 4.3 Per-section, per-metric percentile — mid-rank ties + minimum field size (closes Review §2 — HIGH)

**4.3a — mid-rank (average-rank) percentile: ties centered at 50, not floored at 0.**

For section `S`, metric `X ∈ {tokens, time_s, cost_usd}` (lower always
better), cohort `C(S,season)` (§4.2), model `M`:

```
worse(M)          = #{ m in C, m != M : value(m,S,X) > value(M,S,X) }
tie(M)            = #{ m in C, m != M : value(m,S,X) == value(M,S,X) }
percentile(M,S,X) = 100 * (worse(M) + 0.5 * tie(M)) / (|C| - 1)
```

(A `"-"`/missing value for `X` still excludes that model from that
metric's sub-field — that rule was not defective and is unchanged.)

This is the standard mid-rank/Hazen-style percentile: a model with nobody
strictly worse and everybody tied lands at exactly **50** (the middle),
not 0 (the bottom) — the property the original draft's prose *claimed*
("a 3-way tie all score the same mid percentile") but the strictly-
worse-only formula did not actually deliver (worked example 4.7b).

**4.3b — minimum field size gates the modifier, not just the percentile shape.**

```
MIN_FIELD_SIZE = 4
if |C(S,season)| < MIN_FIELD_SIZE:
    modifier(M,S) = 0   for every M in C     # cohort too small to rank; efficiency neutral
```

Below 4 models a percentile is either undefined (`|C|<2`) or a full-swing
coin flip (`|C|=2` → denominator 1 → every result is exactly 0 or 100;
`|C|=3` → only {0,50,100} are reachable) — not stable enough to move a
tier decision. Because §4.2 computes a whole season in one batch at
close, this is a single cohort-level gate applied once per season (every
section in a season shares one cohort size, per §7), not a per-model,
per-metric special case layered on top.

### 4.4 Weighted efficiency percentile (tokens > time > cost) — mechanics unchanged, now fed by §4.3

```
weights = {tokens: 3, time: 2, cost: 1}
available = {X in weights : percentile(M,S,X) is defined}
EFF_PCT(M,S) = sum(weights[X] * percentile(M,S,X) for X in available)
               ------------------------------------------------------
               sum(weights[X] for X in available)
```

Renormalizing over *available* metrics is unchanged and remains sound
(fair to routes where `cost_usd` is structurally unavailable). The one
thing the review found wrong here — that an identical-for-everyone value
(flat-sub `$0` cost) was being scored 0 ("contributes zero
differentiation" was true, but 0 is not neutral) — is now closed as a
direct consequence of §4.3a's mid-rank fix, not a separate special case:
an all-tied field gives every model `tie(M) = |C|-1`, `worse(M) = 0`, so
`percentile = 100 * 0.5*(|C|-1) / (|C|-1) = 50` for everyone — neutral,
as it should be (worked example 4.7b). If **no** metric is available at
all, `EFF_PCT` is undefined and the modifier (§4.5) is 0.

### 4.5 Bounded per-section modifier + anti-cheat ordering — confirmed sound, unchanged

```
MODIFIER_MAX = 5          # points, out of a 0-100 section score
modifier(M,S) = 0                                        if EFF_PCT undefined or MIN_FIELD_SIZE not met
modifier(M,S) = (EFF_PCT(M,S) - 50) / 50 * MODIFIER_MAX  otherwise
```

Centers at the field median (modifier 0 for an average-efficiency model)
and is linear out to ±5 at the 0th/100th percentile — kept exactly as
originally designed; the review raised no defect in the per-section
magnitude, only in what it does at the composite level (§4.6a).

**Ordering with the anti-cheat cap is unchanged and the review confirmed
it correct**: the correction-round cap (`min(score, 89)` when
`CORRECTIONS_CAP` is hit while still failing) is applied **after** the
modifier:

```
raw = grader_score                                   # from grader JSON, 0-100
adjusted = clamp(raw + modifier(M,S), 0, 100)
section_total(M,S) = min(adjusted, 89)  if this section hit the corrections cap while still failing
                    = adjusted          otherwise
```

A timed-out section scores `raw = 0`; it also naturally gets the field's
worst `time_s` (percentile ≈ 0), so `modifier ≈ -5`, and
`clamp(0 - 5, 0, 100) = 0` — falls out correctly with no special case.

### 4.6 Composite: capped aggregate + strict source/season segregation

Two independent fixes live here: (a) a composite-level magnitude cap so
efficiency cannot flip a real correctness gap into a tier inversion, and
(b) a hard partition so `bench2` and `bench` (and different `bench2`
seasons) are never ranked in one merged ladder.

**4.6a — composite efficiency contribution is capped separately from the per-section modifier (closes Review §4 — MED-HIGH).**

Per-section `MODIFIER_MAX` stays ±5 (§4.5, unchanged — well-calibrated
against the FIXES band, and the review found no defect in it *per
section*). The composite is where a tier decision actually gets made, so
it gets its own, independent, smaller cap on the aggregate effect:

```
section_correctness(M,S) = min(raw,89) if capped-while-failing else raw   # pure correctness, no modifier
composite_raw(M)         = mean(section_correctness(M,S) for S in 1..6)   # = the v1 formula, applied to v2 data

composite_eff_delta(M)          = mean(section_total(M,S) - section_correctness(M,S) for S in 1..6)
COMPOSITE_EFF_CAP               = 2
composite_eff_delta_clamped(M)  = clamp(composite_eff_delta(M), -COMPOSITE_EFF_CAP, +COMPOSITE_EFF_CAP)

composite_final(M) = composite_raw(M) + composite_eff_delta_clamped(M)
```

Tier is read off `composite_final` using the unchanged cuts (90/75/60/50).

**Why cap the composite delta rather than shrink `MODIFIER_MAX` itself**
(the review's alternative suggestion): shrinking the per-section cap only
achieves the same worst-case composite bound if every section swings the
same direction at the same extreme, and it flattens a legitimate,
already-justified per-section signal every time (a single section where a
model burned 5x the field's tokens becomes less visible in the per-
section table even when that's exactly the kind of outlier the table
should show). Capping the *composite delta* directly leaves per-section
detail untouched and adds one new, independently provable invariant at
the exact point a tier gets decided.

**The guaranteed property:** for any two models `P, Q`, `composite_final`
can invert their `composite_raw` ordering only if
`|composite_raw(P) - composite_raw(Q)| < 2 * COMPOSITE_EFF_CAP = 4`. A
real correctness gap of 4 or more composite points can never be
overturned by efficiency; gaps smaller than that are exactly the
"near-tie correctness" band where letting efficiency decide the tier is
the intended, desired behavior — that is what "efficiency still matters"
means under this cap (worked examples 4.7c).

**4.6b — `source` (and, for `bench2`, `season`) is a hard partition key everywhere a ranking or ladder is produced (closes Review §6 — MED-HIGH).**

The original draft tagged v2 rows `source=bench2` and kept the raw-mean
v1 formula for `source=bench`, but only guarded row-*append* — the review
found the *consuming* code (`rank_in_tier`, any future pivot/leaderboard)
was never told the partition must hold all the way through to display.
This revision makes it load-bearing everywhere, not just at write time:

- **Percentile fields (§4.2/4.3):** `C(S,season)` is `source=bench2`-only
  by construction (a `bench` row has no season, no tokens column, and
  cannot be a cohort member) — stated here as a hard filter, not an
  incidental consequence.
- **`rank_in_tier(models, source, season=None)`** takes an explicit
  partition argument and only ever ranks within it. `source=bench` needs
  no `season` (v1 has none); `source=bench2` requires one. There is no
  code path that calls it with a mixed-source or mixed-season list.
- **Tier cuts (90/75/60/50) stay numerically identical** for every
  source/season — "Frontier" is the same bar everywhere — but the two
  formulas are **never rendered as one merged, sorted list**. Every
  render is labeled by formula and, for `bench2`, by season:
  `Frontier · v1` vs `Frontier · v2 (2026-W28)`. A model benchmarked
  under both appears in both labeled panels, never collapsed into one
  cross-formula rank (worked example 4.7d).
- **A single side-by-side comparison view**, if ever wanted ("how does
  this v2 model compare to the v1 field"), must sort on `composite_raw`
  (pure correctness, comparable across both formulas) and print
  `composite_final`/efficiency as an adjacent annotated column — the
  efficiency-adjusted number is never the cross-formula sort key.
- **Self-test to add** (closes the review's "specified but untested"
  note): a golden asserting `rank_in_tier` raises if handed a mixed-
  `source` or mixed-`season` list, and asserting `lib/close_season.py`
  never admits a `source=bench` row into a `bench2` cohort.

### 4.7 Worked examples (one per closed finding)

**4.7a — season freeze / reproducibility (§4.2).** Season `2026-W28`:
`glm-5.2` finishes S4 Monday (`raw=85`), `gpt-5.4` finishes Wednesday
(`raw=90`), `deepseek-v4-pro` finishes Saturday (`raw=87`). All three show
`status: provisional` all week — `raw`-only, no tier. At season close
(Sunday) the batch computes the cohort `C(S4,W28)={glm-5.2, gpt-5.4,
deepseek-v4-pro}`, size 3 < `MIN_FIELD_SIZE`(4) → `modifier=0` for all
three, `section_total=raw`, status flips to `final`, permanently. The
following week, season `2026-W29` opens; a 4th model runs S4 with
excellent efficiency. **None of W28's three scores change** — W29 is a
different, disjoint cohort/field from the start, so there is nothing to
retroactively mutate. This is the reproducibility guarantee stated
explicitly: a recorded `bench2` score is a fact about one closed season,
never revisited by anything that happens afterward.

**4.7b — mid-rank ties + minimum field (§4.3, §4.4).** Season with a
5-model cohort (meets `MIN_FIELD_SIZE`), `cost_usd`: A=$0.02, B=$0.05,
C=$0.05, D=$0.05 (three-way tie B/C/D), E=$0.09. For B:
`worse={E}=1, tie={C,D}=2` → `percentile = 100*(1+0.5*2)/4 = 50` — the
tie lands at the *middle*, matching the design's original (previously
false) claim. For A (uniquely best): `worse=4,tie=0` → 100. For E
(uniquely worst): `worse=0,tie=0` → 0. **Flat-sub case**: a 4-model
cohort all report `cost_usd=$0` (flat-sub route) → every model has
`worse=0, tie=3` → `percentile = 100*0.5*3/3 = 50` for all four — neutral,
not the old formula's 0-for-everyone drag. **Small-N case**: cohort of 2
(`glm-5.2` alone first, a faster/cheaper model joins the same season
before close) → `|C|=2 < 4` → `modifier=0` for *both*, regardless of who
is faster — no run-order coin flip, closing the review's exact
"penalized for running first" example.

**4.7c — composite cap (§4.6a).** `P`: `composite_raw=87` (Strong),
efficiency uniformly excellent (every section modifier `+5`) →
`composite_eff_delta=+5` → clamped to `+2` → `composite_final=89` (still
Strong, not Frontier). `Q`: `composite_raw=91` (Frontier), efficiency
uniformly worst (every section modifier `-5`) → `delta=-5` → clamped to
`-2` → `composite_final=89`. Result: **P and Q tie at 89 — Q never ranks
below P**, proving the required property for a 4-point correctness gap
(the worst case the cap guarantees against). Efficiency still matters for
closer gaps: two models both at `composite_raw=88.5` (a genuine near-tie,
gap 0) — one gets `delta=+2` (clamped from a true +5) → `final=90.5` →
**Frontier**; the other gets `delta=-1` (under the cap, unclamped) →
`final=87.5` → **Strong**. Same correctness, efficiency decides — exactly
the "order within a band, don't cross a boundary on a real gap" behavior
requested.

**4.7d — source/season segregation (§4.6b).** A `bench2` model closes
season `2026-W28` at `composite_raw=88`, `composite_eff_delta_clamped=+2`
→ `composite_final=90` → crosses into Frontier legitimately under §4.6a's
rules. A `bench` (v1) model elsewhere has `composite=90` under the pure
v1 formula. Both are genuinely "Frontier" under their own formula's rules
— and both are displayed in **separate, labeled panels** (`Frontier · v2
(2026-W28)` and `Frontier · v1`), never merged into one sorted list, so
an operator glancing at "Frontier" never mistakes a 90-via-efficiency v2
row for a 90-pure-correctness v1 row without the label making the
difference explicit.

### 4.8 CLOSED table

| # | Review finding (severity) | Fix applied | Where |
|---|---|---|---|
| 1 | Efficiency field never frozen; scores mutate retroactively or freeze against a partial field (HIGH) | Field = season cohort, computed once in a single batch at season close (`lib/close_season.py`); provisional-until-close; closed seasons immutable forever | §4.2, example 4.7a |
| 2 | Tie percentile floors at 0 instead of 50; `\|F\|=2` is a run-order coin flip | Mid-rank percentile (`worse + 0.5·tie`) centers ties/flat fields at 50; `MIN_FIELD_SIZE=4` zeroes the modifier below that cohort size | §4.3, §4.4, example 4.7b |
| 3 | ±5 per-section modifier can flip a composite tier decision across a real correctness gap (MED-HIGH) | New `COMPOSITE_EFF_CAP=±2` on the aggregate delta only (per-section ±5 untouched); provably cannot invert a ≥4-point correctness gap | §4.6a, example 4.7c |
| 4 | bench2 (correctness+efficiency) and v1 (pure correctness) Frontier rows could mix in one ladder, misleading the operator (MED-HIGH) | `source`(+`season` for bench2) is a hard partition on every ranking path (`rank_in_tier` signature, tier-cut evaluation, render labeling); never one merged sorted list | §4.6b, example 4.7d |

---

## 5. DESIGN — per-run SAVE (timestamped snapshot dirs)

Since §1 established the worktree/meta.json write path is real and
working, the delta for v2 is narrow: **key state by a run id, not by bare
model name**, and mint that id **once**, not per-subprocess-invocation.

- **Run id shape**: `<model>-<ts>` where `ts` is a run-start Unix
  timestamp (e.g. `gpt-5.4-1783400000`). Per the operator's own note,
  wall-clock cannot be freshly taken at every invocation and stay
  consistent — `bench.sh grade` is a brand-new process each call, so
  `$(date +%s)` inside it would mint a *different* id every section and
  fragment one run across many directories. **`ts` must be minted exactly
  once**, at `bench.sh start` / `run.sh <model>` (first prepare), and then
  **persisted to disk and re-read**, never recomputed, by every later
  `grade` call in that same run.
- **Where it's persisted**: extend the existing `runs/.current_model`
  single-line pointer to `runs/.current_run` holding `{"model": "...",
  "run_id": "...", "ts": ...}` (same pattern already used for
  `MODEL_STATE`, just one more field). `do_grade`/`grade_section` read
  `run_id` from this file instead of re-deriving anything.
- **State dir becomes** `runs/<run_id>/<section>/{worktree,meta.json,
  grade.json}` (`grade.json` is new: the raw grader JSON — `{"score",
  "gate","reason"}` — saved verbatim, closing the §1.2 gap so the
  initiative judge in §6 never has to reconstruct it from the TSV).
  `lib/grade_state.state_dir()` changes from `RUNS/model/section` to
  `RUNS/run_id/section`; every caller already goes through this one
  function, so this is a single-point change, not a scattered one.
- **Latest-run convenience**: `runs/<model>/latest` becomes a symlink to
  the most recent `runs/<model>-<ts>/` — so `bench.sh chart <model>`,
  `bench.sh status`, and any tool that wants "the current/most recent run
  for this model" without knowing its `ts` keeps working unchanged.
  Historical runs remain addressable directly by `run_id` for the
  initiative judge or manual diffing across a model's improvement over
  time.
- **Existing `runs/gpt-5.4/`, `runs/deepseek-v4-pro/`** (bare-model-named,
  pre-v2) are left exactly as-is — not migrated, not deleted — and keep
  meaning "the one run that model has" under the old layout; new v2 runs
  only ever land under `<model>-<ts>/`.

---

## 6. DESIGN — initiative axis (separate LLM-judge overlay)

**Not part of the deterministic total** — a fully separate, occasional
bonus track, so the core score stays comparable across models/runs and
never depends on an LLM judge's mood.

- **Trigger cadence**: on-demand via a new `bench.sh initiative <model>
  [<run_id>]` subcommand, or automatically every Nth completed run per
  model (config constant, default N=3) — bounds Opus-review cost the same
  way `GRADER-REVIEW.md`'s review of the graders themselves was a one-time
  audit pass, not a per-run tax.
- **Judge-don't-redo prompt shape**: the judge (Opus, per the existing
  adversarial-review convention — `Charon build methodology` memory: "DTC
  gates every decision") is handed, per section: the task prompt
  (`prompts/sN.txt`), the baseline fixture, the saved worktree diff, and
  the saved `grade.json` (§5) — **the deterministic score and reason are
  given as already-decided fact**, with an explicit instruction: *"Do not
  re-grade correctness or second-guess the score/gate above — assume they
  are right. Your ONLY job is to answer: given this diff already passed
  (or the state it's actually in), is there anything here that shows
  initiative ABOVE the deterministic floor — a novel-but-correct approach,
  an elegant simplification, a valuable addition the prompt didn't ask for
  but a good engineer would recognize as right-sized, or a documented
  insight/tradeoff call. Do NOT reward unrequested scope growth
  (overbuild) — that is a negative signal, not initiative."* This mirrors
  the existing "adversarial review must not silently override operator"
  posture — the judge critiques *within* a fixed correctness verdict, it
  never overturns it.
- **Rubric** (0-10 scale, additive sub-scores capped at 10):
  - +0-3 novel-but-correct approach (materially different from the
    obvious fixture-implied approach, and still passes)
  - +0-3 elegant simplification (fewer moving parts than the reference
    solution, same behavior)
  - +0-2 valuable non-overbuild addition (e.g., an edge case genuinely
    worth handling, added tersely — not speculative scaffolding)
  - +0-2 documented insight (a comment/commit message that correctly
    flags a real tradeoff, ambiguity, or risk the task didn't spell out)
  - Overbuild penalty: -0-5 if the diff does meaningfully more than the
    task asked without labeling it as a deliberate, scoped choice
    (mirrors S5's existing "hallucinated config" anti-pattern check, same
    spirit, applied qualitatively here).
- **Storage**: `runs/<run_id>/<section>/initiative.json` — `{"score":
  0-10, "rubric": {...sub-scores...}, "note": "...", "reviewed_ts": ...,
  "reviewer": "opus"}`. **Never written into `model-scorecard.tsv` and
  never read by `lib/efficiency.py` or the composite** — `tier_chart.py`
  may optionally print it as a trailing annotation (`+initiative: 7/10
  (reviewed 2026-07-10)`) next to a section's row, visually separate from
  the score/tier columns, exactly the way `cost_usd`/`time_s` are recorded
  today without being scored.

---

## 7. DESIGN — growing library / bounded rotating pool

**Goal**: keep runtime near the current ~61 min budget, keep the section
set alive and sourced from real production issues, and stop models from
being able to overfit a fixed, memorizable 7-item test.

- **Shape**: `FIXED_CORE` (small, permanent — recommend keeping today's
  S0 sanity gate plus 2 canonical anti-dodge sections, e.g. today's S2 and
  S6, since `GRADER-REVIEW.md` already proved those are the two hardest-
  to-game and most load-bearing) + a `ROTATING_POOL` sampled to bring the
  total to ~7 sections per run. Candidates enter the pool from real
  sources only: a fixed regression/red (`fleet/reds.tsv`-style), a
  scorecard `BLOCK` finding, or a bug actually fixed in Charon — never an
  invented/synthetic scenario, mirroring how S0-S6 themselves were built
  ("mirrors Charon's `gateway/*.py` shape" per `README.md`).
- **Candidate → active-section recipe** (every candidate must clear all
  of these before entering the rotating pool, reusing infrastructure that
  already exists rather than inventing new machinery):
  1. **Fixture**: a self-contained worktree snapshot in the injected-bug
     starting state (same shape as `fixtures/sections/sN/`).
  2. **Deterministic grader**: `<grader> --worktree <dir> --baseline
     <fixture>` → `{"score","gate","reason"}` (same CLI contract as
     `graders/common.py` already defines — new candidates should import
     it, not reinvent diff/pytest/swap-and-rerun helpers).
  3. **Self-test pair(s)**: `selftest/goldens/<id>/{golden,inert,...}`
     asserting the expected score band, run through
     `selftest/run_selftests.py` — at minimum a 100-golden and a 0-or-
     near-0 inert case; add named adversarial cases (dodge/hardcode/
     scope-violation) wherever the section's own failure mode calls for
     one, exactly like `s2/dodge-mocked` and `s6/scope-violation` already
     do.
  4. **Opus adversarial grader-review**: the SAME review discipline
     `GRADER-REVIEW.md` already performed on S0-S6 — does the grader
     actually prove the *code* path is real (not just the test), can it
     be gamed, are the self-tests tight enough to catch a regression.
     Only after a clean review does a candidate flip from `candidate` to
     `active` status.
- **Registry**: a new `fleet/benchmark/lib/sections_registry.json` (or an
  extension of `lib/sections.sh`) recording each section id's `status`
  (`candidate | active | retired`), `source` (which red/bug/scorecard
  finding it came from), and `added_ts`. `FIXED_CORE` ids are hardcoded;
  `ROTATING_POOL` is every `active`-status id not in `FIXED_CORE`.
- **Sampling for fairness**: freeze the rotating-pool draw per **season**
  (a coarse period, e.g. calendar week, identified by an id like
  `2026-W28`) rather than re-randomizing every single run — every model
  benchmarked within the same season faces the identical section set, so
  cross-model ranking within a season stays apples-to-apples; the pool
  only reshuffles at the season boundary, which is also when overfitting
  risk resets. (Randomizing per-run instead would make two models'
  composites incomparable even though both call themselves "v2" — flagged
  here explicitly as the tradeoff being resolved, not glossed over.)
- **Curation via scorecard discrimination**: a section that stops
  discriminating (every model in the last K `bench2` runs scores ≥90 on
  it) is flagged as a **retirement candidate** — never auto-retired
  (`adversarial review must not silently override operator` /
  `investigate-and-backup-before-data-loss` posture: a human confirms).
  Implement as `lib/curate_sections.py`, scanning `model-scorecard.tsv`
  grouped by `(section, source=bench2)`, printing e.g. `"S2: 6/6 models
  scored >=90 over the last 3 seasons — retirement candidate."`
- **Preflight nudge**: `bench.sh start` gets a one-time notice (same
  pattern as the existing `cost_mode_notice()`) — `"(N candidates pending
  curation — run lib/curate_sections.py --review to see them)"` — printed
  once per invocation, informational only, never blocking a run.

---

## 8. Phased build plan (file touch-points)

**Phase 1 — data foundation (tokens + per-run keying).** Prerequisite for
everything else; nothing in §4's math works without it.
- `lib/charon_cost.py`: add `snapshot_usage() -> {"tokens_in","tokens_out",
  "cost_usd"} | None` reading all three keys already in the gateway
  response; keep `snapshot_cost_usd()` as a thin wrapper for existing
  call sites (no behavior change to current callers).
- `lib/grade_state.py`: `cmd_init` snapshots `usage_start` (full dict, not
  just cost); `cmd_record` diffs `tokens_in`/`tokens_out` the same way it
  already diffs cost; `state_dir()` re-keyed from `RUNS/model/section` to
  `RUNS/run_id/section`; save `grade.json` alongside `meta.json`.
- `bench.sh`/`run.sh`: mint `run_id` once at `start`/first-prepare,
  persist to `runs/.current_run`, thread it through `prepare_section`/
  `do_grade`/`grade_section` instead of bare `model`; maintain
  `runs/<model>/latest` symlink.
- `model-scorecard.sh`: add `tokens` column (position 13, before `note`),
  bump `cmd_append`'s arity check, extend `VALID_SOURCE` with `bench2`.

**Phase 2 — scoring math.**
- New `lib/efficiency.py`: implements §4.3-§4.5 (mid-rank percentile,
  `MIN_FIELD_SIZE` gate, weighted combine, bounded per-section modifier,
  `section_total`) — operates only on an already-closed season cohort,
  never on a live/partial field.
- New `lib/close_season.py`: implements §4.2's batch job — reads all
  `bench2` rows tagged with a season id, builds `C(S,season)` per
  section, calls `efficiency.py` once per cohort, writes `section_total`/
  `modifier` back, flips row `status` from `provisional` to `final`.
  Triggered at the §7 season boundary or via `bench.sh season close
  <season_id>`. Never touches a season already marked `final`.
- `lib/tier_chart.py`: branch composite computation on `source`
  (`bench` → unchanged v1 mean; `bench2` → §4.6a's `composite_raw` +
  `COMPOSITE_EFF_CAP`-clamped delta); `rank_in_tier(models, source,
  season=None)` takes an explicit partition and refuses a mixed-source
  or mixed-season list (§4.6b); render labels every ladder by formula
  and season ("Frontier · v1" / "Frontier · v2 (2026-W28)"), never one
  merged sorted list; provisional `bench2` rows render `raw`-only.
- `bench.sh do_grade`: once tokens are present (Phase 1 done), append as
  `bench2` (new flag or harness-version constant) with `section_total:
  null, status: provisional` — the efficiency call happens later, in
  batch, at season close, not at append time.
- Self-tests: cross-source-isolation golden (`rank_in_tier` on a mixed
  list raises; `close_season.py` never admits a `bench` row into a
  `bench2` cohort) and a mid-rank/tie golden (3-way tie → 50, flat field
  → 50, `\|C\|<4` → modifier 0 for the whole cohort).

**Phase 3 — initiative overlay.**
- New `lib/initiative_judge.py` + `prompts/initiative-review.txt`
  implementing §6's judge-don't-redo prompt shape.
- New `bench.sh initiative <model> [<run_id>]` subcommand.
- `lib/tier_chart.py`: optional trailing annotation, no scoring impact.

**Phase 4 — growing library / rotating pool.**
- New `lib/sections_registry.json` + `lib/curate_sections.py`.
- `lib/sections.sh` (or its v2 successor): `FIXED_CORE` + season-scoped
  `ROTATING_POOL` sampling replacing the hardcoded `ALL_SECTIONS=(S0..S6)`.
- `bench.sh start`: preflight nudge for pending candidates.
- Process doc (not code): candidate authoring recipe (§7) added to
  `README.md`'s "Layout" section once Phase 4 lands.

Each phase is independently mergeable and independently useful (Phase 1
alone already fixes the real "tokens aren't captured" gap even before any
scoring-formula change ships); none require rewriting the graders
themselves (`GRADER-REVIEW.md`'s open S2/S6 fixes are an orthogonal,
already-tracked workstream).
