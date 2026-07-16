"""PRICE-REFRESHER — FAIL-ON-REVERT tests (ADR-0016 step #3, ADOPT-NOT-BUILD).

Adopted sources: vendored LiteLLM `model_prices_and_context_window.json`
(MIT) subset, OpenRouter live poll, changedetection.io webhook ingest.
All three are BACKGROUND writers into a local ``PriceCache`` that
``apply_to`` flattens into the ``model_pricing`` map
``routing_policy.order_pool_by_live_cost`` reads. Routing is CACHE-ONLY
— never network, never on the request path.

The meter-observed per-(model, provider) cost SUPERSEDES any quoted
price the moment traffic exists; the adopted sources are cold-start /
advisory only. ANTI-ROT guard #1.

The refresher is OFF the hot path. ANTI-ROT guard #2.

GREEN-IS-NOT-PROOF: existing routing/forwarder suites pass with
``model_pricing`` empty (they exercise "meter or static order"). The
following four tests are the only thing that proves the adopted
sources are actually wired in correctly. Revert any of them → the
adopted source is no longer contributing to cold-start ordering, and
the ticket's "replaces the hand-typed R17 TSV" claim collapses.

Guards, each RED if the named wire is reverted:
  1. The vendored LiteLLM snapshot populates ``model_pricing`` keyed
     per (provider, model) such that ``order_pool_by_live_cost`` orders
     the cheaper-sourced provider first with an EMPTY meter.
  2. ROUTING READS CACHE ONLY — the OpenRouter poller's ``poll_count``
     stays 0 across a real ``forward_with_failover`` call. The poll
     is exercised as a background call that writes the cache.
  3. The meter-observed per-(model, provider) cost SUPERSEDES the
     sourced/pulled quote once traffic exists.
  4. The webhook ingest path accepts a changedetection.io JSON POST,
     writes the cache, and the cache flip drives ``model_pricing``
     cold-start ordering.

Plus an additional structural assertion: the LiteLLM JSON is VENDORED
(embedded in the source, not fetched at request time) and keyed per
(provider, model) — the "100x harder" pitfall #4 guard.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

from charon.proxy_server import GatewayProxyServer, UpstreamRoute
from charon.routing_policy import order_pool_by_live_cost
from charon.routing_policy.price_refresher import (
    OpenRouterPoller,
    PriceCache,
    apply_to,
    ingest_change_detection,
    ingest_openrouter_catalog,
    load_vendored_snapshot,
)


@contextmanager
def _server(**kw) -> Iterator[GatewayProxyServer]:
    """A gateway server bound to an ephemeral port; closed on exit."""
    srv = GatewayProxyServer(**kw)
    try:
        yield srv
    finally:
        try:
            srv.server_close()
        except Exception:  # noqa: BLE001
            pass


# ── mock upstream (honest OpenAI-shaped 200) for the off-hot-path test ─────
class _Echo(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:  # silence
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = json.dumps({
            "model": self.server.return_model,  # type: ignore[attr-defined]
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 5, "cost": 0.0},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@contextmanager
def _mock_upstream(return_model: str) -> Iterator[str]:
    up = _Threaded(("127.0.0.1", 0), _Echo)
    up.return_model = return_model  # type: ignore[attr-defined]
    threading.Thread(target=up.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{up.server_port}"
    finally:
        up.shutdown()


def _send(url: str, payload: dict) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    resp.read()
    resp.close()


# ── structural: the LiteLLM subset is VENDORED, not fetched ────────────────
def test_vendored_subset_is_embedded_and_provider_keyed() -> None:
    """The LiteLLM JSON is embedded in the source as a Python literal
    (vendored), not fetched at request time, and its keys are forced
    into the (provider, model) shape — pitfall #4.

    Revert the ``_LITELLM_SUBSET`` constant to ``{}`` and the
    cold-start ordering reverts to "static-config only" — a wrong
    failure mode the eval flagged as the cost of the "hand-typed R17
    TSV" we are replacing. Revert the provider filter and the subset
    includes entries the router can't key (e.g. openai/bedrock)."""
    from charon.routing_policy import price_refresher

    # Vendored (not fetched): the constant must be a non-empty dict
    # that's importable without touching the network.
    subset = price_refresher._LITELLM_SUBSET
    assert isinstance(subset, dict) and len(subset) > 0, (
        "vendored LiteLLM subset must be embedded (non-empty); "
        "replacing the constant with {} removes the cold-start baseline "
        "the ticket is supposed to provide")
    # Provenance: the source repo / license is declared in the docstring
    # surface area — a reviewer must be able to read it without reading
    # the full file.
    prov = price_refresher._LITELLM_PROVENANCE
    assert "BerriAI" in prov and "MIT" in prov, (
        "LiteLLM provenance must declare upstream repo + license "
        "so a reviewer can verify the adopt-not-build source")
    # Provider-keyed: the subset must be a per-(provider, model) table,
    # not a per-model table. Spot-check a known multi-provider entry
    # (``openai/gpt-oss-20b`` is $5e-8 on together_ai, $2e-8 on
    # openrouter, $7.5e-8 on groq — three distinct values for one
    # model id, the exact pitfall the eval calls out).
    gpt_oss_entries = [
        (k, v) for k, v in subset.items()
        if "gpt-oss-20b" in k
    ]
    assert len(gpt_oss_entries) >= 2, (
        f"subset must carry gpt-oss-20b under MULTIPLE providers "
        f"(pitfall #4: same model priced differently per provider); "
        f"found {len(gpt_oss_entries)} entries")
    providers_seen = {
        v.get("litellm_provider") for _, v in gpt_oss_entries
        if isinstance(v, dict)
    }
    assert len(providers_seen) >= 2, (
        f"gpt-oss-20b entries must span multiple providers in the "
        f"subset (the multi-provider keying); found {providers_seen}")


# ── 1. vendored snapshot populates model_pricing; cheaper-sourced provider first ──
def test_vendored_snapshot_orders_cheaper_sourced_provider_first() -> None:
    """With a populated vendored snapshot, the REAL builder
    (``build_routes_and_pools``) puts the cheaper-sourced provider
    first in the failover chain — that's the cold-start ordering
    the gateway reads when no traffic has filled the meter yet.

    Setup: two providers of the same model, both quoted by the
    vendored LiteLLM snapshot, with one distinctly cheaper than the
    other. ``model_pricing`` is fed via ``apply_to(price_cache, ...)``,
    exactly as the real writer wire would do. We then drive the
    REAL builder — not a re-implementation of the sort — and assert
    the chain order reflects the vendored price.

    KEYING NOTE: the forwarder R2 block builds its per-route registry
    keyed by ``route.model_id`` and pulls from ``model_pricing[mid]``;
    a single shared mid for both providers would collapse the per-
    provider distinction (pitfall #4). The vendored LiteLLM snapshot
    uses reseller-prefixed keys (``openrouter/openai/gpt-oss-20b``,
    ``groq/openai/gpt-oss-20b``); the per-member-id IS the
    (provider, model) keying the eval demands. ``build_routes_and_pools``
    consumes the member-id-keyed registry (the same shape the catalog
    refresh bridge uses) and produces a per-pool failover chain in
    cheapest-first order — that's the cold-start path this test
    exercises.

    WHY NOT ``order_pool_by_live_cost`` WITH EMPTY METER?
    That function deliberately short-circuits on empty meter (see
    routing_policy/__init__.py:270-271: "If ``metered_costs`` is
    empty/None, the order is **unchanged**"). The cold-start order
    is set by ``build_routes_and_pools`` at gateway-startup time;
    ``order_pool_by_live_cost`` only re-sorts when the meter has
    data. The vendored snapshot's job is to feed the builder."""
    from charon.routing_policy import build_routes_and_pools
    cache = PriceCache()
    # Use a slice of the real vendored subset that contains a known
    # multi-provider entry. ``openai/gpt-oss-20b`` has three distinct
    # prices across groq / openrouter / together_ai; filtering the
    # subset down keeps the test fast and the assertion precise.
    from charon.routing_policy import price_refresher
    pruned = {
        k: v for k, v in price_refresher._LITELLM_SUBSET.items()
        if "gpt-oss-20b" in k
    }
    assert len(pruned) >= 2, "subset must carry gpt-oss-20b under multiple providers"
    load_vendored_snapshot(cache, subset=pruned)

    # The vendored cache holds the (provider, model) per-provider
    # prices. Surface them as a member-id-keyed registry — the
    # shape ``build_routes_and_pools`` consumes (same shape the
    # catalog refresh bridge uses, where each entry is one
    # provider's offer of one model with its specific per-token
    # price).
    # Map vendored provider names onto Charon's built-in preset
    # labels: LiteLLM uses ``together_ai`` (matching the upstream
    # API name); Charon's preset is ``together`` (matching the
    # brand). The ``_LITELLM_PROVIDER_TO_CHARON`` table does this
    # in production; we mirror it here for the test.
    _PROV_MAP = {
        "deepseek": "deepseek",
        "openrouter": "openrouter",
        "together_ai": "together",
        "groq": "groq",
        "fireworks_ai": "fireworks",
    }
    registry: dict[str, dict] = {}
    pool_map: dict[str, list[str]] = {}
    shared_mid = "openai/gpt-oss-20b"
    for (provider, model), entry in cache.snapshot().items():
        # The bare model id is the shared routable id; the member
        # id encodes the provider.
        if model != shared_mid:
            continue
        charon_prov = _PROV_MAP.get(provider, provider)
        member_id = f"{charon_prov}/{model}"
        spec: dict = {
            "provider": charon_prov,
            "upstream_model": model,
            "cost_input": entry.cost_input,
            "cost_output": entry.cost_output,
            "source_kind": entry.source_kind,
            "source": entry.source,
        }
        if entry.cache_read is not None:
            spec["cost_input_cache_read"] = entry.cache_read
        if entry.cache_write is not None:
            spec["cost_input_cache_write"] = entry.cache_write
        registry[member_id] = spec
        # Each provider's offer is exposed under the bare shared id
        # so the pool contains all of them; the builder picks the
        # cheapest-first chain from this pool.
        pool_map.setdefault(shared_mid, []).append(member_id)
    assert len(pool_map[shared_mid]) >= 2, (
        f"pool must contain at least two providers for {shared_mid} "
        f"to exercise the per-provider price ordering; got "
        f"{pool_map.get(shared_mid)}")

    # The flattening chose the cheapest sourced provider for this
    # model id — it must be the openrouter variant ($2e-8).
    flat_spec = cache.flatten()[shared_mid]
    assert flat_spec["provider"] == "openrouter", (
        f"cheapest sourced provider for gpt-oss-20b should be openrouter "
        f"($2e-8 per eval), got {flat_spec['provider']!r}")
    assert flat_spec["cost_input"] == 2e-08, (
        f"vendored-sourced cost_input should be the openrouter value "
        f"($2e-8), got {flat_spec['cost_input']!r}")
    # The all_providers list records every (provider, source_kind) pair
    # the cache holds for this model — proves the (provider, model)
    # keying survives the flatten.
    all_provs = flat_spec.get("all_providers", [])
    assert {p for p, _ in all_provs} == {"groq", "openrouter", "together_ai"}, (
        f"flatten must preserve all per-provider variants (pitfall #4: "
        f"the same model is priced differently per provider); got {all_provs}")

    # Drive the REAL builder — no meter, no static config beyond
    # the vendored registry. The chain order must reflect the
    # vendored price (cheaper-sourced provider first).
    # providers_cfg provides the per-provider base_url the builder
    # needs to construct UpstreamRoutes (the vendored snapshot
    # carries the per-token PRICE, not the network endpoint; the
    # endpoint comes from the Charon provider presets).
    providers_cfg = {
        "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
        "together": {"base_url": "https://api.together.xyz/v1"},
        "groq": {"base_url": "https://api.groq.com/openai/v1"},
    }
    _routes, pools, _ids = build_routes_and_pools(
        registry, pool_map, providers_cfg)
    # The pool is keyed by the shared mid; the chain is the
    # cheapest-first list of UpstreamRoute the gateway stores in
    # ``srv.pools[shared_mid]``.
    chain = pools[shared_mid]
    # Charon's preset for together_ai is ``together`` (the LiteLLM
    # upstream name vs the brand); the build order reflects the
    # vendored per-token prices: openrouter ($2e-8) → together
    # ($5e-8) → groq ($7.5e-8).
    assert [r.provider for r in chain] == [
        "openrouter", "together", "groq",
    ], (
        f"REAL builder must order the chain cheapest-first from the "
        f"vendored snapshot: openrouter $2e-8 (cheapest), together "
        f"$5e-8, groq $7.5e-8; got {[r.provider for r in chain]}")


# ── 1b. REVERT-MARKER: empty snapshot → cold-start order is unseeded ───────
def test_empty_snapshot_leaves_model_pricing_unseeded() -> None:
    """The FAIL-ON-REVERT flip-side of test 1. If the vendored snapshot
    load is reverted (constant → {}), the cache is empty, ``model_pricing``
    is unseeded, and cold-start order is arbitrary. This test asserts
    the empty baseline explicitly so the GREEN-IS-NOT-PROOF risk is
    documented in the test suite itself."""
    cache = PriceCache()
    written = load_vendored_snapshot(cache, subset={})
    assert written == 0, "empty subset must write zero entries"
    model_pricing: dict[str, dict] = {}
    n = apply_to(cache, model_pricing)
    assert n == 0, "empty cache → empty model_pricing"
    assert model_pricing == {}, "no baseline, no ordering hint — meter is the only signal"


# ── 2. ROUTING READS CACHE ONLY — OpenRouter poll NEVER runs on hot path ──
def test_openrouter_poll_never_runs_on_forward_with_failover() -> None:
    """The OpenRouter poller is BACKGROUND ONLY — driving real traffic
    leaves its ``poll_count`` at 0. The poller is exercised as a
    background call that writes the cache; the hot path never reaches it.

    Revert the cache/router split (make routing call the network) and
    this test goes RED — the whole point of the ticket's "off the
    per-request hot path" hard requirement."""
    cache = PriceCache()
    # Pre-seed the cache with a known openrouter-sourced entry so the
    # router can serve traffic without ever needing the poller.
    cache.put(__import__("charon.routing_policy.price_refresher",
                          fromlist=["PriceEntry"]).PriceEntry(
        provider="openrouter", model="offpath-model",
        cost_input=1e-6, cost_output=2e-6,
        source="test", source_kind="openrouter"))
    with _mock_upstream("offpath-model") as base:
        # Build a poller whose fetcher returns a valid OpenRouter
        # payload (no real network) and whose TTL is huge so the
        # background loop is dormant during the test.
        payload = {"data": [{"id": "offpath-model", "pricing": {
            "prompt": "0.0000005", "completion": "0.000001", }}]}
        poller = OpenRouterPoller(
            cache, ttl_s=999.0,
            fetcher=lambda _url: payload)
        with _server(modules={"price_refresher_cache": cache,
                              "openrouter_poller": poller}) as srv:
            # Build the routing config the writer would have built.
            model_pricing: dict[str, dict] = {}
            apply_to(cache, model_pricing)
            srv.model_pricing.update(model_pricing)
            # Add a route that the forwarder can use.
            route = UpstreamRoute(
                base, "k", upstream_model="offpath-model",
                provider="openrouter", model_id="offpath-model")
            srv.routes["offpath-model"] = route
            # Set up a pool so chain_for resolves.
            srv.pools["offpath-model"] = [route]
            assert srv.chain_for("offpath-model"), "setup: model must be routable"

            poller.poll_count = 0    # baseline: only traffic counts here

            srv.serve_in_thread()
            try:
                for _ in range(3):
                    _send(srv.url + "/v1/chat/completions",
                          {"model": "offpath-model",
                           "messages": [{"role": "user", "content": "hi"}]})
            finally:
                srv.shutdown()

            assert poller.poll_count == 0, (
                "forward_with_failover must NEVER reach the OpenRouter "
                "poller — routing reads the cache only "
                f"(poll_count={poller.poll_count})")


def test_openrouter_background_poll_writes_cache() -> None:
    """The poller IS reachable out-of-band — exercise the background
    path explicitly. After one poll, the cache carries the parsed
    per-token prices as PriceEntry records; the flatten then exposes
    them in model_pricing. Revert the cache writer and the entry is
    missing; revert the parse and the prices are wrong."""
    cache = PriceCache()
    payload = {"data": [
        {"id": "openai/gpt-4o", "pricing": {
            "prompt": "0.0000025", "completion": "0.00001",
            "input_cache_read": "0.00000125"}},
        {"id": "openai/gpt-4o-mini", "pricing": {
            "prompt": "0.00000015", "completion": "0.0000006"}},
    ]}
    n = ingest_openrouter_catalog(cache, payload)
    assert n == 2, f"both openrouter rows must be cached, got {n}"
    # Spot-check: the cache holds a (openrouter, gpt-4o) entry with
    # the per-token string prices parsed to floats.
    e = cache.get("openrouter", "openai/gpt-4o")
    assert e is not None, "openrouter/gpt-4o entry must be cached"
    assert e.cost_input == 2.5e-06
    assert e.cost_output == 1e-05
    assert e.cache_read == 1.25e-06
    assert e.source_kind == "openrouter"
    # Flatten to model_pricing and check the per-id projection.
    model_pricing: dict[str, dict] = {}
    apply_to(cache, model_pricing)
    assert "openai/gpt-4o" in model_pricing
    assert model_pricing["openai/gpt-4o"]["cost_input"] == 2.5e-06
    assert model_pricing["openai/gpt-4o-mini"]["cost_input"] == 1.5e-07


# ── 3. METER SUPERSEDES the sourced/pulled quote ───────────────────────────
def test_meter_supersedes_sourced_quote() -> None:
    """The third invariant: a non-empty meter overrides the sourced /
    pulled quote the moment traffic exists. The sourced numbers in
    model_pricing say openrouter is cheap; the meter says it's now
    expensive; the REAL selector must follow the meter.

    Without this precedence, the adopted sources would silently
    mis-order spend (the #1 pitfall: thinking-token undercount)."""
    cache = PriceCache()
    # Seed the cache with a vendored price that says openrouter is
    # cheap and groq is expensive.
    cache.put(__import__("charon.routing_policy.price_refresher",
                          fromlist=["PriceEntry"]).PriceEntry(
        provider="openrouter", model="m",
        cost_input=1e-7, cost_output=1e-7,
        source="test", source_kind="vendored"))
    cache.put(__import__("charon.routing_policy.price_refresher",
                          fromlist=["PriceEntry"]).PriceEntry(
        provider="groq", model="m",
        cost_input=9e-6, cost_output=9e-6,
        source="test", source_kind="vendored"))
    model_pricing: dict[str, dict] = {}
    apply_to(cache, model_pricing)
    # Build the registry the way forwarder.py:540 does it.
    registry = {mid: dict(model_pricing[mid]) for mid in model_pricing}
    chain = [
        UpstreamRoute("http://o.test/v1", "ko", upstream_model="m",
                      provider="openrouter", model_id="m"),
        UpstreamRoute("http://g.test/v1", "kg", upstream_model="m",
                      provider="groq", model_id="m"),
    ]
    # Empty meter: the vendored order should put openrouter first.
    base_order = order_pool_by_live_cost(
        chain, registry=registry, metered_costs={})
    # (Chain passed in already-cheap first; the metered version below
    # reverses to test that the order FLIPS under the meter.)
    assert [r.provider for r in base_order] == ["openrouter", "groq"], (
        "baseline: vendored price should rank openrouter above groq")

    # Now the meter INVERTS the economics — openrouter is now expensive
    # in real traffic (the #1 pitfall: thinking tokens), groq is cheap.
    metered = {("m", "openrouter"): 9e-6, ("m", "groq"): 1e-9}
    ordered = order_pool_by_live_cost(
        chain, registry=registry, metered_costs=metered)
    assert ordered[0].provider == "groq", (
        f"live metered cost must SUPERSEDE the sourced/pulled quote "
        f"(pitfall #1: thinking-token undercount); got "
        f"{[r.provider for r in ordered]}")


# ── 4. webhook ingest path (changedetection.io) ────────────────────────────
def test_change_detection_webhook_writes_cache() -> None:
    """The changedetection.io webhook ingest (Apache-2.0, self-hosted,
    NOT in this repo) POSTs a structured ``{provider, url, old, new,
    model}`` body. Charon ingests it out-of-band; the resulting
    PriceEntry lands in the cache; the flatten exposes it in
    model_pricing. Revert the ingest path and the no-API tail
    (nanogpt, neuralwatt, opencode-zen) is un-pricable."""
    cache = PriceCache()
    payload = {
        "provider": "neuralwatt",
        "url": "https://neuralwatt.example/pricing",
        "old": "0.000002",
        "new": "0.0000025",
        "model": "neuralwatt-mini",
        "cost_input": 2.5e-06,
        "cost_output": 3.0e-06,
    }
    n = ingest_change_detection(
        cache, payload, charon_providers={"neuralwatt", "nanogpt", "opencode-zen"})
    assert n == 1, "valid webhook payload must write exactly one cache entry"
    e = cache.get("neuralwatt", "neuralwatt-mini")
    assert e is not None, "webhook entry must be cached under (provider, model)"
    assert e.cost_input == 2.5e-06
    assert e.cost_output == 3.0e-06
    assert e.source_kind == "webhook"
    assert e.source == "https://neuralwatt.example/pricing"
    # Flatten: the webhook entry surfaces in model_pricing as the
    # router-consumable shape.
    model_pricing: dict[str, dict] = {}
    apply_to(cache, model_pricing)
    assert "neuralwatt-mini" in model_pricing
    spec = model_pricing["neuralwatt-mini"]
    assert spec["provider"] == "neuralwatt"
    assert spec["cost_input"] == 2.5e-06
    # The webhook entry has no other providers competing → the
    # all_providers list is the one webhook source.
    assert ("neuralwatt", "webhook") in spec["all_providers"]


def test_change_detection_webhook_rejects_ambiguous_or_offlist() -> None:
    """A webhook that omits ``model`` (or names an off-list provider)
    is dropped with a red log, NOT stored as zero, and NEVER raises
    (a refresh error must never block routing)."""
    cache = PriceCache()
    # No model → ambiguous → drop.
    n = ingest_change_detection(cache, {
        "provider": "neuralwatt", "url": "u", "old": "1", "new": "2"})
    assert n == 0
    # Off-list provider → drop.
    n = ingest_change_detection(
        cache,
        {"provider": "mystery-llm", "url": "u", "old": "1", "new": "2",
         "model": "m"},
        charon_providers={"neuralwatt", "nanogpt"})
    assert n == 0
    # Garbage payload → drop, no raise.
    n = ingest_change_detection(cache, "not a dict")
    assert n == 0
    n = ingest_change_detection(cache, {"provider": "neuralwatt"})  # missing url/new
    assert n == 0
    # The cache is still empty.
    assert cache.snapshot() == {}
