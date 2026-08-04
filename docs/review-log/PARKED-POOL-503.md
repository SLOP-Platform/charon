# PARKED-POOL-503 — review note

Implements OPERATOR DECISION **D-012** (2026-08-04): *"I don't want a situation
where EVERYONE is parked but I understand it may be needed for some reason.
Change it to 503 don't allow it to leak."*

## The defect
The DRAIN-AND-PARK never-strand fallback in `src/charon/forwarder.py` restored
the **FULL** chain — parked legs INCLUDED — whenever nothing survived the drain
pre-flight, and then served a normal **200**. When the reason nothing survived
was *every leg is parked*, that silently undid the park and billed upstream
anyway. Measured 2026-08-03 on the live gateway: `kimi-k2.6` (5/5 legs parked)
and `minimax-m2.5` (2/2 parked) both served 200 via openrouter. Parking exists to
STOP spend; this is how money leaked while every dashboard read healthy.

Three further holes in the same class, all closed here:

* the whole drain/park pre-flight is guarded by `len(chain) > 1`, so a
  **single-leg** pool never consulted park state at all and served a 200 straight
  off its parked leg;
* `gateway._build_balance_tracker` returned `None` unless some provider carried
  `funding_class`/`mode`. A `None` tracker never loads `balance_park.json`, so
  **every** parked leg is served and the new guard silently does not exist — the
  same leak, reachable by one config edit;
* `litellm_plane/litellm_router._preorder_chain` did `return live or list(chain)`
  — the same restore-the-parked-chain fallback, in the commodity plane.

## The fix
One guard in `forwarder.py`, placed **after** the semantic-cache lookup and
**before** `is_stream` / the R2 ordering / the dispatch loop:

```python
if bt is not None and chain and all(
        bt.is_parked(r.provider or r.label) for r in chain):
    ... terminal 503 ...
```

Against each of D-012's four requirements:

1. **Terminal 503, never a success-shaped body.** The branch writes the envelope
   and `return`s; nothing downstream can turn it back into a 200.
2. **Names every leg with its real per-leg status and a non-empty reason.**
   `providers_tried` carries one entry per leg: `provider`, `status: "parked"`,
   a non-empty `reason`, plus `class`/`rearm` from `_classify_provider(prov, bt)`
   so the operator sees what re-arms it. It **reuses the existing
   `all_providers_exhausted` shape** — no second error shape was invented.
3. **Distinguishable from "all legs tried and failed"** via the existing
   `no_provider_reason` field: `"all_legs_parked"` here, `None` on the
   tried-and-failed path. Same envelope, different cause, machine-readable.
4. **`X-Charon-*` reports the truth.** `failovers=[]` → `X-Charon-Failovers: 0`
   (zero upstream calls) and **no `X-Charon-Provider`**, because no provider
   served the request — naming a leg that was never called would be the same lie
   in a different field. No `Retry-After`: a parked leg re-arms on an operator
   top-up/unpark, not on a timer. And **no `note_request`**: `provider_stats`
   records what PROVIDERS did, and a sentinel row there would blame a config
   state on an upstream that was never called. This follows the established
   convention for a gateway-side refusal — the spend-cap 402 and the guardrail
   400 above also return without touching `provider_stats`. The WARNING log is
   the operator signal, and it names every parked leg.

### Placement is load-bearing in both directions
* **Below the cache check.** A cache HIT costs **zero dollars**. D-012 stops
  SPEND, not traffic; refusing an already-paid-for response has no money
  argument behind it and is a straight regression. Red-proof I2 below.
* **Above `is_stream` and the dispatch loop.** No upstream call is reachable
  from the guard, streaming or not.

### `bt is None` fails CLOSED at the source
`_build_balance_tracker` now also builds a tracker when a **persisted park set**
is on disk, even with no provider carrying balance config, reading the same file
and key as `BalanceTracker._load_parked` (an unreadable/corrupt park file counts
as "parked" — fail closed). Refusing to *start* would be the wrong kind of
closed: a gateway with no balance config is a supported, backward-compatible mode
with nothing to enforce. After this, `balance_tracker is None` provably means
"no balance config AND nothing parked on disk", which makes the forwarder guard
**vacuous rather than absent**. Red-proofs K and K2 pin both halves.

### ⚠ Anti-over-block — stated plainly, NOT presented as a proof
`test_one_unparked_leg_still_serves_a_real_200_and_never_strands` **does not**
independently prove that `all(...)` (rather than `any(...)`) is what scopes the
503. The DRAIN-AND-PARK pre-flight already removes every parked leg before the
guard runs, so the chain the guard sees can never be MIXED: `any` and `all` agree
on it, and mutating one into the other leaves the **entire suite green** (2395
passed — confirmed by adversarial review). The scoping is **structurally
guaranteed upstream, not pinned by a test at this position**. `all` is kept
because it is the defensively correct predicate, not because a test falsifies the
alternative. What the test *does* pin is the end-to-end property the operator
cares about — one parked leg must not take a servable pool down — which goes red
the moment the guard is moved above the drain pre-flight (red-proof I). The
equivalent property in the litellm plane **is** independently falsifiable and is
proved there (red-proof L2).

### The commodity plane
`_preorder_chain` now returns `live` (possibly empty) instead of
`live or list(chain)`. An empty chain builds no deployment, so the plane can only
refuse; it can never silently serve a parked leg. A pool with one unparked leg is
unaffected.

## RED-PROOF — every new/changed assertion OBSERVED failing
Method: mutate the source, run the target test, restore. Each line is the ACTUAL
captured failure, not a paraphrase.

| # | Mutation | Assertion that went RED |
|---|---|---|
| A | D-012 guard deleted | `BEHAVIOUR: every leg parked → the gateway answered 200; a fully-parked pool must be a terminal 503, not a billed 200` / `assert 200 == 503` (also reddens the sole-leg test) |
| B | `type` → `"all_legs_parked"` (second error shape) | `...invented a second error shape` / `assert 'all_legs_parked' == 'all_providers_exhausted'` |
| C | `for r in chain[:1]` | `does not name EVERY parked leg` / `assert ['pa'] == ['pa','pb']` |
| D | per-leg `status` → `503` | `per-leg status is not the real one` / `assert [503, 503] == ['parked','parked']` |
| E | per-leg `reason` → `""` | `a leg was named with no reason` / `assert False` |
| F | `no_provider_reason` → `None` | `indistinguishable from real upstream exhaustion — an operator cannot tell them apart` / `assert None == 'all_legs_parked'` |
| G | `failovers` = the parked legs | `headers claim upstream attempts that never happened; reported '2'` / `assert '2' == '0'` |
| G2 | `provider=parked_legs[0]["provider"]` | `the refusal names a serving provider ('pa') — nothing served it` / `assert 'pa' is None` |
| G3 | `note_request(..., "(all-legs-parked)", 503, ...)` restored | `the refusal invented a provider row in provider_stats: {'(all-legs-parked)': {'served': 0, 'failed': 0, 'errors': 1, ...}}` / `assert {'(all-legs-parked)'} <= {'pa','pb'}` |
| H | branch un-parks the legs | `serving the 503 silently UN-PARKED providers` / `assert False = is_parked('pa')` |
| I | guard moved ABOVE the drain pre-flight, `any()` | `one leg parked, one live → the gateway answered 503. The parked-pool 503 over-blocked a servable pool` / `assert 503 == 200`; also reddens `test_parked_leg_is_never_dispatched_while_a_live_leg_exists` |
| I2 | guard moved ABOVE the cache check | `a fully-parked pool refused a FREE cache hit with 503 — D-012 stops spend, not zero-cost traffic` / `assert 503 == 200` |
| J | guard re-nested under `len(chain) > 1` | `a sole parked leg still served 200 — the park leaked through the len(chain) > 1 guard` / `assert 200 == 503` |
| K | `_build_balance_tracker` ignores persisted parks | `a persisted park set was ignored because no provider carried balance config — the fully-parked 503 guard cannot exist` / `assert None is not None` |
| K2 | tracker built with nothing configured and nothing parked | `a tracker is built when there is provably nothing parked and nothing configured — that is not fail-closed, it is noise` / `assert <BalanceTracker...> is None` |
| L | `_preorder_chain` → `live or list(chain)` | `a fully-parked pool was restored into the selectable set: ['a', 'b']` / `assert [UpstreamRoute...] == []` |
| L2 | `_preorder_chain` → `[]` (over-block) | `the live leg did not survive the parked exclusion: []` / `assert [] == ['b']` |

`all(...)` → `any(...)` **in place** is deliberately absent from this table: it
stays GREEN, for the structural reason set out above. An unfalsifiable assertion
is not a proof and is not presented as one.

## FOUND, NOT FIXED — needs an operator decision
`litellm_plane/park_cooldown.py::park_cooldown_filter_chain` has the SAME
restore-the-parked-chain behaviour via `sole_leg_guard(live, chain)`, and
`tests/test_gw_bridge4_park_cooldown.py` cements it
(`test_sole_leg_guard_keeps_last_leg` parks the only leg and asserts the chain is
restored; `test_sole_leg_guard_multi_model` likewise). It is **inert** — zero
callers in `src/` — so there is no live leak today. It is NOT changed here
because that module's stated invariant #2 is operator-declared
("SOLE-LEG GUARD ... non-negotiable"), and D-012 does not obviously override it:
the guard also covers *cooldown* exclusion, which is transient and costs nothing
extra to retry, unlike a park. Splitting park (money) from cooldown (transient)
there is the right fix, and it needs the operator to say so.

## Scope note
This branch contains ONLY the D-012 change. An earlier revision also carried a
cherry-pick of `be71807` (FORWARDER-COST-ORDER-FALLBACK); adversarial review
proved it a **no-op** on the live gateway (no deepseek-v4-flash leg carries
`cost_input`, so every paid leg derives rank 1000 and the stable sort returns the
chain unchanged) **and** an active regression (its empty-meter `sorted()`
clobbers `order_chain_by_funding_class`, so a cheaper-per-token PAYG leg is tried
before a prepaid class-3 credit the drain-then-park directive says to drain
first). It was dropped. **No cost-order fix landed on this branch.**
