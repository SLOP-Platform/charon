"""SPIKE harness — drive litellm.Router UNDER Charon's UNCHANGED policy layer.

No paid calls: litellm.Router hits a LOCAL mock OpenAI-compatible server, so the
real Router.completion path (HTTP call, cost computation, exception->status
mapping) is exercised end-to-end without any provider credential. Everything
Charon-side is imported from the product source and called UNMODIFIED:

  * charon.proxy_server.UpstreamRoute        (the route type)
  * charon.routing_policy.order_chain_by_funding_class  (drain ordering)
  * charon.routing_policy.order_pool_by_live_cost       (cheapest-first)
  * charon.proxy.ProxyObserver.classify      (silent-downgrade / exhaustion)
  * charon.quality_scorer.QualityScorer      (the feedback loop, .score/.record)

The ONLY new code is litellm_router_adapter.attempt(), which replaces the
substrate slice forwarder.py:559-651 (build req + urlopen + retry). The policy
functions are invoked with the SAME arguments forwarder.py passes them.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from charon.proxy import GatewayProxy  # the observer: .classify / .record
from charon.proxy_server import UpstreamRoute
from charon.quality_scorer import QualityScorer
from charon.routing_policy import (
    order_chain_by_funding_class,
    order_pool_by_live_cost,
)

sys.path.insert(0, str(Path(__file__).parent))
from litellm_router_adapter import attempt  # noqa: E402

# ── mock OpenAI-compatible upstream ────────────────────────────────────────
# Behaviour keyed on api port. Each Charon route points at its own port so we
# can make one 429 and one 200, exactly like two real providers of a pool.
_BEHAVIOUR: dict[int, dict] = {}


class _MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        _ = self.rfile.read(n)
        beh = _BEHAVIOUR.get(self.server.server_address[1], {})
        status = beh.get("status", 200)
        if status != 200:
            body = {"error": {"message": beh.get("msg", "error"),
                              "type": beh.get("type", "error")}}
        else:
            body = {
                "id": "chatcmpl-mock", "object": "chat.completion",
                "created": 0, "model": beh.get("model", "gpt-4o-mini"),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6,
                          "total_tokens": 18},
            }
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _start_mock() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _MockHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def _route(provider: str, port: int, upstream_model: str = "gpt-4o-mini",
           model_id: str | None = None) -> UpstreamRoute:
    return UpstreamRoute(
        upstream_base=f"http://127.0.0.1:{port}/v1",
        api_key="sk-mock", upstream_model=upstream_model,
        provider=provider, model_id=model_id or provider, pool_id="pool-x")


# ── minimal stand-ins for the srv-side collaborators the loop reads ────────
# These mirror what GatewayProxyServer exposes; they are NOT reimplementations
# of policy — the policy functions themselves are the real product code.
class _FundingBook:
    """Same shape forwarder.py:427-435 calls: funding_class(prov)/remaining(prov)."""
    def __init__(self, classes: dict[str, int], remaining: dict[str, float]):
        self._c, self._r = classes, remaining

    def funding_class(self, p): return self._c.get(p)
    def remaining(self, p): return self._r.get(p)


def main() -> int:
    observer = GatewayProxy()           # REAL, unmodified
    quality = QualityScorer(state_dir=Path("/tmp/claude-1000/spike-quality"))
    results: list[str] = []

    # ── SCENARIO 1: funding-class + live-cost ordering, then failover ──────
    # provider-a: class 4 (PAYG), cheap-configured, but returns 429 (exhausted)
    # provider-b: class 1 (free-recurring), returns 200
    # Charon policy must put the free class-1 FIRST (drain-then-park), and the
    # loop must fail over off the 429 to the 200 — all with product code.
    # provider-b sorts FIRST (class 1 free) but returns 429 -> the loop must
    # fail over to provider-a (class 4 PAYG) which returns 200. This exercises
    # BOTH the policy ordering AND the exhaustion-failover branch.
    port_a, port_b = _start_mock(), _start_mock()
    _BEHAVIOUR[port_a] = {"status": 200, "model": "gpt-4o-mini"}
    _BEHAVIOUR[port_b] = {"status": 429, "msg": "rate limit", "type": "rate_limit"}
    ra = _route("provider-a", port_a)
    rb = _route("provider-b", port_b)

    chain = [ra, rb]
    book = _FundingBook({"provider-a": 4, "provider-b": 1},
                        {"provider-a": 5.0, "provider-b": 0.0})
    # >>> PRODUCT POLICY CALL #1 (forwarder.py:434) — UNCHANGED <<<
    chain = order_chain_by_funding_class(
        chain, funding_class_fn=lambda p: book.funding_class(p),
        remaining_fn=lambda p: book.remaining(p))
    # >>> PRODUCT POLICY CALL #2 (forwarder.py:544) — UNCHANGED <<<
    chain = order_pool_by_live_cost(chain, registry={}, metered_costs={})
    order = [r.provider for r in chain]
    results.append(f"policy order (free-first): {order}")
    assert order[0] == "provider-b", "funding-class ordering did NOT run"

    # failover loop — the same classify/quality_scorer calls forwarder.py makes
    served = None
    for i, route in enumerate(chain):
        more = i < len(chain) - 1
        status, headers, body = attempt(route, [{"role": "user", "content": "hi"}],
                                        requested_model="pool-x")
        # >>> PRODUCT POLICY CALL #3 (forwarder.py:773/599) — UNCHANGED <<<
        obs = observer.classify("pool-x", status, headers, body,
                                expected_model=route.upstream_model)
        if status != 200 and obs.failover and more:
            # >>> quality feedback on a failed attempt (forwarder path) <<<
            quality.record(route.provider, 0, success=False, tokens=0)
            results.append(f"  {route.provider}: {status} exhausted={obs.exhausted} "
                           f"-> failover")
            continue
        if status == 200:
            # >>> PRODUCT POLICY CALL #4 (forwarder.py:814) — UNCHANGED <<<
            quality.record(route.provider, 0, success=not obs.pseudo_success, tokens=0)
            cost = obs.usage.cost_usd if obs.usage else None
            served = (route.provider, cost, obs.pseudo_success)
            results.append(f"  {route.provider}: 200 cost=${cost} "
                           f"downgrade={obs.pseudo_success} -> SERVED")
            break
    assert served and served[0] == "provider-a", "failover to 200 did not happen"
    assert served[1] and served[1] > 0, "litellm cost NOT captured"
    results.append(f"quality: provider-a={quality.score('provider-a'):.2f} "
                   f"provider-b={quality.score('provider-b'):.2f}")

    # ── SCENARIO 2: silent downgrade detected by UNCHANGED classify ────────
    # route asks upstream_model gpt-4o-mini; mock returns model gpt-3.5-turbo.
    port_c = _start_mock()
    _BEHAVIOUR[port_c] = {"status": 200, "model": "gpt-3.5-turbo"}
    rc = _route("provider-c", port_c, upstream_model="gpt-4o-mini")
    status, headers, body = attempt(rc, [{"role": "user", "content": "hi"}],
                                    requested_model="pool-x")
    obs = observer.classify("pool-x", status, headers, body,
                            expected_model=rc.upstream_model)
    # forwarder.py:815 — a downgrade is scored success=False so the router won't
    # learn to prefer a habitual downgrader.
    quality.record(rc.provider, 0, success=not obs.pseudo_success, tokens=0)
    results.append(f"downgrade case: asked gpt-4o-mini got {obs.returned_model!r} "
                   f"pseudo_success={obs.pseudo_success} "
                   f"quality(provider-c)={quality.score('provider-c'):.2f}")
    assert obs.pseudo_success is True, "silent downgrade NOT detected by classify"

    print("\n".join(results))
    print("\nSPIKE OK: litellm.Router drove every attempt; Charon policy code ran unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
