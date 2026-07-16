# Adversarial review — DELETE-STATIC-RANK (ADR-0016 step #6, PR #152, merged b9140b5)

Scope of the diff: commits `c6bfc2c` (src) + `6978e1f` (tests). It removes the
"explicit `cost_rank` wins" branch from `derived_cost_rank`, stops persisting
`cost_rank` to `models.json`, and flips the old-behavior tests. Ordering is now
ALWAYS derived from `cost_input`/`cost_output` (+ live meter, dormant) and
`cost_class`. **The diff touches ordering DERIVATION only — no availability,
funding, or fail-loud code was modified.**

---

## 1. Correctness of selection — VERDICT: SOUND
- Sort key is ascending, cheapest-first, everywhere it matters:
  `pools.py:136` → `(not e.free, e.cost_class_priority, e.cost_rank)`;
  identical tuple in `routing_policy/__init__.py:142-145` and `_live_rank_key`
  (`:244-248`). `not free` → False(0) sorts first, class-priority 0=cheapest
  first, cost_rank ascending. No wrong sort direction, no off-by-one, no
  tie-break that floats the dearest up.
- `derived_cost_rank` (`cost_rank.py:82-93`): metered path and pricing path use
  the SAME ×1e8 scale, so priced and metered models are comparable. Blend
  `(3*ci+co)/4` is a sane in:out weighting. `max(0, …)` clamps negatives.

## 2. Availability / funding (zero-balance / parked / dead excluded) — VERDICT: SOUND (out of scope of diff)
- Drain-then-park / funding-class ordering (`_FUNDING_CLASS_ORDER`,
  `order_chain_by_funding_class`, `:278+`) and cooldown/quality filters
  (`forwarder.py:500-508`) are UNTOUCHED by this diff. A dead/parked provider is
  excluded by those downstream passes, not by cost_rank. No regression path
  introduced here.

## 3. Fallback / empty-set fail-loud — VERDICT: SOUND (out of scope of diff)
- Terminal exhaustion / `providers_tried` envelope is a SEPARATE commit
  (`c4377f7`), not in this PR. `order_pool_by_live_cost` is null-safe
  (`:268-272` returns `[]` / unchanged chain). This PR cannot select from an
  empty capable set — it only reorders an already-built chain. No new crash or
  silent-wrong-pick path.

## 4. Money exposure — VERDICT: SUSPECT (operational, data-dependent — the real finding)
Two exposures, both conditional on catalog data completeness, made worse by the
removal of the operator override:

**4a. Missing-pricing collapse to the 1000 fallback (`cost_rank.py:88-89`).**
Any model with NO `cost_input`/`cost_output` derives rank **1000** — a fixed
"neutral middle" (≈ $10/M blended, since 1e-5 × 1e8 = 1000). After this PR:
- Two unpriced models in the same `cost_class` TIE at 1000 → order falls to
  config/dict-insertion order (`pools.py:136` stable sort). If the pricier
  provider is listed first in `models.json`, it is tried first → **routes to the
  more expensive provider.**
- An unpriced-but-genuinely-EXPENSIVE model sorts at 1000, i.e. AHEAD of any
  priced model whose blended rank > 1000 (> $10/M) → the dear unpriced one wins.
- Pre-delete, an operator could correct this with a hand `cost_rank`. That
  escape hatch is now GONE (`routing_policy/__init__.py:117`, docstring drops
  "operator escape hatch").

**Failing scenario:** `.60 models.json` has two metered providers for a role,
`prov-A` (dear, listed first, no `cost_input`) and `prov-B` (cheap, no
`cost_input`). Operator previously ranked B first via `cost_rank`. The ticket's
own DEPLOY action ("purge `cost_rank` from `.60 /data/models.json`",
review-log §65-67) removes that rank. Both now derive 1000 → stable sort keeps
config order → **A (dear) is tried first. Money leak, silent, no warning.**
There is NO preflight/gate ensuring every routable model carries
`cost_input`/`cost_output` (grep found none; `pricing_limits_checker.py` is
flagged inert/unwired in `tools/inert-code-disposition.json`).

**4b. (Pre-existing, currently DORMANT) metered path is cumulative, not per-unit.**
`proxy.py:522` accumulates `_model_provider_cost[key] += u.cost_usd` — CUMULATIVE
total spend per (model,provider). `derived_cost_rank(metered_cost=…)` treats it
as a comparable cost figure. A cheap, heavily-used provider accrues a larger
cumulative total than a rarely-used dear one → the CHEAP one sorts as "dearer"
and is deprioritized. This bug PRE-DATES this PR (R5/COST-RANK-AUTO) and is
currently inert (`proxy.py:595`: ledger EMPTY under real traffic, Wave-2
deferred; confirmed by MEMORY "meter is inert"). **But this PR removes the
override that could have masked it when the meter is finally wired.** Flag for
the METER wiring ticket.

## 5. Regression (capability/latency/detention filters, assign.py re-rank) — VERDICT: SOUND
- Diff does not touch capability/latency/cooldown/quality filters or
  `assign.py`. `cost_class` retained and still orders (tests + `pools.py:136`).
  `mypy`/`ruff`/boundary green per review-log; 1828 tests pass.

## 6. Tests — VERDICT: SOUND but INCOMPLETE
- Non-vacuous: `test_delete_static_rank.py` uses real `add_model`/`load_config`/
  `load_pools`, does A/B pool-order comparison (`:52-90`), asserts warning
  emission and non-persistence (`:91-127`), and cost_class precedence. Reverting
  the deletion turns them RED. Good FAIL-ON-REVERT contract.
- GAP: **no test covers the finding-4a scenario** — two models with NO pricing
  and NO cost_rank tie-broken by config order, i.e. the exact production state
  after the deploy purge. The tests always supply `cost_input`/`cost_output`, so
  they never exercise the 1000-collapse that the deploy will actually create.
- Concerns 2/3 (dead-provider-excluded, empty-set-fail-loud) are NOT proven here
  — correctly, since the diff doesn't own that code — but the task asked, so:
  those guarantees rest on untouched downstream code, not on this PR.

---

## Bottom line
The CODE change is correct and well-tested for what it does (sort direction,
cost_class retention, override-ignored, non-persistence). The risk is
OPERATIONAL: the mandated deploy-side purge of `cost_rank` from `.60`
`models.json` will silently collapse any model lacking `cost_input`/`cost_output`
to a fixed rank 1000, tie-broken by config order — and the operator override that
could correct a bad derived order is now gone, with no preflight guaranteeing
priced-completeness. Highest-risk = **4a**.

## Recommended fix (before/with the .60 purge)
1. Add a preflight/gate: every model reachable in a pool chain MUST have
   `cost_input`+`cost_output` (or `free:true`); FAIL LOUD otherwise. Run it as
   part of the deploy that purges `cost_rank`.
2. Add a test for the unpriced-tie scenario (two pool members, no pricing, no
   cost_rank) asserting a deterministic + documented order (or a raised error).
3. Ticket the cumulative-vs-per-unit metered-cost bug (4b) as a blocker on the
   METER-wiring ticket, since the override safety net is now removed.
