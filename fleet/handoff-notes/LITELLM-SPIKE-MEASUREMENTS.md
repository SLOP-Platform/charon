# LiteLLM spike — durable measurements (extracted before branch disposal)

**Provenance:** product-repo branch `spike/litellm-router-adapter` @ `f2cee9d`
("spike(litellm-router): prove litellm.Router fits UNDER Charon's policy layer"),
base `4028819`, spike authored 2026-07-19; extracted 2026-07-24.
Source file: `spike_litellm/SPIKE-FINDINGS.md` on that branch.

**Status: SUPERSEDED.** The spike branch is obsolete and safe to discard. Its question is
settled and its code is superseded by the shipped `src/charon/litellm_plane/` package
(`litellm_router.py`, `metering.py`, `park_cooldown.py`, `streaming.py` — `make_router`,
`complete_via_router`, `complete_via_router_guarded`, GW-BRIDGE-1/2/3, ADR-0020).
`spike_litellm/litellm_router_adapter.py` (~55 LOC) is strictly worse than the shipped
`litellm_plane/litellm_router.py`. The author marked `spike_litellm/` disposable in the
findings themselves. This note exists so nothing measured is lost when the branch goes.
Kept here in the **private rig repo** because the source file carried a `/home/stack`
absolute path that fails the product repo's `public-clean` gate.

---

## 1. Dependency footprint (measured, `pip install litellm` into a worktree venv)

- **218 MB** total installed (**204 MB** excluding pip).
- **1.6 s** cold `import litellm`.
- **17 packages ship native compiled extensions**, all on the request hot path:
  - Rust: `pydantic_core`, `tokenizers`, `hf_xet`, `jiter`, `rpds`
  - C: `aiohttp`, `regex`, `tiktoken`, `yaml`, `markupsafe`, `fastuuid`, `multidict`,
    `yarl`, `frozenlist`, `propcache`, `charset_normalizer`
- Size breakdown (heaviest): litellm 106M, openai 20M, hf_xet 12M, tokenizers 11M,
  aiohttp 7.7M, huggingface_hub 6.8M, pydantic_core 5M, pydantic 4M, tiktoken 3.5M,
  regex 3.5M.
- Windows wheels exist for all 17 → portable, but the architectural property is gone.

**Why it matters:** this is the concrete refutation of the stdlib-only / zero-native-dep
property of the privileged key-holding core (`gateway.py` docstring, ADR-0005). Because
the dependency lands on the *request hot path*, the "lazy-import optional plugin" escape
does **not** apply. This is the one measurement the spike produced that the landed
`litellm_plane` code does not record anywhere.

## 2. Deletable-LOC inventory — substrate made redundant by adoption

Direct input to the still-open wire-in ticket (accept #4), which `feat/gateway-litellm-live-wire`
deliberately refused to execute ("STOP, do not half-migrate the money-path").

| Target | What it is | LOC |
|---|---|---|
| `forwarder.py:181-235` | `_build_upstream_req` — per-attempt OpenAI request build | ~55 |
| `forwarder.py:563-651` | `urlopen` + retry-once + connection-error mapping | ~120 |
| `forwarder.py:825-915` | manual SSE head-buffering / stream commit (litellm streams natively) | ~90 |
| `failover.py` | cooldown / circuit-breaker FSM (litellm has per-deployment cooldown + `allowed_fails`) | 141 |
| `translate.py` | wire/shape translation | 142 |
| `response_adapters.py` | response shape adaptation | 106 |
| `proxy_server.py` | most of the raw forwarding plumbing | (unquantified) |

**Total rough deletable substrate: ~650–750 LOC** across forwarder / failover /
translate / response_adapters.

Line numbers are as of the spike base `4028819` (2026-07-19) — re-locate before acting.

## 3. What Charon KEEPS (the novel ~30% policy layer — proven to survive untouched)

`routing_policy/` (`order_chain_by_funding_class`, `order_pool_by_live_cost`,
`derived_cost_rank`, drain/pools/spill), `quality_scorer.py`,
`capability/scorecard.py` + `taxonomy.py`, and the drain-then-park / sole-leg guard
logic at `forwarder.py:418-482`. All are pure functions over a route chain and ran on
top of litellm unmodified in the spike.

## 4. Measured fit result

The spike drove every attempt through `litellm.Router` against a LOCAL mock OpenAI
server (no paid call) and called PRODUCT policy code unmodified. Observed:

```
policy order (free-first): ['provider-b', 'provider-a']
  provider-b: 429 exhausted=True -> failover
  provider-a: 200 cost=$5.4e-06 downgrade=False -> SERVED
quality: provider-a=1.00 provider-b=0.60
downgrade case: asked gpt-4o-mini got 'gpt-3.5-turbo' pseudo_success=True quality(provider-c)=0.60
```

- `order_chain_by_funding_class` reordered the chain free-first.
- `order_pool_by_live_cost` ran unchanged (no-op with an empty meter, as in prod).
- `GatewayProxy.classify` consumed litellm's response dict directly and derived
  `exhausted=True` on the mock 429 and `pseudo_success=True` on the model-mismatch 200.
- `QualityScorer.record(success=not obs.pseudo_success)` scored the downgrade as a
  FAILURE (0.60), matching prod.
- Only translation needed: fold litellm's out-of-band `response_cost` onto the
  `usage.cost` key that `_gateway_usage` (`proxy.py:139`) already reads.

Verdict recorded by the spike: **PASS** — the substrate is a documented, replaceable
commodity; the one real cost is the dependency footprint in §1.

## 5. Measured gaps — capabilities litellm does NOT provide

These are load-bearing for the future wire-in; each must stay Charon-side.

- **Silent-downgrade detection is Charon's, not litellm's.** litellm returns the 200
  happily; only `GatewayProxy.classify` flags `pseudo_success` on a model mismatch and
  only `quality_scorer` penalizes it. Adoption does not get this free.
  (Now landed as `complete_via_router_guarded`, GW-BRIDGE-1.)
- **Cost-meter semantics differ.** Charon distinguishes `cost_source` =
  free/provider/computed/unpriced (`proxy.py:409-433`) and carries the phantom-`$0`-spend
  fix (`forwarder._spend_to_record`). litellm gives a single `response_cost` float.
  (Resolved by ADR-0020: litellm metering is **verify-only**, Charon stays source of record.)
- **Funding-class drain-then-park and the sole-leg guard have no litellm equivalent.**
  litellm's fallback classes are static ordered lists; Charon's economic ordering,
  auto-park and pool-orphan guard (`forwarder.py:253-325, 437-482`) stay entirely Charon-side.
- **litellm wants to own failover.** To keep Charon's ordering authoritative you must pin
  `num_retries=0` and hand it ONE deployment per attempt — i.e. deliberately not use its
  router-of-many.

## 6. Superseded items (recorded for completeness, do not action)

The spike proposed follow-up ticket `ADOPT-SUBSTRATE-01` (land the adapter behind a
`gateway.backend` flag, default `stdlib`, dep opt-in via `pip install charon[litellm]`).
That has effectively been executed by the `litellm_plane` package. `.litellm-venv/`
(218 MB, untracked/gitignored) exists in the spike worktree and was never committed.
