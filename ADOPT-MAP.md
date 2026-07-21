# ADOPT-MAP — `litellm.Router` (as a library) for the gateway commodity plane

**Branch:** `feat/gateway-litellm-adopt` (off `origin/master` `56a00a1`) · **ADR:** 0017
(§Build-vs-Adopt: *OpenAI proxy / failover / cost / cooldown → ADOPT — LiteLLM*, PROVEN) ·
**Governing rule:** MANAGER-OPERATING-RULES §0 ADOPT-FIRST (adding `litellm` is allowed and
preferred; the former stdlib-only / `dependencies=[]` prohibition was removed on this base).

## What is being adopted, and how

`litellm.Router` is imported **as a library** — NOT its proxy-server / FastAPI / Prisma /
Redis deployment. Confirmed against the installed package (`litellm==1.93.0`): `Router.__init__`
exposes exactly the commodity-plane knobs Charon hand-rolls:

| Charon hand-rolled behavior (file:line) | `litellm.Router` feature | Notes |
|---|---|---|
| provider failover loop — `forwarder.py:565` (`for i, route in enumerate(ordered)`), unreachable→next `:586`, exhausted→next `:668` | N deployments per `model_name` + `num_retries` | a Charon chain maps to N deployments of one model_name |
| retry-once transient (`forwarder.py:611` `obs.exhausted and obs.transient`) | `num_retries=1`, `retry_after` | |
| cooldown after failure — `proxy_server.py:651` `order_by_cooldown`, `:716` `set_cooldown`, `_cooldown` dict + lock | `cooldown_time=`, `allowed_fails=` | account-level cooldown = Router's native model-cooldown |
| mechanical cheapest/latency ordering — `forwarder.py:530` (live cost), `:553` latency tiebreak | `routing_strategy="cost-based-routing"` / `"latency-based-routing"` | |
| cost metering — `balance.py BalanceTracker`, `proxy.py observe` | litellm cost callback + vendored price JSON (already ADOPTED, ADR-0016) | |
| HTTP data-plane — `proxy_server.py:20/207/454` (stdlib `http.server`) | subsumed (Router.completion makes the call) | see "deferred" |

## Files / LOC this adopt is on a path to DELETE (per ADR-0017: ~650–750 LOC)

- `forwarder.py` (934 LOC) — the failover loop, retry-once, cooldown calls, live-cost reorder.
  **KEEP (novel/policy, re-hosted on top of Router):** silent-downgrade double-bill fix
  (SR-1/SR-2, `:788`/`:878`), drain-then-park + funding-class + sole-leg (`:424`–`:487`),
  streaming-head downgrade detection (`:837`).
- `proxy_server.py` cooldown machinery — `order_by_cooldown:651`, `set_cooldown:716`,
  `retry_after_hint:686`, `_cooldown`/`_cooldown_lock`, `inflight_*`.
- `failover.py` `next_entry` / `proxy_excluded_keys` — KEEP `ReviewerCircuitBreaker`
  (post-MVP capability C, not the HTTP path).
- `routing_policy/cost_rank.py` `derived_cost_rank` mechanical sort — KEEP the funding-class
  drain ORDER (genuine local policy Router does not model).
- `netutil.py` — per ADR-0019 its own docstring: *"If the LiteLLM adopt lands … most of this
  file should be DELETED rather than ported"* (httpx does not follow redirects by default).

## HARD-PRESERVE controls, and where they live under litellm

The money-path is **not clean commodity** — it is fused with security + Charon policy. This
slice preserves each control at `model_list` build time and re-proves it (fail-on-revert tests
in `tests/test_litellm_router_adopt.py` + `tests/test_litellm_router_e2e.py`):

1. **base-bound provider key (#181, `secrets.get_provider_key`).** litellm sends `api_key`
   to `api_base` 1:1. The adapter resolves each route's key via
   `get_provider_key(provider, base_url=route.upstream_base)` (base-bound) and attaches it
   ONLY to that route's own `api_base`; a moved base resolves **no key**.
2. **SSRF / non-routable refusal (`netutil.validate_base_url`).** Link-local / cloud-metadata
   / non-http bases raise before entering the `model_list`.
3. **Preset-derived egress allowlist (`egress.assert_base_allowed`) — the egress.py
   reconciliation.** The `litellm_plane` outbound path is a NEW way to reach providers, so it
   enforces the SAME fail-CLOSED allowlist the live path enforces at
   `routing_policy.route_from_spec`: the EFFECTIVE base (the exact value written into the
   nested `litellm_params['api_base']` litellm actually dials — the LiteLLM CVE-2024-6587
   lesson) must be a git-tracked preset external host or a local host, else the route is
   REFUSED (`EgressPolicyError`). A preset repointed off-preset, or an attacker base, is
   dropped exactly as the live path drops it.
4. **No-redirect.** `httpx` (litellm's transport) does not follow redirects by default;
   `no_redirect_client()` pins `follow_redirects=False`.
5. **SG-never-Anthropic (`providers.is_anthropic_route`).** Every candidate is screened; an
   Anthropic model/provider/base is dropped from the `model_list` (never selectable).
6. **drain-then-park + funding-class ordering.** Preserved as a PRE-ordering
   (`routing_policy.order_chain_by_funding_class` + parked-provider exclusion).

## Slice boundary — what this branch delivers vs defers

**DELIVERS (coherent, landable, default-OFF so the live money-path is byte-identical):**
- `litellm` in `pyproject.toml` as the optional extra `router` (opt-in while it is not yet the
  live money-path; **promotable to core `dependencies`** when the live wire-in lands, accepting
  the ~218MB + native deps ADR-0017 calls out — no stdlib-gate rationale is involved, that gate
  was removed on this base).
- `src/charon/litellm_plane/` — the config→Router mapping (`build_model_list`, `make_router`,
  `complete_via_router`, `resolve_route_key`, `routes_by_model`, `no_redirect_client`) with
  controls 1–6 enforced at build time; `litellm` imported lazily so the module loads without it.
- fail-on-revert preservation tests for all six controls + cold-start order equivalence, an
  e2e (real gateway config → Router → httpx → stub upstream → served response), and a runnable
  dogfood (`tools/dogfood_litellm_router.py` + captured `DOGFOOD-litellm-router.txt`).

**DEFERRED to the next slice (documented, NOT silently dropped):**
- **The wire-in**: replacing `forwarder.forward_with_failover` / stdlib `http.server` so Router
  serves live traffic. Doing that safely means re-hosting the KEEP-list policy (silent-downgrade,
  drain-park, streaming downgrade) as Router callbacks/hooks — larger than one pass and
  highest-stakes; deferring it keeps the money-path from being half-migrated/broken.
- **Free-tier quota (parked FT-WIRE-QUOTA):** unchanged — preserved via the funding-class
  pre-ordering; litellm does not model per-provider free-tier windows, so this stays Charon
  policy fed into the Router pre-order.
- **Full park ↔ Router-cooldown unification** and the cost-callback → `BalanceTracker` bridge.
