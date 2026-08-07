"""FORWARDER-COST-ORDER-FALLBACK — the money path must use cost_rank ASC when the
per-provider meter is empty, NOT the static configured order.

Regression for the 2026-08-01 fleet stall: the OpenRouter key cap 403'd every
leg while a funded, ~6x cheaper deepseek-direct leg sat one position further
down the static chain, never tried.  Root cause: ``forwarder.py`` stated
"Empty meter -> the order is unchanged (preserves the static configured order)"
— but the per-provider meter was NEVER populated (``spend.json`` held a GLOBAL
aggregate only), so the reorder never fired and the static hand-authored order
governed every request.

The fix: when per-provider metered spend is absent or empty, fall back to
``cost_rank`` ASC (free-first) via ``routing_policy.derived_cost_rank`` — NOT
to the static configured order.  Precedence:
  1. free legs first
  2. real per-provider metered spend, when present
  3. ``cost_rank`` ASC (derived from configured per-token pricing)
  4. static configured order (last-resort tiebreak only)

Hermetic, offline, no live gateway.  Each test drives ``forward_with_failover``
end-to-end against mock upstreams.  ``test_empty_meter_uses_cost_rank_not_static_order``
is the FAIL-ON-REVERT guard: RED with the old "empty meter → order unchanged"
fallback, GREEN only with the fix.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.request
from pathlib import Path

from charon.balance import BalanceTracker
from charon.proxy_server import GatewayProxyServer, UpstreamRoute
from charon.spend_limits import SpendLimiter
from charon.types import SpendDecision


class _Prog(http.server.BaseHTTPRequestHandler):
    """Mock upstream: records the upstream_model it received, returns a
    configurable status with a usage block."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        srv.received.append(body.get("model"))  # type: ignore[attr-defined]
        # Global ordering witness (shared across all upstreams in this test).
        order_log = getattr(srv, "order_log", None)  # type: ignore[attr-defined]
        if order_log is not None:
            order_log.append(body.get("model"))
        if srv.status == 200:  # type: ignore[attr-defined]
            payload = json.dumps({
                "model": srv.return_model,  # type: ignore[attr-defined]
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                          "cost": srv.cost},  # type: ignore[attr-defined]
            }).encode()
            self.send_response(200)
        else:
            err = {"error": {"metadata": {"error_type": "rate_limit_exceeded"}}}
            payload = json.dumps(err).encode()
            self.send_response(srv.status)  # type: ignore[attr-defined]
            if srv.status == 429:  # type: ignore[attr-defined]
                self.send_header("Retry-After", "30")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _up(status=200, return_model="m", cost=0.0, order_log=None):
    srv = _Threaded(("127.0.0.1", 0), _Prog)
    srv.status, srv.return_model, srv.cost = status, return_model, cost  # type: ignore[attr-defined]
    srv.received = []  # type: ignore[attr-defined]
    srv.order_log = order_log  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _req(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.status, json.loads(resp.read()), dict(resp.headers)


class _AllowAllLimiter(SpendLimiter):
    """Always allows — so the spend cap never blocks the test request."""

    def __init__(self, state_dir: Path) -> None:
        super().__init__(monthly_limit_usd=0.0, state_dir=state_dir)

    def check(self, estimated_cost: float) -> SpendDecision:
        return SpendDecision(allowed=True, remaining=float("inf"), reason="")


def _gw(pools, *, model_pricing=None, balance_tracker=None, tmp_path=None):
    kwargs = {"pools": pools}
    if model_pricing is not None:
        kwargs["model_pricing"] = model_pricing
    if balance_tracker is not None:
        kwargs["balance_tracker"] = balance_tracker
    if tmp_path is not None:
        kwargs["spend_limiter"] = _AllowAllLimiter(tmp_path)
    gw = GatewayProxyServer(**kwargs)
    gw.serve_in_thread()
    return gw


# ── (a) Reproduce the real incident: empty meter → cost_rank ASC, not static ─

def test_empty_meter_uses_cost_rank_not_static_order(tmp_path: Path) -> None:
    """FAIL-ON-REVERT: with an empty per-provider meter, the cheaper leg (by
    derived cost_rank) is tried FIRST — even if the static configured order
    places a costlier leg ahead of it.

    This is the 2026-08-01 incident: openrouter (rank 50, costlier) sat BEFORE
    deepseek-direct (rank 8, ~6x cheaper) in the static chain.  The empty
    per-provider meter meant the reorder never fired, so openrouter was tried
    first and 403'd the whole fleet while deepseek-direct sat untried.

    RED with the old "empty meter → order unchanged" fallback (openrouter
    tried first), GREEN only with the cost_rank ASC fallback (deepseek first).
    """
    # Static configured order: openrouter FIRST, deepseek SECOND (the incident).
    or_up, base_or = _up(status=429, return_model="or-dsv4", cost=0.0)
    ds_up, base_ds = _up(status=200, return_model="ds-dsv4", cost=0.0)
    # Pricing: openrouter is ~6x costlier than deepseek-direct.
    pricing = {
        "or-dsv4": {"cost_input": 0.000010, "cost_output": 0.000020},
        "ds-dsv4": {"cost_input": 0.000001, "cost_output": 0.000002},
    }
    gw = _gw({
        "deepseek-v4-flash": [
            UpstreamRoute(base_or, "kor", upstream_model="or-dsv4",
                          provider="openrouter", model_id="or-dsv4"),
            UpstreamRoute(base_ds, "kds", upstream_model="ds-dsv4",
                          provider="deepseek", model_id="ds-dsv4"),
        ]
    }, model_pricing=pricing, tmp_path=tmp_path)
    try:
        status, body, hdrs = _req(
            gw.url + "/v1/chat/completions", {"model": "deepseek-v4-flash"})
        assert status == 200
        # deepseek-direct (cheaper) tried FIRST, succeeds → openrouter never tried
        assert ds_up.received == ["ds-dsv4"], (
            f"deepseek-direct received {ds_up.received}, expected ['ds-dsv4'] "
            "(the cheaper leg must be tried first under cost_rank ASC fallback)")
        assert or_up.received == [], (
            f"openrouter received {or_up.received}, expected [] "
            "(the costlier leg must NOT be tried first under cost_rank ASC "
            "fallback — this is the 2026-08-01 stall regression)")
    finally:
        gw.shutdown()
        or_up.shutdown()
        ds_up.shutdown()


# ── (b) free legs precede all paid legs ─────────────────────────────────────

def test_free_legs_precede_paid_legs(tmp_path: Path) -> None:
    """A free leg is tried before any paid leg, regardless of static order."""
    paid_up, base_paid = _up(status=429, return_model="paid-m", cost=0.0)
    free_up, base_free = _up(status=200, return_model="free-m", cost=0.0)
    # Static order: paid FIRST, free SECOND.
    pricing = {
        "paid-m": {"cost_input": 0.000001, "cost_output": 0.000002},
        "free-m": {"free": True},
    }
    gw = _gw({
        "v": [
            UpstreamRoute(base_paid, "kp", upstream_model="paid-m",
                          provider="paid-prov", model_id="paid-m"),
            UpstreamRoute(base_free, "kf", upstream_model="free-m",
                          provider="free-prov", model_id="free-m"),
        ]
    }, model_pricing=pricing, tmp_path=tmp_path)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        # free leg tried FIRST (free-first precedence), succeeds
        assert free_up.received == ["free-m"]
        assert paid_up.received == []
    finally:
        gw.shutdown()
        paid_up.shutdown()
        free_up.shutdown()


# ── (c) per-provider metered spend wins over cost_rank ─────────────────────

def test_live_metered_spend_wins_over_cost_rank(tmp_path: Path) -> None:
    """When per-provider metered spend IS present, it wins over cost_rank —
    do not regress the existing R2 behaviour."""
    cheap_by_rank_up, base_cheap = _up(status=200, return_model="cheap-m", cost=0.0)
    exp_by_rank_up, base_exp = _up(status=200, return_model="exp-m", cost=0.0)
    # Pricing: cheap-m has LOWER cost_rank (cheaper by configured price).
    pricing = {
        "cheap-m": {"cost_input": 0.000001, "cost_output": 0.000002},
        "exp-m": {"cost_input": 0.000010, "cost_output": 0.000020},
    }
    # model_id="v" matches the pool vid / requested model so the live-meter
    # lookup key (route.model_id, provider) aligns with the observer's
    # (requested_model, provider) meter key (the existing R2 test pattern).
    gw = _gw({
        "v": [
            UpstreamRoute(base_cheap, "kc", upstream_model="cheap-m",
                          provider="prov-cheap", model_id="v"),
            UpstreamRoute(base_exp, "ke", upstream_model="exp-m",
                          provider="prov-exp", model_id="v"),
        ]
    }, model_pricing=pricing, tmp_path=tmp_path)
    # Seed the live meter: prov-exp has LOWER cumulative spend → cheaper by meter.
    # This INVERTS the cost_rank order: by rank, cheap-m is cheaper; by meter,
    # exp-m is cheaper.  The meter must win.
    gw.observer._model_provider_cost[("v", "prov-cheap")] = 0.50
    gw.observer._model_provider_cost[("v", "prov-exp")] = 0.05
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        # meter says prov-exp is cheaper → tried first
        assert exp_by_rank_up.received == ["exp-m"]
        assert cheap_by_rank_up.received == []
    finally:
        gw.shutdown()
        cheap_by_rank_up.shutdown()
        exp_by_rank_up.shutdown()


# ── (d) a leg with no cost_rank never sorts ahead of a priced cheaper leg ────

def test_unpriced_leg_never_sorts_ahead_of_priced_cheaper(tmp_path: Path) -> None:
    """A leg with NO pricing (no ``cost_input``/``cost_output``) derives to a
    neutral 1000 and must NEVER sort ahead of a known-cheap priced leg."""
    unpriced_up, base_unpriced = _up(status=429, return_model="unpriced-m", cost=0.0)
    cheap_up, base_cheap = _up(status=200, return_model="cheap-m", cost=0.0)
    # Static order: unpriced FIRST, cheap SECOND.
    # Pricing: cheap-m has low cost; unpriced-m has NO pricing entry at all.
    pricing = {
        "cheap-m": {"cost_input": 0.000001, "cost_output": 0.000002},
        # "unpriced-m" deliberately absent → derived_cost_rank returns 1000
    }
    gw = _gw({
        "v": [
            UpstreamRoute(base_unpriced, "ku", upstream_model="unpriced-m",
                          provider="unpriced-prov", model_id="unpriced-m"),
            UpstreamRoute(base_cheap, "kc", upstream_model="cheap-m",
                          provider="cheap-prov", model_id="cheap-m"),
        ]
    }, model_pricing=pricing, tmp_path=tmp_path)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        # cheap-m (known-cheap, rank < 1000) tried FIRST
        assert cheap_up.received == ["cheap-m"]
        assert unpriced_up.received == []
    finally:
        gw.shutdown()
        unpriced_up.shutdown()
        cheap_up.shutdown()


# ── (e) disabled/parked legs are skipped entirely ───────────────────────────

def test_parked_leg_is_skipped(tmp_path: Path) -> None:
    """A parked leg (``balance_park.json``) is excluded from the chain entirely
    — the DRAIN-AND-PARK pre-flight exclusion drops it before the cost_rank
    fallback reorders the remaining legs."""
    parked_up, base_parked = _up(status=200, return_model="parked-m", cost=0.0)
    live_up, base_live = _up(status=200, return_model="live-m", cost=0.0)
    pricing = {
        "parked-m": {"cost_input": 0.000001, "cost_output": 0.000002},
        "live-m": {"cost_input": 0.000010, "cost_output": 0.000020},
    }
    bt = BalanceTracker()
    # Park the cheaper leg — it must be skipped, leaving the costlier live leg.
    bt.park("parked-prov")
    gw = _gw({
        "v": [
            UpstreamRoute(base_parked, "kp", upstream_model="parked-m",
                          provider="parked-prov", model_id="parked-m"),
            UpstreamRoute(base_live, "kl", upstream_model="live-m",
                          provider="live-prov", model_id="live-m"),
        ]
    }, model_pricing=pricing, balance_tracker=bt, tmp_path=tmp_path)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        # parked-prov skipped → only live-prov tried
        assert parked_up.received == []
        assert live_up.received == ["live-m"]
    finally:
        gw.shutdown()
        parked_up.shutdown()
        live_up.shutdown()


# ── (f) ANTI-OVER-BLOCK: correct cost order returned unchanged ──────────────

def test_chain_already_in_cost_order_returned_unchanged(tmp_path: Path) -> None:
    """A chain already in correct cost order (cheapest-first) is returned
    unchanged — the cost_rank ASC fallback is a stable sort, not a shuffle."""
    cheap_up, base_cheap = _up(status=200, return_model="cheap-m", cost=0.0)
    exp_up, base_exp = _up(status=200, return_model="exp-m", cost=0.0)
    # Static order ALREADY cheapest-first: cheap FIRST, expensive SECOND.
    pricing = {
        "cheap-m": {"cost_input": 0.000001, "cost_output": 0.000002},
        "exp-m": {"cost_input": 0.000010, "cost_output": 0.000020},
    }
    gw = _gw({
        "v": [
            UpstreamRoute(base_cheap, "kc", upstream_model="cheap-m",
                          provider="prov-cheap", model_id="cheap-m"),
            UpstreamRoute(base_exp, "ke", upstream_model="exp-m",
                          provider="prov-exp", model_id="exp-m"),
        ]
    }, model_pricing=pricing, tmp_path=tmp_path)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        # cheap-m stays first → tried first, succeeds
        assert cheap_up.received == ["cheap-m"]
        assert exp_up.received == []
    finally:
        gw.shutdown()
        cheap_up.shutdown()
        exp_up.shutdown()


# ── (g) cross cost_class: a free-daily class wins over a cheaper-by-token paid leg ─

def test_cost_class_priority_overrides_lower_token_cost(tmp_path: Path) -> None:
    """A leg whose ``cost_class`` is cheaper (e.g. ``free-daily``) is preferred
    over a paid leg with a lower derived cost_rank.  Mirrors the precedence
    ``pools.load_pools`` and ``build_routes_and_pools`` enforce at startup —
    the empty-meter fallback must reproduce that ordering, not just rank by
    token price alone."""
    fd_up, base_fd = _up(status=200, return_model="fd-m", cost=0.0)
    paid_up, base_paid = _up(status=429, return_model="paid-m", cost=0.0)
    # Static order: paid FIRST (cheap by token), free-daily SECOND (would be
    # costly by token alone).  cost_class is what ranks free-daily ahead.
    pricing = {
        # free-daily: token price is HIGHER than the paid leg — only cost_class
        # can rank it ahead.  Without the cost_class priority pass, the paid
        # leg would sort first (lower derived_cost_rank).
        "fd-m": {"cost_input": 0.000050, "cost_output": 0.000060,
                 "cost_class": "free-daily"},
        # paid: cheap by token, but cost_class=metered → cost_class_priority=3.
        "paid-m": {"cost_input": 0.000001, "cost_output": 0.000002,
                   "cost_class": "metered"},
    }
    gw = _gw({
        "v": [
            UpstreamRoute(base_paid, "kp", upstream_model="paid-m",
                          provider="paid-prov", model_id="paid-m"),
            UpstreamRoute(base_fd, "kfd", upstream_model="fd-m",
                          provider="fd-prov", model_id="fd-m"),
        ]
    }, model_pricing=pricing, tmp_path=tmp_path)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        # free-daily (cost_class priority 0) tried FIRST despite higher token price
        assert fd_up.received == ["fd-m"]
        assert paid_up.received == []
    finally:
        gw.shutdown()
        fd_up.shutdown()
        paid_up.shutdown()


# ── Real scenario: the deepseek-v4-flash leg set, before and after ──────────

def test_real_deepseek_v4_flash_leg_set_order(tmp_path: Path) -> None:
    """Report the resulting order for the real ``deepseek-v4-flash`` leg set.

    The stored static order (2026-08-01) was:
      nv(free) -> go(rank 5, DISABLED) -> ng(rank 800) ->
      hf(rank 30, parked) -> or(rank 50) -> ds(rank 8) -> cline(rank 900)

    go is ``enabled: false`` (excluded at config-load, never in the chain).
    hf is parked (``balance_park.json`` → skipped by DRAIN-AND-PARK).

    After the fix, the remaining legs order by cost_rank ASC (free-first):
      nv(free) -> ds(8) -> or(50) -> ng(800) -> cline(900)

    All legs return 429 except cline (the last) so the failover walks the
    entire chain, making the order observable from the received-models list.
    """
    legs = {
        "nv":  {"free": True, "cost_input": 0.0, "cost_output": 0.0},
        # go: enabled:false → excluded at config-load, not modelled here
        "ng":  {"cost_input": 0.000050, "cost_output": 0.000060},  # rank ~800
        "hf":  {"cost_input": 0.000003, "cost_output": 0.000004},  # rank ~30
        "or":  {"cost_input": 0.000005, "cost_output": 0.000008},  # rank ~50
        "ds":  {"cost_input": 0.000001, "cost_output": 0.000002},  # rank ~8
        "cline": {"cost_input": 0.000100, "cost_output": 0.000120},  # rank ~900
    }
    # Build mock upstreams: all 429 except cline (last) returns 200.
    ups: dict[str, _Threaded] = {}
    bases: dict[str, str] = {}
    order_log: list[str] = []
    for name in legs:
        status = 200 if name == "cline" else 429
        u, b = _up(status=status, return_model=f"{name}-dsv4", cost=0.0,
                   order_log=order_log)
        ups[name] = u
        bases[name] = b

    bt = BalanceTracker()
    bt.park("hf")  # huggingface parked (balance_park.json)
    # Build the pool in the stored static order (minus go, which is disabled).
    chain = [
        UpstreamRoute(bases["nv"],  "knv",  upstream_model="nv-dsv4",
                      provider="nv",  model_id="nv"),
        UpstreamRoute(bases["ng"],  "kng",  upstream_model="ng-dsv4",
                      provider="ng",  model_id="ng"),
        UpstreamRoute(bases["hf"],  "khf",  upstream_model="hf-dsv4",
                      provider="hf",  model_id="hf"),
        UpstreamRoute(bases["or"],  "kor",  upstream_model="or-dsv4",
                      provider="or",  model_id="or"),
        UpstreamRoute(bases["ds"],  "kds",  upstream_model="ds-dsv4",
                      provider="ds",  model_id="ds"),
        UpstreamRoute(bases["cline"], "kcl", upstream_model="cline-dsv4",
                      provider="cline", model_id="cline"),
    ]
    pricing = dict(legs)
    gw = _gw({"deepseek-v4-flash": chain}, model_pricing=pricing,
             balance_tracker=bt, tmp_path=tmp_path)
    try:
        status, body, hdrs = _req(
            gw.url + "/v1/chat/completions", {"model": "deepseek-v4-flash"})
        assert status == 200
        # Expected order (free-first, then cost_rank ASC; hf parked → skipped):
        #   nv → ds → or → ng → cline
        assert order_log == ["nv-dsv4", "ds-dsv4", "or-dsv4", "ng-dsv4",
                             "cline-dsv4"], (
            f"expected [nv, ds, or, ng, cline]; got {order_log}")
        # hf is parked → never tried
        assert ups["hf"].received == [], "hf should be parked/skipped"  # type: ignore[attr-defined]
    finally:
        gw.shutdown()
        for u in ups.values():
            u.shutdown()
