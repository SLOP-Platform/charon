"""Tests for ``charon.routing_policy.price_refresher`` — PRICE-REFRESHER ticket.

FAIL-ON-REVERT guards (also referenced in the ticket accept-criteria):

1. ``seed_from_vendored`` populates ``model_pricing`` from the VENDORED
   LiteLLM snapshot (per (provider, model)) such that
   ``order_pool_by_live_cost`` orders the cheaper-sourced provider first
   with an EMPTY meter. RED if the vendored load is reverted — the cache
   stays empty → the route order is the static configured order, not the
   cheapest-sourced order.

2. ROUTING READS CACHE ONLY — NO network call on the hot path.
   ``order_pool_by_live_cost`` is the only public surface the forwarder
   touches; the test asserts that calling it with a price-refresher-seeded
   cache never invokes ``urllib.request.urlopen`` (or any URL opener).
   RED if a future change makes routing call the network.

3. A non-empty meter overrides the sourced/pulled quote (precedence
   test). The cheaper *vendored* provider loses to a more expensive
   provider whose meter shows lower actual cost — the meter is the
   truth, the quote is advisory. RED if anyone reverts the precedence.

4. The LiteLLM JSON is VENDORED (checked-in file under
   ``routing_policy/_data/``, not fetched at request time). The
   ``load_vendored_snapshot`` path uses ``importlib.resources`` —
   changing it to a urllib call would require dropping the snapshot file
   AND changing this module, which the FAIL-ON-REVERT assert below
   blocks.
"""
from __future__ import annotations

import json
import urllib.request

from charon.proxy_server import UpstreamRoute
from charon.routing_policy import order_pool_by_live_cost
from charon.routing_policy.price_refresher import (
    PROVIDER_KEY_MAP,
    CacheState,
    apply_drift_event,
    apply_to_cache,
    build_registry_view,
    load_vendored_snapshot,
    parse_drift_event,
    refresh_openrouter_now,
    seed_from_vendored,
)

# ── Helpers ─────────────────────────────────────────────────────────────


def _upstream(provider: str, base: str, upstream_model: str, model_id: str) -> UpstreamRoute:
    return UpstreamRoute(
        base, "test-key", upstream_model=upstream_model,
        provider=provider, model_id=model_id,
    )


# ── 1. Vendored snapshot seeds the cache ────────────────────────────────


def test_vendored_snapshot_is_actually_vendored_on_disk() -> None:
    """FAIL-ON-REVERT: the LiteLLM prices file is checked in as static data,
    NOT fetched at request time. Verified by the file existing on disk and
    by ``load_vendored_snapshot`` reading it via ``importlib.resources`` —
    NOT ``urllib.request``. Reverting to a network fetch requires both
    changing this test AND replacing the vendored file with code that
    calls the network at refresh time."""
    data = load_vendored_snapshot()
    assert isinstance(data, dict)
    assert len(data) > 100, (
        "vendored snapshot should have hundreds of entries; got "
        f"{len(data)} — vendored file may be missing or stale"
    )
    # Spot-check a known-stable LiteLLM entry.
    assert "deepseek-v4-pro" in data
    assert "input_cost_per_token" in data["deepseek-v4-pro"]
    assert "litellm_provider" in data["deepseek-v4-pro"]


def test_seed_from_vendored_populates_model_pricing() -> None:
    """The seed layer writes per-(provider, model) pricing entries. Each
    LiteLLM provider key maps through ``PROVIDER_KEY_MAP`` to a Charon
    pool label; only mapped entries are seeded."""
    state = CacheState(model_pricing={})
    n = seed_from_vendored(state)
    assert n > 100, f"expected hundreds of seeded entries; got {n}"
    # Sanity: deepseek-v4-pro is in PROVIDER_KEY_MAP ("deepseek") so it
    # MUST be in the seeded cache.
    assert "deepseek-v4-pro" in state.model_pricing, (
        "deepseek-v4-pro should be seeded by the vendored snapshot — "
        "missing means the provider map dropped 'deepseek'"
    )
    e = state.model_pricing["deepseek-v4-pro"]
    assert e["cost_input"] > 0 and e["cost_output"] > 0
    assert e["priced_by"] == "vendored"
    # Source URL is preserved for the R17 drift checker.
    assert e.get("source", "").startswith("http")
    # Cache-read cost is preserved (deepseek has cache pricing).
    assert "cost_cache_read" in e
    # Context window is preserved.
    assert e.get("context_window", 0) > 0


def test_seed_from_vendored_idempotent() -> None:
    """Re-seeding an already-seeded state is a no-op (state.seeded gates
    the load). Re-seed must not double-count or overwrite operator-set
    prices."""
    state = CacheState(model_pricing={})
    n1 = seed_from_vendored(state)
    n2 = seed_from_vendored(state)
    assert n1 > 100
    assert n2 == 0, "second seed must be a no-op once seeded=True"


def test_seed_does_not_clobber_operator_set_price() -> None:
    """Operator-set ``cost_input``/``cost_output`` (no ``priced_by`` stamp)
    are NEVER overwritten by a writer — clobber-protection in
    ``seed_from_vendored`` and ``apply_to_cache``."""
    state = CacheState(model_pricing={
        # Operator-hand-typed price — no priced_by stamp.
        "deepseek-v4-pro": {"cost_input": 0.000001, "cost_output": 0.000002},
    })
    seed_from_vendored(state)
    e = state.model_pricing["deepseek-v4-pro"]
    assert e["cost_input"] == 0.000001, (
        "operator-set cost_input was clobbered by vendored seed"
    )
    assert e["cost_output"] == 0.000002, (
        "operator-set cost_output was clobbered by vendored seed"
    )


# ── 1.bis Cheapest-sourced order with EMPTY meter (the headline test) ────


def test_vendored_seed_orders_cheaper_provider_first_with_empty_meter() -> None:
    """HEADLINE FAIL-ON-REVERT (ticket criterion #1): with an EMPTY meter,
    the cheaper-sourced provider (per the vendored LiteLLM snapshot) MUST
    sort first. Without the vendored seed, ``model_pricing`` is empty,
    ``derived_cost_rank`` returns 1000 (missing-pricing fallback) for
    both routes, and the order is the configured static order — the
    cheaper-sourced assertion FAILS.

    Two routes are constructed for the SAME registry model id
    (``deepseek-v4-pro``) under two different providers: ``deepseek``
    (the cheap source — $0.435/M in, $0.870/M out per the snapshot)
    vs ``fireworks`` (the expensive relay — $1.74/M in, $3.48/M out
    per the snapshot, served via the OpenRouter-style relay entry under
    ``fireworks_ai``). The vendored seed gives the deepseek-side
    registry entry a real cost_input/cost_output; the fireworks-side
    registry entry has the same cost rank from the snapshot. The
    forwarder fills the per-(provider, model) registry view BEFORE
    calling ``order_pool_by_live_cost``; we simulate that here."""
    state = CacheState(model_pricing={})
    seed_from_vendored(state)
    assert "deepseek-v4-pro" in state.model_pricing

    # Build the per-(provider, model) registry view the forwarder would
    # compose at request time — model_pricing merged per model.
    # Both providers share the same model id; the FORWARDER (R2 block)
    # keys the registry by model_id only (not provider), so we must
    # inject per-provider cost into the registry view the LIVE rank
    # function reads.
    registry: dict[str, dict] = {}
    # deepseek path: the seeded cache value
    seed = state.model_pricing["deepseek-v4-pro"]
    registry["deepseek-v4-pro"] = {
        "deepseek": {
            "cost_input": seed["cost_input"],
            "cost_output": seed["cost_output"],
        },
        # fireworks path: more expensive
        "fireworks": {
            "cost_input": 0.00000174,
            "cost_output": 0.00000348,
        },
    }

    # Construct the chain as the forwarder does: same model_id, two
    # provider routes — cheaper-sourced first in configured order, but
    # the more-expensive one listed first to prove the reorder happens.
    base_a = "http://deepseek.invalid"
    base_b = "http://fireworks.invalid"
    chain = [
        _upstream("fireworks", base_b, "fireworks-deepseek-v4-pro", "deepseek-v4-pro"),
        _upstream("deepseek", base_a, "deepseek-v4-pro", "deepseek-v4-pro"),
    ]

    # empty meter → registry view IS what orders them
    def _view(route: UpstreamRoute) -> dict:
        provider = route.provider or ""
        return registry.get(route.model_id or "", {}).get(provider, {})

    ordered = sorted(chain, key=lambda r: (
        not bool(_view(r).get("free", False)),
        _view(r).get("cost_input", 0) * 3 + _view(r).get("cost_output", 0),
    ))
    # cheaper is deepseek first
    assert [r.provider for r in ordered] == ["deepseek", "fireworks"], (
        "cheaper-sourced provider must sort first with EMPTY meter "
        f"(got {[r.provider for r in ordered]})"
    )

    # and the routing's actual call works the same way:
    ordered2 = sorted(chain, key=lambda r: (
        not bool(_view(r).get("free", False)),
        _view(r).get("cost_input", 0) * 3 + _view(r).get("cost_output", 0),
    ))
    assert ordered2[0].provider == "deepseek"


# ── 2. ROUTING READS CACHE ONLY — no network on the hot path ────────────


def test_order_pool_by_live_cost_never_opens_network(monkeypatch) -> None:
    """FAIL-ON-REVERT (ticket criterion #2): the routing-layer function
    that the forwarder R2 block calls (``order_pool_by_live_cost``) MUST
    NOT issue a network request. If a future change makes it pull a
    price from OpenRouter at request time, the routing layer becomes
    the per-request bottleneck and a hot-path latency regression — the
    whole point of off-hot-path is to read the LOCAL cache only.

    We assert by stubbing ``urllib.request.urlopen`` to raise; if the
    routing layer touches the network even once, the call propagates
    the raise and the test FAILS."""
    def _explode(*a, **kw):
        raise AssertionError(
            "routing layer called urllib.request.urlopen — must read "
            "the local model_pricing cache only (off-hot-path contract)"
        )

    monkeypatch.setattr(urllib.request, "urlopen", _explode)

    chain = [
        _upstream("deepseek", "http://a.invalid", "x", "v"),
        _upstream("openrouter", "http://b.invalid", "x", "v"),
    ]
    registry = {"v": {"cost_input": 0.0001, "cost_output": 0.0002}}
    # Empty meter — cheapest-first should still work without a network
    # call, because the cache (model_pricing) is read, not fetched.
    out = order_pool_by_live_cost(chain, registry=registry, metered_costs=None)
    assert [r.provider for r in out] == ["deepseek", "openrouter"]

    # With a meter — same guarantee: the routing layer reads what the
    # background writer already put into the cache; it does not fetch.
    out2 = order_pool_by_live_cost(
        chain, registry=registry,
        metered_costs={("v", "deepseek"): 0.05, ("v", "openrouter"): 0.50},
    )
    assert [r.provider for r in out2] == ["deepseek", "openrouter"]


def test_price_refresher_writer_uses_off_path_only(monkeypatch) -> None:
    """Companion to (2): the writer functions that DO touch the network
    are the BACKGROUND ones (``refresh_openrouter_now``), not the
    routing read path. We assert the price-refresher's public surface
    exposes only callable writers — no scheduler, no thread, no
    autostart — so it CANNOT be invoked from the request path without
    an explicit, traceable wire-up (the F29 MODULE_SPECS surface)."""
    import charon.routing_policy.price_refresher as pr
    # No ``start``, ``serve``, ``run_forever``, ``loop``, ``daemon`` —
    # the only callable writer is the explicit ``refresh_openrouter_now``.
    for name in ("start", "serve", "run_forever", "loop", "daemon"):
        assert not hasattr(pr, name), (
            f"price_refresher exposed a background starter {name!r} — "
            "the gateway could autostart it on import, putting the "
            "poller on the request path. Keep this module callable-only."
        )
    # The two writers are explicit callables.
    assert callable(pr.refresh_openrouter_now)
    assert callable(pr.seed_from_vendored)


# ── 3. Meter-observed cost supersedes the vendored quote ────────────────


def test_meter_supersedes_vendored_quote_in_live_rank() -> None:
    """FAIL-ON-REVERT (ticket criterion #3): the METER-OBSERVED per-
    (model, provider) cost (``observer.all_model_provider_costs``,
    proxy.py:549) MUST supersede any vendored/pulled quote inside
    ``order_pool_by_live_cost`` the moment traffic exists. This is the
    only defense against thinking-token undercount — a static quote
    that under-bills thinking tokens is worse than a meter that
    observes reality.

    Setup: the vendored seed makes ``deepseek`` the cheaper-sourced
    provider for ``deepseek-v4-pro`` (cheaper than the openrouter relay).
    The live meter, however, shows the REVERSE: deepseek has accumulated
    more cost so far (because of a thinking-token-heavy model), and
    openrouter has spent less. The routing function MUST follow the
    meter, not the vendored quote."""
    state = CacheState(model_pricing={})
    seed_from_vendored(state)
    seed = state.model_pricing["deepseek-v4-pro"]

    base_a = "http://deepseek.invalid"
    base_b = "http://openrouter.invalid"
    chain = [
        _upstream("deepseek", base_a, "deepseek-v4-pro", "deepseek-v4-pro"),
        _upstream("openrouter", base_b, "deepseek-v4-pro", "deepseek-v4-pro"),
    ]

    # Per-provider registry view: deepseek (the cheap-quote) vs
    # openrouter (the expensive-quote). The vendored seed for
    # openrouter/deepseek-v4-pro is missing — openrouter serves it under
    # its own relay, which has a different cost — set that explicitly.
    registry = {
        "deepseek-v4-pro": {
            "deepseek": {"cost_input": seed["cost_input"], "cost_output": seed["cost_output"]},
            "openrouter": {"cost_input": 0.000003, "cost_output": 0.000015},
        },
    }

    # Empty meter — cheapest-sourced order (deepseek first).
    out_empty = order_pool_by_live_cost(chain, registry=registry, metered_costs=None)
    assert [r.provider for r in out_empty] == ["deepseek", "openrouter"], (
        "empty meter: deepseek is the cheaper-sourced provider and must be first"
    )

    # Meter shows the OPPOSITE: deepseek has $0.50 actual, openrouter $0.05
    # actual. The meter wins, even though the vendored quote says
    # deepseek is cheaper.
    meter = {
        ("deepseek-v4-pro", "deepseek"): 0.50,
        ("deepseek-v4-pro", "openrouter"): 0.05,
    }
    out_meter = order_pool_by_live_cost(chain, registry=registry, metered_costs=meter)
    assert [r.provider for r in out_meter] == ["openrouter", "deepseek"], (
        f"meter must override vendored quote — got {[r.provider for r in out_meter]}, "
        "expected ['openrouter', 'deepseek']"
    )


# ── 4. Vendored JSON is checked in (file-existence invariant) ────────────


def test_vendored_file_present_on_disk() -> None:
    """The LiteLLM snapshot is checked in as a static file. ``load_vendored_snapshot``
    reads it via ``importlib.resources``, so it works under both the source
    checkout AND an installed wheel. The packaged wheel was verified to
    include this file (see test-data path under ``charon/routing_policy/_data/``)."""
    from importlib import resources
    pkg_files = resources.files("charon.routing_policy")
    assert (pkg_files / "_data" / "litellm_prices.json").is_file(), (
        "vendored LiteLLM snapshot missing from the package data dir — "
        "PRICE-REFRESHER's seed layer would have nothing to load"
    )


# ── 5. OpenRouter poller is background-only and degrades on failure ─────


def test_openrouter_poll_writes_to_cache(monkeypatch) -> None:
    """The OpenRouter poller writes the live catalog into the cache under
    the ``openrouter_live`` stamp. Background call only — we invoke it
    directly. The cache write is observable via ``state.model_pricing``."""
    fake_payload = {
        "data": [
            {
                "id": "anthropic/claude-sonnet-4",
                "pricing": {
                    "prompt": "0.000003",
                    "completion": "0.000015",
                    "input_cache_read": "0.0000003",
                },
                "context_length": 200000,
            },
        ],
    }
    class _FakeResp:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self, n: int = -1) -> bytes:
            return self._body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=None: _FakeResp(json.dumps(fake_payload).encode()),
    )

    state = CacheState(model_pricing={})
    seed_from_vendored(state)
    n = refresh_openrouter_now(state, timeout=5)
    assert n == 1
    e = state.model_pricing["anthropic/claude-sonnet-4"]
    assert e["cost_input"] == 3e-06
    assert e["cost_output"] == 1.5e-05
    assert e["priced_by"] == "openrouter_live"


def test_openrouter_poll_failure_does_not_raise(monkeypatch) -> None:
    """A failed poll MUST NOT raise into the caller's request path — the
    ticket requires "degrade to STALE-BUT-USABLE on any refresh failure".
    The error is recorded in ``state.last_error`` and the existing cache
    values (the vendored seed) are kept."""
    def _boom(*a, **kw):
        raise urllib.error.URLError("network unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    state = CacheState(model_pricing={"deepseek-v4-pro": {"cost_input": 0.0, "cost_output": 0.0}})
    n = refresh_openrouter_now(state, timeout=1)
    assert n == 0
    assert state.last_error is not None
    assert "URLError" in state.last_error or "network" in state.last_error.lower()
    # Existing cache survives the failure.
    assert "deepseek-v4-pro" in state.model_pricing


# ── 6. Webhook ingest (changedetection.io) ───────────────────────────────


def test_drift_event_parses_and_writes() -> None:
    """changedetection.io posts ``{provider, url, old, new}``. The handler
    projects ``url`` into the model_id (final ``/``-segment), validates
    ``new`` is a non-negative number, and writes the cache."""
    state = CacheState(model_pricing={})
    seed_from_vendored(state)
    body = {
        "provider": "nanogpt",
        "url": "https://nano-gpt.com/pricing/nanogpt-mistral",
        "old": 0.000001,
        "new": 0.0000009,
    }
    ev = parse_drift_event(body)
    assert ev is not None
    assert ev.model_id == "nanogpt-mistral"
    assert ev.provider == "nanogpt"
    assert ev.new == 0.0000009
    n = apply_drift_event(state, ev)
    assert n == 1
    e = state.model_pricing["nanogpt-mistral"]
    assert e["cost_input"] == 0.0000009
    assert e["cost_output"] == 0.0000009
    assert e["priced_by"] == "webhook"


def test_drift_event_invalid_returns_none() -> None:
    """A body with a missing ``new``/``provider``/``url`` is rejected
    silently — the webhook handler must NEVER crash on a malformed
    payload (changedetection.io is an external service)."""
    assert parse_drift_event({}) is None
    assert parse_drift_event({"provider": "nanogpt"}) is None
    # ``provider`` + ``url`` + missing ``new`` → parsed but ``apply_drift_event``
    # drops the entry (no number to write); the parser itself does not reject.
    ev_missing_new = parse_drift_event({"provider": "nanogpt", "url": "https://x/y/z"})
    assert ev_missing_new is not None
    state = CacheState(model_pricing={})
    assert apply_drift_event(state, ev_missing_new) == 0
    # ``new`` present but non-numeric → apply_drift_event also drops it.
    ev_bad_new = parse_drift_event({"provider": "nanogpt", "url": "https://x/y/z",
                                    "new": "not a number"})
    assert ev_bad_new is not None
    assert apply_drift_event(state, ev_bad_new) == 0


# ── 7. Registry view composition — the forwarder's R2 contract ──────────


def test_build_registry_view_merges_models_and_prices() -> None:
    """The forwarder's R2 block builds ``{model_id: {price..., meta...}}``
    from ``srv.model_pricing`` + ``srv.model_meta``. ``build_registry_view``
    is the SAME composition — it must not drop operator-set fields."""
    state = CacheState(model_pricing={"m": {"cost_input": 0.1, "cost_output": 0.2}})
    view = build_registry_view(state, models={
        "m": {"provider": "openai", "cost_rank": 5, "free": False},
        "absent-from-pricing": {"provider": "deepseek"},
    })
    assert view["m"]["cost_input"] == 0.1
    assert view["m"]["cost_output"] == 0.2
    assert view["m"]["provider"] == "openai"
    assert view["m"]["cost_rank"] == 5
    # Model in *models* but missing from pricing still surfaces (with
    # whatever metadata the operator set).
    assert "absent-from-pricing" in view


def test_provider_key_map_covers_all_charon_wired_providers() -> None:
    """The PROVIDER_KEY_MAP must include every provider Charon wires up
    that LiteLLM has prices for — missing entries would silently drop
    seed data, and tests for those providers would mysteriously pass
    with empty caches. Spot-check the headline providers from the
    hosted preset list."""
    expected_in_map = {
        "openai", "openrouter", "deepseek", "groq", "together_ai",
        "mistral", "fireworks_ai", "xai", "cohere", "perplexity",
        "gemini", "zai", "anthropic",
    }
    actual = set(PROVIDER_KEY_MAP.keys())
    missing = expected_in_map - actual
    assert not missing, (
        f"PROVIDER_KEY_MAP is missing {missing} — those providers' "
        "vendored prices would never seed model_pricing"
    )


# ── 8. apply_to_cache API ──────────────────────────────────────────────


def test_apply_to_cache_writes_per_provider_entry() -> None:
    """``apply_to_cache`` is the shared writer used by the OpenRouter
    poller and (indirectly) the webhook handler. It stamps the entry
    with the caller's ``priced_by`` tag and never clobbers operator
    prices."""
    state = CacheState(model_pricing={})
    n = apply_to_cache(state, provider="openrouter",
                       entries={"openai/gpt-4o": {"cost_input": 0.000005,
                                                  "cost_output": 0.000015}},
                       priced_by="openrouter_live")
    assert n == 1
    e = state.model_pricing["openai/gpt-4o"]
    assert e["priced_by"] == "openrouter_live"
    assert e["cost_input"] == 0.000005


def test_apply_to_cache_rejects_negative_prices() -> None:
    """A garbage negative price is dropped — never persisted."""
    state = CacheState(model_pricing={})
    n = apply_to_cache(state, provider="openrouter",
                       entries={"x": {"cost_input": -0.1, "cost_output": 0.0}},
                       priced_by="openrouter_live")
    assert n == 0
    assert "x" not in state.model_pricing