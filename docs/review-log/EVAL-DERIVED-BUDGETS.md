# EVAL-DERIVED-BUDGETS — Review Log

## Ticket
EVAL-DERIVED-BUDGETS (review F8): replace the arbitrary rung/latency budgets
(3/6/10 min, 480/900s) with **DERIVED** budgets keyed on (canonical work_class
× difficulty), computed from the OBSERVED completion-time distribution of
known-good models, and normalized per-leg via token / measured tok_s.

## The problem (F8, restated)
`fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md` F8 catches that the round
numbers contradict the observed 20s–538s spread (RFL-3 field jammed 497–499 s
against a 480 s ceiling — below the task's real p50 for capable models — while
SECRET-HOTROTATE finishes in 20–35 s, making 480 s ~15× too loose there). One
flat budget is simultaneously too tight AND too loose. F8's fix is two-part:
(a) derive `p95(good_model_completion) + margin` per (work_class, difficulty),
and (b) normalize out leg throughput by expressing the budget in tokens and
deriving the per-run wall-clock as `tokens / measured_tok_s(leg) + overhead`.

## What was done (files owned by this ticket)
- `fleet/benchmark/budget-derive.py` — stdlib-only derivation module. Reads
  `model-scorecard.tsv` (`time_s`, col 10) and dogfood-eval result-card
  SUMMARY.md tables (`wall_s`, col 4) for KNOWN-GOOD completions only (verdict
  MERGE from the scorecard; REVIEW-READY from a result card), groups by
  canonical work_class (resolving legacy fleet classes via
  `fleet/state/EVAL-TAXONOMY.md`'s `_LEGACY_TO_CANONICAL`-shaped mapping so the
  budget key matches what `grades.py`/the product router consume), and derives
  `budget = p95(times) + margin`. Also reads `LEG-RANK.tsv` per-leg `tok_s` to
  normalize: `wall_budget = token_budget / tok_s + overhead`. Emits a small
  `budgets.tsv` keyed `(canonical_work_class, difficulty)` with both the
  wall-clock budget (slow-leg reference) AND a token budget, so a caller divides
  by the actual leg's tok_s for a fair per-run ceiling.
- `fleet/state/PREFLIGHT-DESIGN-V2.md` — the design-of-record doc the codebase
  already references (`fleet/benchmark/preflight.sh`, `preflight.py`, the
  preflight-tasks manifest, and the grader `_pf_common.py` all point at it). It
  did NOT exist on master; this ticket creates it. §LATENCY-BUDGET replaces the
  arbitrary 3/6/10 min + 480/900s with the derived table + the p95+margin rule
  + the token/tok_s normalization rule, and points at `budget-derive.py` as the
  single recompute path.
- `fleet/tests/budget-derive.test.sh` — hermetic FAIL-ON-REVERT proof.

## Key decisions

### D1 — "known-good" = MERGE (scorecard) or REVIEW-READY (result card)
F8 says "budget from the OBSERVED completion-time distribution of KNOWN-GOOD
models." A model-run is known-good iff it actually completed the work to a
passing objective grade. For the scorecard that's `verdict == MERGE`
(the `dogfood-to-scorecard.sh` mapping of REVIEW-READY→MERGE confirms this).
For a result-card SUMMARY row that's `verdict` startswith `REVIEW-READY`
(before the finalize step folds it to MERGE). FIXES/BLOCK/RETRY/DETAIN rows
are excluded — a DETAIN(latency) row is exactly the too-slow tail we must NOT
let raise the p95 (it would re-introduce the RFL-3 499-s truncation as
"evidence" the budget should be 499). This also means a fixture with zero
good rows falls back to a documented safe default, never silently 0.

### D2 — `budget = p95(good_times) + margin`, margin = 0.5 × p95 (1.5× total)
F8 names "p95 + margin (e.g. 1.5×)" as the rule. Implemented as
`budget = p95 * 1.5` (margin is 0.5×p95, total 1.5×). Reasons:
- p95, not max: robust to a single outlier run (a one-off provider hiccup that
  still graded MERGE shouldn't pin the budget at 2× typical).
- 1.5× total: enough headroom that a capable model on a slightly-slow-but-
  healthy leg is not DETAINed for latency (F4's wall-clock DETAIN), while a
  model that needs >>1.5× a known-good model's time is genuinely too slow.
  F8's own worked example ("RFL-3 ~800 s" from a 538 s good-model max ≈ p95)
  sits inside 1.5× (538 × 1.5 = 807).
- Margin is a FUNCTION of p95, never a flat add-on — otherwise slow tasks
  (RFL-3) and fast tasks (SECRET-HOTROTATE) get the same headroom and the
  "one flat budget failed both" problem returns in a different shape.

### D3 — canonical work_class key (join on EVAL-TAXONOMY.md)
Budgets are per "(work_class, difficulty)". The work_class MUST be the
canonical product-router vocabulary from EVAL-TAXONOMY.md (`reasoning, coding,
translation, creative, analysis, general`), not the fleet ticket-shape
vocabulary — for the exact reason EVAL-TAXONOMY-ALIGN fixed: a budget keyed on
a fleet class the router never queries is useless to the router. So
`budget-derive.py` ships the SAME legacy→canonical mapping
(`_LEGACY_TO_CANONICAL`) EVAL-TAXONOMY-ALIGN put in grades.py (duplicated
verbatim per that file's duplication discipline — both are literal copies of
the SSOT table in EVAL-TAXONOMY.md, drift-checked at import). A scorecard row
tagged `bugfix`/`ci-infra`/`routing`/etc. is resolved to `coding` before
entering its (work_class, difficulty) bucket. This is the
EVAL-TAXONOMY-ALIGN dependency made load-bearing.

### D4 — difficulty = 2 default; difficulty axis stays a caller input
F8 specifies `(work_class × difficulty)`. The difficulty axis is the ticket's
rung/IRT-ladder input (EVAL-PIPELINE-CONSOLIDATE owns the ladder); this module
accepts `--difficulty` and defaults to 2 (mid) so a caller without a ladder
still gets a sensible single budget. The dogfood-eval tickets observed in F8
are all "small-ticket D1–D3" today; D2 is the honest mid-band centroid.

### D5 — token + tok_s normalization (the "not a flat number" half)
F8(b): a fixed wall-clock conflates "model is slow to reason" with "leg has
low throughput today." Fix: express the task budget in TOKENS (p95 of
good-model OUTPUT tokens for the task — `tokens_out` col 15 in the scorecard,
`completion_tokens` proxy via wall_s×tok_s when tokens_out is `-`), then
`wall_budget(leg) = token_budget / measured_tok_s(leg) + fixed_overhead`.
LEG-RANK.tsv (col `tok_s`, produced by LEG-PREFLIGHT-CANARY) is the source of
per-leg throughput. A slow leg (low tok_s) gets proportionally more wall time
for the same token budget; only a model that emits MORE tokens than the
good-model p95 (thrashing/looping) or stalls fails. This is exactly the
"2× tok_s → ~½ wall-clock" invariant the FAIL-ON-REVERT test asserts.

### D6 — overhead = 20s (fixed), per-leg normalization is multiplicative
The `fixed_overhead` in `wall = tokens/tok_s + overhead` covers worktree
setup, gate invocation, and the non-streaming kernel of any run (git fetch,
worktree add, the grader fork). 20s matches the `BENCH_MTIME_STABLE_SEC`
settle gate and the leg-preflight latency probe order of magnitude; it is
NOT a second latency budget, just a constant floor so a 1-token leg still
gets nonzero wall. Normalization is `tokens / tok_s` — so a 2× tok_s leg
gets exactly ½ the streaming wall (the fail-on-revert invariant).
- token_budget = p95(good `tokens_out`) — what a correct, non-looping model
  actually emits for this task class.
- If no token data: fall back to `p95(good wall_s) × reference_tok_s` so the
  module still produces a token budget from wall-clock-only scorecards (the
  common case today; tokens_in/out were added later and many rows are `-`).

### D7 — safe fallback when no known-good data
If a (work_class, difficulty) bucket has ZERO known-good rows, the module
returns a documented `status=insufficient-data` row with a conservative
default (`DEFAULT_WALL_S = 900`, the current dogfood-eval default, and
`DEFAULT_TOKEN_BUDGET = 12000`) rather than 0/None. This default is NOT
presented as derived — it is explicitly labeled so a caller can see which
buckets still need calibration data and so the DETAIN threshold is never
absent (F1/F4's gate requires a number to fire). 900s is the highest of the
old arbitrary numbers, used as a ceiling-not-cliff: better to over-budget
an uncalibrated class than to DETAIN a good model for exceeding 0.

### D8 — output format (budgets.tsv)
Tab-separated, keyed (canonical_work_class, difficulty), with columns:
`work_class  difficulty  n_good  p95_time_s  wall_budget_s  token_budget  status`.
`wall_budget_s` is the SLOW-LEG reference (p95_time_s × 1.5); per-run callers
divide `token_budget` by the actual leg's `tok_s` and add overhead for the
fair per-run ceiling. Both are emitted so a caller without LEG-RANK.tsv can
still use the flat wall (graceful degrade) while a caller with it gets the
normalized number (the F8(b) win).

## FAIL-ON-REVERT proof (`fleet/tests/budget-derive.test.sh`)
Two assertions, both hermetic over a fixture distribution:

1. **p95+margin exact**: a fixture scorecard with a known time distribution
   → derived `wall_budget_s == p95(times) * 1.5`. Revert the derivation (make
   `derive_budget` return the hardcoded 480) → the assertion fails. This is
   the exact "revert the derivation → it returns the hardcoded 480 → test
   fails" clause in the ticket's FAIL-ON-REVERT.

2. **2× tok_s → ~½ wall-clock**: same token_budget, two legs (tok_s = T and
   2T) → the 2T leg's `wall_for_leg` is ~½ the T leg's. Revert the
   normalization (make `wall_for_leg` ignore tok_s and return the flat
   wall_budget_s) → the two legs get the SAME wall → the ratio is 1.0, not
   ~0.5 → assertion fails. This is the "a leg with 2x tok_s gets ~½ the
   wall-clock ceiling for the same token budget (proves normalization, not a
   flat number)" clause.

Both assertions use the REAL `budget-derive.py` over a fixture scorecard +
fixture LEG-RANK.tsv (no network, no live ledger).

## Scope check (changed paths)
- `fleet/benchmark/budget-derive.py` — in `owns:`
- `fleet/state/PREFLIGHT-DESIGN-V2.md` — in `owns:`
- `fleet/tests/budget-derive.test.sh` — in `owns:`
- `docs/review-log/EVAL-DERIVED-BUDGETS.md` — this fragment (allowed)

No other files touched.

## Gate
- `ruff check fleet/benchmark/budget-derive.py` → clean
- `mypy fleet/benchmark/budget-derive.py` → clean
- `bash fleet/tests/budget-derive.test.sh` → SELFTEST SUMMARY: N passed, 0 failed

## Residual / blast radius
- Zero existing callers read `budget-derive.py` today (new file); it feeds
  EVAL-LATENCY-GATE's DETAIN threshold and EVAL-PIPELINE-CONSOLIDATE's rungs
  by PRODUCING the budgets those tickets consume. Neither is wired here
  (out of scope, out of `owns:`). The module is a pure derivation + I/O tool;
  merging it cannot break a green gate.
- The arbitrary numbers in `dogfood-eval.sh` (`LATENCY_BUDGET_S=900`),
  `honest-battery-sweep.sh` (`480`), and `lib/sections.sh` (`180/360/600/480/
  720/600/720`) are NOT edited here (out of `owns:`); PREFLIGHT-DESIGN-V2.md
  documents them as the values to be REPLACED by the derived table, and
  names the consuming tickets that will repoint them. This ticket is the
  source-of-truth derivation + the design doc; the repointing is the
  consumers' job (per the `Feeds EVAL-LATENCY-GATE's DETAIN threshold and
  EVAL-PIPELINE's rungs` clause).
