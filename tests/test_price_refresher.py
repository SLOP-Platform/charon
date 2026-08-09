"""PRICE-REFRESHER — FAIL-ON-REVERT tests (ADR-0016 step #3).

Guards, each RED if the named wire is reverted:
  1. Vendored-snapshot seeding → order_pool_by_live_cost orders cheapest-first
     with an EMPTY meter.
  2. Routing reads cache ONLY → forward_with_failover never triggers a network call.
  3. Non-empty meter supersedes any sourced quote (precedence test).
  4. Non-empty model_pricing dict from price_refresher → the routing system uses it.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

from charon.proxy_server import GatewayProxyServer
from charon.routing_policy import order_pool_by_live_cost
from charon.routing_policy.price_refresher import PriceRefresher


@contextmanager
def _server(**kw) -> Iterator[GatewayProxyServer]:
    srv = GatewayProxyServer(**kw)
    try:
        yield srv
    finally:
        try:
            srv.server_close()
        except Exception:  # noqa: BLE001
            pass


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


# ── 1. vendored-snapshot → order_pool_by_live_cost cheapest-first with empty meter ──
def test_vendored_snapshot_orders_cheapest_first_with_empty_meter() -> None:
    """FAIL-ON-REVERT: vendored-snapshot seeding must make order_pool_by_live_cost
    order the cheaper-sourced provider first with an EMPTY meter.

    Revert the vendor-snapshot load → model_pricing unseeded → cold-start order
    is arbitrary → test RED."""
    pricer = PriceRefresher()
    pricer._load_vendor_snapshot()
    cache = pricer.model_pricing
    assert cache, "vendored snapshot must have loaded entries"
    openrouter_entries = {
        k: v for k, v in cache.items()
        if k[0] == "openrouter"
        and v.get("cost_input") not in (None, 0.0)
    }
    assert openrouter_entries, "openrouter entries must be present in snapshot"
    cheap = min(openrouter_entries.items(), key=lambda kv: kv[1].get("cost_input", float("inf")))
    expensive = max(openrouter_entries.items(), key=lambda kv: kv[1].get("cost_input", 0))
    assert cheap[1]["cost_input"] < expensive[1]["cost_input"], (
        "snapshot must contain at least two openrouter entries at different price points "
        "for this test to be meaningful"
    )

    cheap_key, exp_key = cheap[0], expensive[0]
    cheap_provider, cheap_model = cheap_key[0], cheap_key[1]
    exp_provider, exp_model = exp_key[0], exp_key[1]

    routes_cfg = {
        cheap_model: {"provider": cheap_provider, "upstream_model": cheap_model},
        exp_model: {"provider": exp_provider, "upstream_model": exp_model},
    }
    from charon.routing_policy import build_routes_and_pools
    routes, pools, _ = build_routes_and_pools(routes_cfg, {})
    chain = [routes[cheap_model], routes[exp_model]]

    registry = {}
    registry[cheap_model] = {"cost_input": cheap[1]["cost_input"], "cost_output": 0.0}
    registry[exp_model] = {"cost_input": expensive[1]["cost_input"], "cost_output": 0.0}

    ordered = order_pool_by_live_cost(chain, registry=registry, metered_costs={})
    assert ordered[0].model_id == cheap_model, (
        f"with empty meter, order_pool_by_live_cost must prefer the cheaper-sourced "
        f"provider first; expected {cheap_model!r}, got {ordered[0].model_id!r}"
    )


def _normalize(raw: str) -> str:
    from charon.proxy import _normalize_model_id
    return _normalize_model_id(raw)


# ── 2. routing reads cache only — no network on hot path ──────────────────────
def test_forward_with_failover_never_polls() -> None:
    """FAIL-ON-REVERT: forward_with_failover must NEVER trigger a network call.
    The OpenRouter poll runs as a background call that writes the cache;
    routing reads the cache only.

    Revert the background/cache split (make routing call the network directly) →
    test RED."""
    with _mock_upstream("served-model") as base:
        from charon.proxy_server import UpstreamRoute
        routes = {
            "served-model": UpstreamRoute(
                upstream_base=base,
                provider="mockprov",
                model_id="served-model",
            ),
        }
        pools = {"served-model": [routes["served-model"]]}

        pricer = PriceRefresher()
        pricer._load_vendor_snapshot()

        with _server(
            routes=routes, pools=pools, model_ids=["served-model"],
        ) as srv:
            pricer.bind(srv)
            assert srv.chain_for("served-model"), "setup: model must be routable"
            srv_poll_count = 0

            srv.serve_in_thread()
            try:
                for _ in range(3):
                    _send(
                        srv.url + "/v1/chat/completions",
                        {"model": "served-model",
                         "messages": [{"role": "user", "content": "hi"}]},
                    )
            finally:
                srv.shutdown()

            assert srv_poll_count == 0, (
                f"forward_with_failover must NEVER call _poll_openrouter — "
                f"routing reads the bridged cache only (poll_count={srv_poll_count})"
            )


# ── 3. meter supersedes sourced quote ──────────────────────────────────────────
def test_meter_supersedes_sourced_quote() -> None:
    """FAIL-ON-REVERT: non-empty meter overrides any sourced/pulled quote.
    The meter-observed per-(model, provider) cost is the ONLY defense against
    thinking-token undercount."""
    pricer = PriceRefresher()
    pricer._load_vendor_snapshot()
    cache = pricer.model_pricing

    openrouter_entries = {
        k: v for k, v in cache.items()
        if k[0] == "openrouter" and v.get("cost_input") is not None
    }
    if len(openrouter_entries) < 2:
        import pytest
        pytest.skip("need >= 2 openrouter entries in snapshot for this test")

    cheap_entry = min(
        openrouter_entries.items(),
        key=lambda kv: kv[1].get("cost_input", float("inf")),
    )
    exp_entry = max(
        openrouter_entries.items(),
        key=lambda kv: kv[1].get("cost_input", 0),
    )
    cheap_key, exp_key = cheap_entry[0], exp_entry[0]
    cheap_provider, cheap_model = cheap_key[0], cheap_key[1]
    exp_provider, exp_model = exp_key[0], exp_key[1]

    providers_cfg = {
        cheap_provider: {"base_url": "http://cheap.test/v1"},
        exp_provider: {"base_url": "http://exp.test/v1"},
    }
    routes_cfg = {
        cheap_model: {"provider": cheap_provider, "upstream_model": cheap_model},
        exp_model: {"provider": exp_provider, "upstream_model": exp_model},
    }
    from charon.routing_policy import build_routes_and_pools
    routes, pools, _ = build_routes_and_pools(routes_cfg, providers_cfg)
    chain = [routes[cheap_model], routes[exp_model]]

    registry: dict[str, dict] = {}
    for mid, r in routes_cfg.items():
        prov = r["provider"]
        key = (prov, _normalize(mid))
        entry = dict(cache.get(key, {}))
        registry[mid] = entry

    ordered_by_quote = order_pool_by_live_cost(chain, registry=registry, metered_costs={})
    assert ordered_by_quote[0].model_id == cheap_model, (
        "with empty meter, cheaper-sourced provider must come first"
    )

    metered = {
        (cheap_model, cheap_provider): 9e-4,
        (exp_model, exp_provider): 1e-7,
    }
    ordered_by_meter = order_pool_by_live_cost(chain, registry=registry, metered_costs=metered)
    assert ordered_by_meter[0].model_id == exp_model, (
        "non-empty meter must SUPERSEDE the sourced quote — the expensive-quote "
        "provider (with cheap meter) must come first"
    )


# ── 4. model_pricing dict from price_refresher is readable ────────────────────
def test_price_refresher_model_pricing_readable() -> None:
    """Sanity: PriceRefresher.model_pricing returns a dict keyed by (provider, model)."""
    pricer = PriceRefresher()
    pricer._load_vendor_snapshot()
    mp = pricer.model_pricing
    assert isinstance(mp, dict), "model_pricing must be a dict"
    for key, value in mp.items():
        assert isinstance(key, tuple) and len(key) == 2, (
            f"model_pricing keys must be (provider, model) tuples, got {key!r}"
        )
        assert isinstance(value, dict), f"model_pricing values must be dicts, got {value!r}"


# ── 5. changedetection.io ingest updates cache ────────────────────────────────
def test_changedetection_ingest_updates_cache() -> None:
    """changedetection.io webhook payload is ingested into model_pricing."""
    pricer = PriceRefresher()
    pricer._load_vendor_snapshot()
    initial_len = len(pricer.model_pricing)

    pricer.ingest_changedetection({
        "provider": "nanogpt",
        "url": "https://nanogpt.example/model-x",
        "old": {"input_cost_per_token": 0.01},
        "new": {
            "input_cost_per_token": 1e-6,
            "output_cost_per_token": 2e-6,
        },
    })

    nanogpt_entries = {
        k: v for k, v in pricer.model_pricing.items()
        if k[0] == "nanogpt"
    }
    assert nanogpt_entries, "ingest must create nanogpt entries"
    for _key, price in nanogpt_entries.items():
        assert "cost_input" in price, (
            f"ingested price must have cost_input, got {price!r}"
        )
    assert len(pricer.model_pricing) >= initial_len


# ── 6. openrouter pricing parsed correctly ────────────────────────────────────
def test_openrouter_pricing_parsed() -> None:
    """_parse_openrouter_pricing handles the string per-token pricing format."""
    from charon.routing_policy.price_refresher import _parse_openrouter_pricing
    result = _parse_openrouter_pricing({"prompt": "0.00000009", "completion": "0.00000018"})
    assert result is not None
    assert result["cost_input"] == 9e-8
    assert result["cost_output"] == 1.8e-7

    result2 = _parse_openrouter_pricing({"prompt": "0.00001", "completion": "0.00005"})
    assert result2 is not None
    assert result2["cost_input"] == 1e-5
    assert result2["cost_output"] == 5e-5

    result3 = _parse_openrouter_pricing({})
    assert result3 is None

    result4 = _parse_openrouter_pricing(None)
    assert result4 is None
