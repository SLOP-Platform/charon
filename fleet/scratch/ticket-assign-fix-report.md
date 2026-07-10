# #14 review fixes — grades.py confidence-aware scoring + fixture tests

Scope: rig-level only (`fleet/capability/`), no product (`src/`) touch, no
commit/push. Builds on the existing #14 capability code, doesn't replace it.
Did not read or modify `fleet/model-scorecard.tsv` (live, mid-benchmark-run) —
all pinned assertions now run against a frozen fixture instead.

## 1. MUST-FIX: small-N over-trust in `capability/grades.py`

### The old formula and why it broke

`score = merge_pct - block_pct` collapses to `+100 / 0 / -100` at n=1 — a
single lucky MERGE is statistically indistinguishable from a 20/20 record,
and a model with more evidence *including a real BLOCK* could score worse
than a model that's never been tested more than once.

### The fix

Two **asymmetric Wilson score interval bounds** (Wilson 1927, 95%
confidence, `z=1.959963985`), scaled to 0..100, in `_wilson_bound()`:

```
score = wilson_lower_bound(merge, n)  -  wilson_upper_bound(block, n)
```

- **Merge uses the LOWER bound** — don't over-trust a good rate seen on a
  small sample (n=1, 1/1 MERGE lands at ~20.6, not 100).
- **Block uses the UPPER bound** — don't under-trust the *risk* a small
  sample implies. An n=1 sample with **zero** observed blocks still carries
  a wide "could-be-bad" upper bound (~79.3, not 0), because with only one
  data point you genuinely don't know the true block rate. A model with
  *more* total evidence narrows that upper bound even when one of its
  samples **is** a real block — this asymmetry is exactly what lets
  more-evidence-with-a-real-failure outrank a lucky single sample.

`merge_pct`/`block_pct` (raw percentages) are kept on `Grade` unchanged for
human-readable display; only the `score` rank key changed.

`Grade` gained a `low_confidence: bool` field (`n < MIN_N`), surfaced both
on the object and in `summary()` (e.g. `... score=-58 [LOW-CONFIDENCE: n<4]
...`), which `assign.py`'s rationale already prints via `grade.summary()`.
It's a **disclosure** flag, not a ranking gate — the Wilson bounds already
do continuous discounting, so this doesn't need to zero anything out
(unlike benchmark-v2's per-section `modifier=0` gate).

**MIN_N = 4**, reusing `fleet/benchmark/lib/efficiency.py`'s
`MIN_FIELD_SIZE = 4` and its stated rationale verbatim: "cohorts smaller
than this get modifier=0 ... below 4, percentile is either undefined or a
full-swing coin flip; not stable enough to move a tier decision." Same
sibling-scoring-module discipline, not a new invented threshold.

### Before/after on the demonstrated inversion (glm-5.2/routing, n=3, 2
MERGE + 1 real BLOCK vs. kimi-k2.6/routing, n=1 lucky MERGE)

| | old formula | new formula |
|---|---|---|
| glm-5.2/routing (n=3, 1 real BLOCK) | **33.3** | **-58.47** |
| kimi-k2.6/routing (n=1, lucky MERGE) | **100** | **-58.69** |
| Result | kimi wins (WRONG — less evidence, no failure, beats real record) | glm-5.2 wins (n=3 with real evidence edges out n=1 luck) |

`assign("routing", ...)` now picks `glm-5.2`, not `kimi-k2.6`, given only
those two candidates. Both are still flagged `LOW-CONFIDENCE` (n<4) in the
rationale — disclosed, not hidden — but the ranking itself is now correct.
A genuinely high-n case (`claude-sonnet-5`/`tests`, n=5, 4 MERGE + 1 FIXES)
is NOT flagged low-confidence and scores -5.89 — much better than either
n=1/n=3 case above, confirming the fix makes small-n and large-n cases
distinguishable in the direction the review asked for ("a 20/20 record
should not be indistinguishable from a lucky n=1").

## 2. SHOULD-FIX: frozen fixture TSV

New file: `fleet/capability/testdata/scorecard-fixture.tsv` — hand-designed,
13-column rows matching `ScorecardGradesProvider._load()`'s parser. Covers:
- the routing inversion case (glm-5.2 n=3 w/ BLOCK vs kimi-k2.6 n=1 lucky)
- ci-infra (single clean-MERGE winner among FIXES)
- money-path (hy3-preview-or is the only BLOCK)
- refactor / bugfix (independent distinct winners, for the differentiation
  proof)
- frontend (direct-data models vs. a fallback-only model with a *higher*
  raw score — the fallback-de-prioritization case)
- tests (claude-sonnet-5, n=5, the high-confidence contrast case)
- greenfield-feature (**no rows at all** — pure generalist-fallback path)

Model ids intentionally reuse real `charon/src/charon/model_catalog.py`
entries (glm-5.2=med, claude-opus-4-8=high, claude-haiku-4.5=low,
claude-sonnet-5=med, gpt-5.5=high, kimi-k2.6=med) so `get_tier_hint()`
resolves real tiers and the tier-exclusion path is exercisable without
faking the catalog; `hy3-preview-or` is deliberately absent from the
catalog to exercise the documented "unknown tier passes through" gap.

`selftest.py`'s pinned/hard assertions (differentiation, ci-infra pick,
money-path BLOCK penalty, availability-changes-pick, D&S refusal, the
confidence-inversion fix, tier-exclusion, generalist-fallback,
fallback-de-prioritization) all now run against this fixture via
`ScorecardGradesProvider(FIXTURE_TSV)`.

A separate `smoke_check_live_scorecard()` still runs `assign()` against the
**live** `fleet/model-scorecard.tsv` (via `DEFAULT_TSV`) but only prints
`[INFO]` lines — no assertions, wrapped in try/except so it can never fail
the gate on live-data shape changes. This is the "non-asserting, tolerant"
real-scorecard check the review asked to keep.

New test coverage added (previously missing per review Q4b):
- **Tier-exclusion path**: `required_tier="high"` on money-path excludes
  glm-5.2 (tier=med) even though it's equal-or-better scoring than the
  pick, picks claude-opus-4-8 (tier=high), and asserts the exclusion is
  surfaced in the rationale.
- **Generalist-fallback path**: `greenfield-feature` has zero direct rows
  for any model; asserts assign() still produces a pick (doesn't refuse)
  and that the picked grade is flagged `fallback_used=True`,
  `used_work_class="generalist"`.

## 3. SHOULD-FIX: de-prioritize generalist fallback

`assign.py`'s `_sort_key()` now sorts on `(fallback_used, -score, ...)` —
direct-work_class evidence (`fallback_used=False`) always ranks ahead of a
generalist-fallback grade (`fallback_used=True`), regardless of raw score.
`_rationale()` gained a matching audit NOTE (mirroring the existing
excluded-candidate NOTE): if a fallback candidate out-scored the
direct-evidence pick, it's called out by name, e.g.:

```
NOTE: claude-sonnet-5 scored higher via generalist fallback
(no direct frontend evidence) — ranked below the direct-evidence pick
```

Demonstrated in the fixture: `claude-sonnet-5`'s frontend *fallback* score
(-5.89, borrowed from its n=5 `tests` record) is objectively higher than
`claude-opus-4-8`'s *direct* frontend score (-58.69, n=1). Before this fix,
sonnet would have won frontend on raw score with zero direct frontend
evidence. After: `claude-opus-4-8` (direct) wins, sonnet is visibly
de-prioritized and named in the rationale — not silently dropped.

## Test results

```
$ python3 capability/selftest.py
... (22 checks total across differentiation / availability / D&S /
     confidence-inversion / tier-exclusion / generalist-fallback /
     fallback-de-prioritization)
SELFTEST: ALL CHECKS PASS — assign() differentiates on a frozen fixture,
confidence-aware scoring fixes the small-N inversion, and availability
demonstrably changes the pick.
$ echo $?
0
```

`py_compile` clean on all four modules (`grades.py assign.py availability.py
selftest.py`). Also manually ran `python3 assign.py --work-class ci-infra`
against the live `model-scorecard.tsv` (read-only CLI invocation, no writes)
to confirm the new scoring doesn't crash on real data shapes — picked
`glm-5.2`, printed `[LOW-CONFIDENCE: n<4]` as expected for n=1 real rows.

## Deferred (not in this pass, per the review's own "defer/nits" bucket)

- Item 4 (lockstep test for bash↔Python WORK_CLASSES/tier-alias/TSV-column
  duplication) and item 5 (sys.path bare-name shadow risk) were explicitly
  filed as "defer/nits", not must/should-fix — left untouched.

## Files touched

- `fleet/capability/grades.py` — Wilson-bound confidence-aware `score`,
  `MIN_N`/`low_confidence`/`_wilson_bound`, updated docstrings.
- `fleet/capability/assign.py` — fallback-de-prioritized `_sort_key`, new
  audit NOTE in `_rationale`.
- `fleet/capability/selftest.py` — rewritten to run hard assertions against
  the frozen fixture, added confidence-inversion / tier-exclusion /
  generalist-fallback / fallback-de-prioritization tests, added a
  non-asserting live-scorecard smoke check.
- `fleet/capability/testdata/scorecard-fixture.tsv` — new, frozen synthetic
  fixture (not derived from live data).
- `fleet/model-scorecard.tsv` — **untouched** (confirmed via `git status`:
  no diff).

## Proposed commit message (not committed — operator's call)

```
fix(capability): confidence-aware grade scoring + frozen fixture tests (#14 review)

Replace raw merge%-block% scoring in grades.py with an asymmetric Wilson
score interval spread (merge lower bound - block upper bound) so a model
with more evidence and a real observed failure no longer loses to a single
lucky sample (demonstrated inversion: glm-5.2/routing n=3 w/ real BLOCK
now outranks n=1 lucky-MERGE competitors). Adds a LOW_CONFIDENCE disclosure
flag (n < MIN_N=4, reusing benchmark-v2 efficiency.py's MIN_FIELD_SIZE
threshold/rationale) surfaced on Grade and in the rationale.

De-prioritizes generalist-fallback grades below direct-work_class evidence
in assign()'s ranking (was ranked as an equal peer), with a matching audit
NOTE when a de-prioritized fallback candidate outscored the pick.

Freezes capability/testdata/scorecard-fixture.tsv and points selftest.py's
pinned assertions at it instead of the live, append-only
model-scorecard.tsv; adds tier-exclusion and generalist-fallback path
coverage; keeps one non-asserting smoke check against the live scorecard.

Addresses must-fix #1 and should-fix #2/#3 from
fleet/scratch/ticket-assign-review.md. Defer/nits #4-#5 left for later.
```
