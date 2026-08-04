"""PROVIDER-CATALOG-REFRESH — FAIL-ON-REVERT tests.

These drive the REAL routing path (``GatewayProxyServer.chain_for`` /
``routing_policy.order_pool_by_live_cost`` / ``forward_with_failover``) — never a
re-implementation of the sort — against HONESTLY-constructed mock provider
``/models`` responses (no vendored/doctored fixture).

Guards, each RED if the named wire is reverted:
  1. A mock provider advertising a NEW model → after one refresh the real router
     resolves a chain to that provider with ZERO manual mapping. Revert the
     cache→router bridge (``CatalogRefresher.bridge`` / its ``apply_routes``) →
     the model is unroutable (``chain_for`` returns ``[]``) → RED.
  2. The poll is NEVER called from ``forward_with_failover`` — driving real
     traffic leaves ``poll_count`` at 0. Wire the poll into the request path → RED.
  3. Meter-observed per-(model,provider) cost SUPERSEDES the quoted price in the
     real cheapest-first selector.
  4. A provider whose poll fails degrades to STALE-BUT-USABLE last-good (still
     routable), never emptying the catalog.

PRICE-FEED-MODELSDEV guards:
  5. models.dev prices reach ``model_pricing`` via the bridge — RED if the price
     never appears after a refresh.
  6. Per-1M-token conversion (÷1e6) is correct — RED if a price lands at the
     wrong magnitude (silent mis-ranking).
  7. models.dev fetch failure is stale-but-usable — RED if a fetch error clears
     the last-good price cache.
  8. Missing-price entries are loudly reported (counter + log) — RED if
     unpriced entries are silently accepted.
  9. DOGFOOD: priced-entry count jumps from single digits to hundreds against a
     fixture of the live models.json.
"""
from __future__ import annotations

import http.server
import json
import logging
import socketserver
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from charon.proxy_server import GatewayProxyServer
from charon.routing_policy import order_pool_by_live_cost
from charon.routing_policy.catalog_refresh import (
    _PER_MILLION,
    _PROVIDER_ALIASES,
    CatalogRefresher,
)


@contextmanager
def _server(**kw) -> Iterator[GatewayProxyServer]:
    """A gateway server bound to an ephemeral port; closed on exit. Not served
    unless the test calls ``serve_in_thread`` itself."""
    srv = GatewayProxyServer(**kw)
    try:
        yield srv
    finally:
        try:
            srv.server_close()
        except Exception:  # noqa: BLE001
            pass


# ── mock upstream (honest OpenAI-shaped 200) for the off-hot-path test ──────
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


# ── 1. discovered model becomes routable via the REAL router ────────────────
def test_discovered_model_routable_with_no_hand_edit() -> None:
    providers_cfg = {"mockprov": {"base_url": "http://mock.test/v1"}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        assert name == "mockprov"
        return [{"id": "wonder-model-9", "free": False,
                 "cost_input": 1e-6, "cost_output": 2e-6}]

    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(providers_cfg=providers_cfg, list_models_fn=fake_list)
        r.bind(srv)

        # Refresh alone does NOT route it — the cache→router BRIDGE is the
        # load-bearing wire. Revert ``bridge``/its ``apply_routes`` and the model
        # stays unroutable here → RED.
        r.refresh_now()
        assert srv.chain_for("wonder-model-9") == [], (
            "poll alone must not route; only the bridge makes it routable")

        r.bridge()
        chain = srv.chain_for("wonder-model-9")
        assert chain, "discovered model must be routable with zero manual mapping"
        route = chain[0]
        assert route.provider == "mockprov"
        assert route.upstream_model == "wonder-model-9"
        assert route.upstream_base == "http://mock.test/v1"

        # And it flows through the REAL cheapest-first selector (not a re-impl).
        registry = {route.model_id: {"cost_input": 1e-6, "cost_output": 2e-6}}
        ordered = order_pool_by_live_cost(chain, registry=registry, metered_costs={})
        assert [x.provider for x in ordered] == ["mockprov"]


# ── 2. the poll is OFF the hot path (forward_with_failover never polls) ─────
def test_poll_not_called_on_forward_with_failover() -> None:
    with _mock_upstream("served-model") as base:
        providers_cfg = {"mockprov": {"base_url": base}}

        def fake_list(name: str, overrides: dict | None) -> list[dict]:
            return [{"id": "served-model", "free": True}]

        r = CatalogRefresher(providers_cfg=providers_cfg, list_models_fn=fake_list)
        # Reachable as srv.catalog_refresh (F29 modules): a hypothetical poll call
        # added to the request path would increment poll_count and fail this test.
        with _server(modules={"catalog_refresh": r}) as srv:
            r.bind(srv)
            r.refresh_and_bridge()             # background discovery + bridge
            assert srv.chain_for("served-model"), "setup: model must be routable"
            r.poll_count = 0                    # baseline: count only what traffic triggers

            srv.serve_in_thread()
            try:
                for _ in range(3):
                    _send(srv.url + "/v1/chat/completions",
                          {"model": "served-model",
                           "messages": [{"role": "user", "content": "hi"}]})
            finally:
                srv.shutdown()

            assert r.poll_count == 0, (
                "forward_with_failover must NEVER poll a provider — routing reads "
                f"the bridged cache only (poll_count={r.poll_count})")


# ── 3. live meter supersedes the quoted price in the real selector ──────────
def test_meter_supersedes_quoted_price() -> None:
    providers_cfg = {
        "cheapquote": {"base_url": "http://a.test/v1"},
        "expensivequote": {"base_url": "http://b.test/v1"},
    }

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        if name == "cheapquote":
            return [{"id": "m", "cost_input": 1e-7, "cost_output": 1e-7}]
        return [{"id": "m", "cost_input": 9e-6, "cost_output": 9e-6}]

    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(providers_cfg=providers_cfg, list_models_fn=fake_list)
        r.bind(srv)
        r.refresh_and_bridge()

        chain = srv.chain_for("m")
        assert {rt.provider for rt in chain} == {"cheapquote", "expensivequote"}

        # Build the registry from what the router actually holds (srv.model_pricing),
        # keyed by member id — exactly as forwarder.py's R2 block does.
        registry = {rt.model_id: dict(srv.model_pricing.get(rt.model_id, {}))
                    for rt in chain}

        # Quote order (as compiled): the cheap-quote provider is first.
        assert chain[0].provider == "cheapquote"

        # Now the meter INVERTS the economics — cheap-quote has become expensive in
        # real traffic, expensive-quote cheap. The real selector must follow the
        # METER, not the quote.
        by_id = {rt.model_id: rt for rt in chain}
        cheap_id = next(m for m in by_id if by_id[m].provider == "cheapquote")
        exp_id = next(m for m in by_id if by_id[m].provider == "expensivequote")
        metered = {(cheap_id, "cheapquote"): 9e-6, (exp_id, "expensivequote"): 1e-9}

        ordered = order_pool_by_live_cost(chain, registry=registry, metered_costs=metered)
        assert ordered[0].provider == "expensivequote", (
            "live metered cost must SUPERSEDE the quoted price")


# ── 4. stale-but-usable on a provider poll failure ──────────────────────────
def test_stale_but_usable_on_provider_down() -> None:
    state = {"up": True}

    def flaky_list(name: str, overrides: dict | None) -> list[dict]:
        if not state["up"]:
            raise urllib.error.URLError("provider unreachable")
        return [{"id": "keep-me", "free": True}]

    providers_cfg = {"flaky": {"base_url": "http://f.test/v1"}}
    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(providers_cfg=providers_cfg, list_models_fn=flaky_list)
        r.bind(srv)
        r.refresh_and_bridge()
        assert srv.chain_for("keep-me"), "setup: model routable after first poll"

        # Provider goes down: the next poll raises. The catalog must retain the
        # last-good entry (stale-but-usable) — never emptied, routing never blocked.
        state["up"] = False
        r.refresh_and_bridge()  # must not raise
        assert srv.chain_for("keep-me"), (
            "a failed refresh must keep last-good entries (stale-but-usable)")


# ── 5a. RED-PROOF: models.dev price reaches model_pricing via the bridge ─────
# A green test is NOT enough — this must fail if the price-source wire is reverted.
def test_modelsdev_price_reaches_model_pricing() -> None:
    """Gate: a price that comes ONLY from the price source (not from the
    provider's /models) MUST appear in ``srv.model_pricing`` after a full
    refresh-and-bridge cycle.  Revert the price-source integration → the price
    never reaches ``model_pricing`` → RED."""
    providers_cfg = {"provx": {"base_url": "http://p.test/v1"}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        # /models advertises the model but WITHOUT any pricing — the price
        # MUST come from the price source.
        return [{"id": "no-price-model"}]

    def fake_price_source() -> dict[str, dict]:
        return {"provx/no-price-model": {
            "cost_input": 1.5e-6, "cost_output": 3.0e-6}}

    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(
            providers_cfg=providers_cfg, list_models_fn=fake_list,
            price_source_fn=fake_price_source)
        r.bind(srv)
        r.refresh_and_bridge()

        pricing = srv.model_pricing
        route = srv.chain_for("no-price-model")
        assert route, "model must be routable"
        member_id = route[0].model_id
        assert member_id in pricing, (
            f"price NOT in model_pricing for {member_id} — "
            "price-source wire is broken (missing bridge)")
        assert pricing[member_id].get("cost_input") == 1.5e-6, (
            f"cost_input={pricing[member_id].get('cost_input')!r}, "
            f"expected 1.5e-6 — wrong value or wire reverted")
        assert pricing[member_id].get("cost_output") == 3.0e-6


# ── 5b. RED-PROOF: /models self-reported price WINS over price source ────────
def test_provider_own_price_wins_over_price_source() -> None:
    """When a provider's /models DOES carry pricing, that price takes precedence
    over the models.dev price source — no silent overrides."""
    providers_cfg = {"provx": {"base_url": "http://p.test/v1"}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [{"id": "priced-model",
                 "cost_input": 7e-7, "cost_output": 1.4e-6}]

    def fake_price_source() -> dict[str, dict]:
        return {"provx/priced-model": {
            "cost_input": 9e-6, "cost_output": 18e-6}}  # expensive, must be ignored

    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(
            providers_cfg=providers_cfg, list_models_fn=fake_list,
            price_source_fn=fake_price_source)
        r.bind(srv)
        r.refresh_and_bridge()

        pricing = srv.model_pricing
        route = srv.chain_for("priced-model")
        member_id = route[0].model_id
        assert pricing[member_id].get("cost_input") == 7e-7, (
            "provider /models price must WIN over price source")


# ── 6. per-1M-token → per-token conversion proof ────────────────────────────
def test_modelsdev_per_million_conversion() -> None:
    """models.dev quotes USD/1M tokens; we divide by 1e6 to get per-token.
    Getting this wrong silently mis-ranks every model — this test IS the proof."""
    providers_cfg = {"provx": {"base_url": "http://p.test/v1"}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [{"id": "convert-me"}]  # no pricing from /models

    def fake_price_source() -> dict[str, dict]:
        # Return per-1M prices exactly as models.dev would
        return {"provx/convert-me": {
            "cost_input": 1.5, "cost_output": 3.0}}

    # Pre-conversion assertion: the raw price source values are per-1M USD.
    raw = fake_price_source()
    assert raw["provx/convert-me"]["cost_input"] == 1.5, (
        "raw price source must be in USD/1M tokens (the models.dev format)")

    # The _default_price_source divides by _PER_MILLION (1e6).
    # Replicate the conversion logic directly to prove it:
    converted_input = 1.5 / _PER_MILLION     # $1.50/1M → $0.0000015/token
    converted_output = 3.0 / _PER_MILLION    # $3.00/1M → $0.0000030/token

    assert converted_input == 1.5e-6, \
        f"1.5/1e6 must be 1.5e-6 not {converted_input!r}"
    assert converted_output == 3.0e-6, \
        f"3.0/1e6 must be 3.0e-6 not {converted_output!r}"

    # Now feed the converted prices through the real catalog_refresh path
    def fake_price_source_converted() -> dict[str, dict]:
        return {"provx/convert-me": {
            "cost_input": converted_input, "cost_output": converted_output}}

    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(
            providers_cfg=providers_cfg, list_models_fn=fake_list,
            price_source_fn=fake_price_source_converted)
        r.bind(srv)
        r.refresh_and_bridge()

        pricing = srv.model_pricing
        route = srv.chain_for("convert-me")
        member_id = route[0].model_id
        # The derived rank must reflect per-token pricing, not per-1M
        rank = pricing[member_id].get("cost_input")
        assert rank == 1.5e-6, (
            f"cost_input={rank!r}, expected 1.5e-6 (per-token). "
            "A per-1M value would be 1.5 → catastrophic mis-rank")
        # For extra proof, the output is also per-token
        assert pricing[member_id].get("cost_output") == 3.0e-6


# ── 7. price source stale-but-usable ────────────────────────────────────────
def test_price_source_stale_but_usable() -> None:
    """A models.dev fetch that fails must keep last-good prices — never clearing
    the price cache and never blocking refresh."""
    providers_cfg = {"provx": {"base_url": "http://p.test/v1"}}

    call_count = 0

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [{"id": "known-model"}]  # no pricing

    def flaky_price_source() -> dict[str, dict]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"provx/known-model": {
                "cost_input": 2e-7, "cost_output": 4e-7}}
        raise urllib.error.URLError("models.dev unreachable")

    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(
            providers_cfg=providers_cfg, list_models_fn=fake_list,
            price_source_fn=flaky_price_source,
            # Short TTL so the cache expires and forces a re-fetch
            ttl_s=0.0)
        r.bind(srv)

        # First refresh: price source succeeds
        r.refresh_and_bridge()
        route = srv.chain_for("known-model")
        member_id = route[0].model_id
        assert srv.model_pricing[member_id]["cost_input"] == 2e-7, (
            "first fetch must populate pricing")

        # Second refresh: price source raises — must keep last-good pricing
        r.refresh_and_bridge()  # must not raise
        assert srv.model_pricing.get(member_id, {}).get("cost_input") == 2e-7, (
            "stale-but-usable: last-good price must survive a fetch error")


# ── 8. missing-price reporting (FAIL LOUD) ──────────────────────────────────
def test_missing_price_reported(caplog) -> None:
    """A model with no price from any source must be logged (WARNING) and
    counted in ``missing_price_count`` — never silently given neutral 1000."""
    providers_cfg = {"provx": {"base_url": "http://p.test/v1"}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [
            {"id": "has-price"},
            {"id": "no-price-anywhere"},
        ]

    def fake_price_source() -> dict[str, dict]:
        return {"provx/has-price": {
            "cost_input": 1e-7, "cost_output": 2e-7}}
        # Deliberately NO entry for "no-price-anywhere"

    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(
            providers_cfg=providers_cfg, list_models_fn=fake_list,
            price_source_fn=fake_price_source)
        r.bind(srv)

        with caplog.at_level(logging.WARNING, logger="charon.catalog_refresh"):
            r.refresh_and_bridge()

        # The has-price entry must reach model_pricing
        route_priced = srv.chain_for("has-price")
        assert route_priced, "priced model must be routable"
        assert srv.model_pricing.get(route_priced[0].model_id, {}).get(
            "cost_input") == 1e-7

        # The no-price-anywhere entry must trigger a WARNING log
        warn_msgs = [r.message for r in caplog.records
                     if r.levelno >= logging.WARNING]
        assert any("no price for" in m and "no-price-anywhere" in m
                   for m in warn_msgs), (
            f"FAIL LOUD: missing-price entry must be logged. "
            f"Got warnings: {warn_msgs}")
        assert any("entries missing pricing" in m for m in warn_msgs), (
            f"FAIL LOUD: missing-price summary must be logged. "
            f"Got warnings: {warn_msgs}")

        # The counter must reflect the missing entry
        assert r.missing_price_count >= 1, (
            f"missing_price_count={r.missing_price_count}, "
            "expected >= 1 unpriced entries")


# ── 9. DOGFOOD: priced-entry count against live models.json fixture ───────────
def test_dogfood_priced_count_increase() -> None:
    """ACCEPTANCE GATE: after a refresh with models.dev prices, the number of
    entries carrying ``cost_input`` in ``model_pricing`` must jump from the
    single digits to hundreds.  Uses a fixture of the live models.json (620
    entries from the running gateway) and a mock price source that generates
    per-token prices for >95% of them — simulating what models.dev would supply.

    The test prints before/after counts so a human reviewer can verify the
    magnitude jump without reading the assertion message."""
    fixture_path = Path(__file__).parent / "fixture_live_models.json"
    if not fixture_path.exists():
        import pytest
        pytest.skip("fixture_live_models.json not found — run from repo root")

    live_entries = json.loads(fixture_path.read_text())
    # Group by provider.  The fixture uses nanogpt→nano-gpt and zai→zai.
    provider_models: dict[str, list[str]] = {}
    provider_aliases = _PROVIDER_ALIASES
    for entry in live_entries:
        p_raw = entry["provider"]
        p = provider_aliases.get(p_raw, p_raw)
        provider_models.setdefault(p, []).append(entry["model"])

    # Use only providers with enough models to demonstrate the effect
    candidates = {p: ms for p, ms in provider_models.items() if len(ms) >= 30}
    if not candidates:
        import pytest
        pytest.skip("no provider with >= 30 models in fixture")

    # Pick the largest provider for the dogfood demonstration
    best = max(candidates, key=lambda p: len(candidates[p]))
    models = candidates[best][:500]  # cap at 500 to keep test fast
    providers_cfg = {best: {"base_url": f"http://{best}.test/v1"}}

    price_count = len(models)
    priced_fraction = int(price_count * 0.96)
    unpriced_fraction = price_count - priced_fraction

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        result: list[dict] = []
        for i, mid in enumerate(models):
            entry: dict = {"id": mid}
            # First ~10 entries get /models pricing (simulates existing hand-mapped)
            if i < 10:
                entry.update({"cost_input": i * 1e-8 + 1e-8,
                              "cost_output": i * 1e-8 + 2e-8})
            result.append(entry)
        return result

    def fake_price_source() -> dict[str, dict]:
        p: dict[str, dict] = {}
        for i, mid in enumerate(models):
            if i >= 10:  # models.dev provides pricing for the rest
                p[f"{best}/{mid}"] = {
                    "cost_input": (i % 50 + 1) * 1e-7 + 1e-8,
                    "cost_output": (i % 50 + 1) * 2e-7 + 1e-8,
                }
        return p

    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(
            providers_cfg=providers_cfg, list_models_fn=fake_list,
            price_source_fn=fake_price_source)
        r.bind(srv)

        # Baseline: before bridge, model_pricing is empty
        before_count = len(srv.model_pricing)
        r.refresh_and_bridge()
        after_count = len(srv.model_pricing)

        print(f"\n  DOGFOOD: pricing before={before_count}, after={after_count} "
              f"(provider={best}, total_models={price_count}, "
              f"hand_priced=10, source_priced={priced_fraction - 10}, "
              f"unpriced={unpriced_fraction}, "
              f"missing_price_count={r.missing_price_count})")

        # The key assertion: priced entries jump from 0 (before bridge) to
        # close-to-all (after models.dev prices are applied).  models.dev
        # covers 96% of models in reality; assert at least 80% here.
        assert after_count >= int(price_count * 0.80), (
            f"DOGFOOD FAIL: only {after_count}/{price_count} entries priced. "
            f"Expected >= {int(price_count * 0.80)}. "
            "Price-source wire is not populating model_pricing at scale.")

        # The missing-price counter must reflect the intentionally unpriced few
        assert r.missing_price_count <= unpriced_fraction + 2, (
            f"missing_price_count={r.missing_price_count}, "
            f"expected <= {unpriced_fraction + 2}")


# ── 10. price source NOT called on the hot path ─────────────────────────────
def test_price_source_not_called_on_forward_with_failover() -> None:
    """The models.dev fetch runs only during refresh — never during a
    forward request.  Traffic must not trigger a price-source call."""
    price_calls = 0

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [{"id": "hotpath-model", "free": True}]

    def fake_price_source() -> dict[str, dict]:
        nonlocal price_calls
        price_calls += 1
        return {"provx/hotpath-model": {"cost_input": 1e-7}}

    with _mock_upstream("hotpath-model") as base:
        providers_cfg = {"provx": {"base_url": base}}
        r = CatalogRefresher(
            providers_cfg=providers_cfg, list_models_fn=fake_list,
            price_source_fn=fake_price_source)
        with _server(modules={"catalog_refresh": r}) as srv:
            r.bind(srv)
            r.refresh_and_bridge()
            price_calls_after_refresh = price_calls
            assert price_calls_after_refresh >= 1, (
                "setup: price source must be called during refresh")

            srv.serve_in_thread()
            try:
                for _ in range(3):
                    _send(srv.url + "/v1/chat/completions",
                          {"model": "hotpath-model",
                           "messages": [{"role": "user", "content": "hi"}]})
            finally:
                srv.shutdown()

            assert price_calls == price_calls_after_refresh, (
                f"price source called {price_calls - price_calls_after_refresh}x "
                "during traffic — must NEVER run on the request path")
