# SPIKE: can `litellm.Router` sit UNDER Charon's policy layer?

Throwaway feasibility proof. NOT an adoption. Branch `spike/litellm-router-adapter`,
worktree `/home/stack/code/charon-fleet-LITELLM-SPIKE`. Settles the months-old
build-vs-adopt question for the gateway *substrate* with running evidence.

## The question
Can `litellm.Router` be the mechanical substrate for ONE provider attempt (the
OpenAI-compatible call + retry/cooldown + cost capture) while Charon's policy
layer — its funding-class ordering, live-cost cheapest-first, quality feedback
loop, silent-downgrade penalty — keeps deciding WHICH provider to try, unchanged?

## What was built (additive, new files only)
- `litellm_router_adapter.py` (~55 LOC of body) — makes `litellm.Router` satisfy
  the exact per-attempt contract `forwarder.forward_with_failover` consumes:
  `(route, messages) -> (status:int, headers:dict, body:dict)` in OpenAI shape,
  which `GatewayProxy.classify(...)` turns into a `ProxyObservation`. It replaces
  the substrate slice `forwarder.py:181-235` (`_build_upstream_req`) +
  `forwarder.py:563-651` (`urllib.urlopen` + retry-once). `num_retries=0` keeps
  Charon's OUTER failover loop authoritative (litellm is the caller, not the brain).
- `run_spike.py` — drives it end-to-end against a LOCAL mock OpenAI server (no paid
  call). Imports and calls the PRODUCT policy code unmodified:
  `order_chain_by_funding_class`, `order_pool_by_live_cost`, `GatewayProxy.classify`,
  `QualityScorer.record/score`.

Run: `PYTHONPATH=src .litellm-venv/bin/python3 spike_litellm/run_spike.py`

Observed output:
```
policy order (free-first): ['provider-b', 'provider-a']
  provider-b: 429 exhausted=True -> failover
  provider-a: 200 cost=$5.4e-06 downgrade=False -> SERVED
quality: provider-a=1.00 provider-b=0.60
downgrade case: asked gpt-4o-mini got 'gpt-3.5-turbo' pseudo_success=True quality(provider-c)=0.60
SPIKE OK: litellm.Router drove every attempt; Charon policy code ran unchanged.
```

## The 5 measured answers

### 1. Fit — YES, policy layer literally unchanged
Every Charon policy call ran on the dict litellm returns with ZERO modification:
- `order_chain_by_funding_class` reordered the chain free-first (`[provider-b, provider-a]`).
- `order_pool_by_live_cost` ran on the same chain (no-op with empty meter, as in prod).
- `GatewayProxy.classify` consumed litellm's response dict and correctly derived
  `exhausted=True` on the mock 429, and `pseudo_success=True` on the model-mismatch 200.
- `QualityScorer.record(success=not obs.pseudo_success)` — the DTC-CONCERN-#4 loop
  (forwarder.py:814) — scored the downgrade as a FAILURE (0.60), exactly as prod.

The only translation the adapter performs is folding litellm's out-of-band
`response_cost` onto the `usage.cost` key that `_gateway_usage` (proxy.py:139)
already reads. Charon's cost/quality/failover semantics needed no change.

### 2. Dependency footprint — CONFIRMS the ~200MB hot-path concern
`pip install litellm` into a worktree venv: **218 MB** total (204 MB excl. pip).
`import litellm` cold: **1.6 s**. Heaviest: litellm 106M, openai 20M, hf_xet 12M,
tokenizers 11M, aiohttp 7.7M, huggingface_hub 6.8M, pydantic_core 5M, pydantic 4M,
tiktoken 3.5M, regex 3.5M. **17 packages ship native compiled extensions** (Rust:
pydantic_core, tokenizers, hf_xet, jiter, rpds; C: aiohttp, regex, tiktoken, yaml,
markupsafe, fastuuid, multidict, yarl, frozenlist, propcache, charset_normalizer).
This lands on the request hot path — the "lazy-import optional plugin" escape does
NOT apply. It directly refutes the stdlib-only / zero-native-dep property of the
privileged key-holding core (gateway.py docstring, ADR-0005). Windows wheels exist
for all 17, so it's portable, but the architectural property is gone.

### 3. What Charon DELETES if this holds (substrate made redundant)
- `forwarder.py:181-235` `_build_upstream_req` — per-attempt OpenAI request build (~55 LOC)
- `forwarder.py:563-651` urlopen + retry-once + connection-error mapping (~120 LOC)
- `forwarder.py:825-915` manual SSE head-buffering / stream commit (~90 LOC; litellm streams natively)
- `failover.py` cooldown/circuit-breaker FSM (141 LOC — litellm has per-deployment cooldown/`allowed_fails`)
- `translate.py` (142 LOC) + `response_adapters.py` (106 LOC) — wire/shape translation litellm ships for 100+ providers
- most of `proxy_server.py`'s raw forwarding plumbing
Rough deletable substrate: **~650-750 LOC** across forwarder/failover/translate/adapters.

### 3b. What Charon KEEPS (the novel ~30% policy layer, all survives untouched)
`routing_policy/` (`order_chain_by_funding_class`, `order_pool_by_live_cost`,
`derived_cost_rank`, drain/pools/spill), `quality_scorer.py`, `capability/scorecard.py`
+ `taxonomy.py`, the drain-then-park / sole-leg guard logic in `forwarder.py:418-482`.
All are pure functions over a route chain — proven here to run on top of litellm unchanged.

### 4. What breaks / doesn't fit (concrete gaps)
- **Silent-downgrade detection is CHARON'S, not litellm's.** litellm returns the 200
  happily; only `GatewayProxy.classify` flags `pseudo_success` on a model mismatch and
  only Charon's `quality_scorer` penalizes it. Adopting litellm does NOT get this free —
  it must stay in Charon's layer, wrapping litellm's response (proven working in the spike).
- **Cost-meter semantics differ.** Charon distinguishes `cost_source` = free/provider/
  computed/unpriced (proxy.py:409-433) and has the phantom-`$0`-spend fix (forwarder.py
  `_spend_to_record`). litellm gives a single `response_cost` float. The adapter maps it,
  but Charon's richer $0/unpriced/free distinctions still live in `classify`, not litellm.
- **Funding-class drain-then-park & sole-leg guard have no litellm equivalent** — litellm's
  fallback classes are static ordered lists; Charon's economic ordering + auto-park + pool-
  orphan guard (forwarder.py:253-325, 437-482) stay entirely Charon-side.
- **litellm wants to own failover.** It has its own retry/fallback across deployments. To
  keep Charon's ordering authoritative you must pin `num_retries=0` and give it ONE
  deployment per attempt (as the adapter does), i.e. deliberately NOT use its router-of-many.

None of these BREAK the fit — they are all things Charon keeps on top. No policy code changed.

## VERDICT: **PASS**
The substrate is a documented, replaceable commodity. `litellm.Router` satisfied
Charon's exact per-attempt interface with the policy layer literally unchanged;
failover, cost capture, and the silent-downgrade quality penalty all worked on top.
The one real cost is measured and confirmed (218MB + 17 native-ext deps on the hot
path, trading away the stdlib-only property) — a genuine tradeoff, not a blocker.

This does NOT recommend a rip-and-replace. It confirms the escape hatch is real, per
the survey: freeze the substrate, stop investing in it, and the adopt path exists when
needed.

### Smallest real adoption ticket that would follow
> **ADOPT-SUBSTRATE-01 (behind a `gateway.backend` flag, default `stdlib`):** land
> `litellm_router_adapter.attempt()` as the `litellm` backend for a single provider
> attempt inside `forward_with_failover`, gated so the stdlib path stays default and
> the 200MB dep is opt-in (`pip install charon[litellm]`, extra only). Keep 100% of
> `routing_policy/` + `quality_scorer` + downgrade classify on top. Acceptance: the
> existing forwarder test suite passes against BOTH backends; the litellm backend is
> never imported unless the flag is set (preserves stdlib-only default core).

## Throwaway note
`spike_litellm/` is disposable. `.litellm-venv/` is gitignored (never committed).
`run_spike.py` is a rough harness (bare asserts, no test framework). `litellm_router_adapter.py`
passes ruff and is the only file worth keeping as a reference for ADOPT-SUBSTRATE-01.
