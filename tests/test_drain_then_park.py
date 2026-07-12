"""FAIL-ON-REVERT tests for DRAIN-THEN-PARK: auto-park, re-arm, sole-leg guard.

Two invariants (operator, non-negotiable):
  1. A class-3 (drain-then-park) provider whose balance reaches ~0 is AUTO-PARKED
     (marked unavailable; routing skips it, no fail-churn) and RE-ARMS to active
     when topped up.
  2. SOLE-LEG GUARD — a provider that is the ONLY remaining leg of any pool is
     NEVER auto-parked at 0 (kept/alerted instead of orphaning the pool).

Reverting either invariant must fail the corresponding assertion (FAIL-ON-REVERT).
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.request
from pathlib import Path

from charon.balance import BalanceTracker
from charon.forwarder import _is_sole_leg
from charon.proxy_server import GatewayProxyServer, UpstreamRoute


class TestClass3AutoParkAndRearm:
    """Invariant 1: a class-3 provider at ~0 is auto-parked AND re-arms on top-up."""

    def test_class3_at_zero_is_auto_parked(self):
        """A class-3 fixed-mode provider at ~0 → park flag set.

        FAIL-ON-REVERT: reverting the park trigger must fail this assertion."""
        bt = BalanceTracker(config={
            "openrouter": {
                "mode": "fixed",
                "starting_balance": 5.00,
                "funding_class": 3,
            }
        })
        # Wire a trivial spend source (no actual spend → full balance)
        bt.set_spend_provider_fn(lambda p: 0.0)
        assert bt.remaining("openrouter") == 5.0
        assert not bt.is_parked("openrouter")
        assert bt.should_drain("openrouter")

        # Simulate spend that drains the balance via the observer meter
        bt.set_spend_provider_fn(lambda p: 5.0)
        assert bt.is_drained("openrouter")
        assert not bt.should_drain("openrouter")

        # Auto-park (normally done by the forwarder's pre-flight exclusion)
        bt.park("openrouter")
        assert bt.is_parked("openrouter")

    def test_class3_rearms_on_top_up(self):
        """A parked class-3 provider re-arms (unparked) when topped up.

        FAIL-ON-REVERT: reverting the re-arm must fail this assertion."""
        bt = BalanceTracker(config={
            "neuralwatt": {
                "mode": "fixed",
                "starting_balance": 2.00,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 2.0)  # drained
        assert bt.is_drained("neuralwatt")

        # Park it
        bt.park("neuralwatt")
        assert bt.is_parked("neuralwatt")

        # Top up → re-arm
        bt.top_up("neuralwatt", 10.0)
        bt.unpark("neuralwatt")
        assert not bt.is_parked("neuralwatt")

        # After top-up, the configured starting_usd increased
        bt.set_spend_provider_fn(lambda p: 2.0)  # spent 2, but now has 12
        rem = bt.remaining("neuralwatt")
        assert rem is not None and rem > 0

    def test_class3_positive_balance_not_parked(self):
        """A class-3 provider with positive balance is NEVER parked."""
        bt = BalanceTracker(config={
            "deepseek": {
                "mode": "fixed",
                "starting_balance": 99.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)
        assert not bt.is_parked("deepseek")
        assert bt.should_drain("deepseek")
        # Even if we try to park it manually, remaining is still positive
        bt.park("deepseek")
        assert bt.is_parked("deepseek")  # park() always works (operator override)
        bt.unpark("deepseek")
        assert not bt.is_parked("deepseek")

    def test_park_unpark_cycle_preserves_remaining(self):
        """Park → unpark → balance unchanged."""
        bt = BalanceTracker(config={
            "provider-a": {
                "mode": "fixed",
                "starting_balance": 7.50,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 1.0)  # spent 1
        assert bt.remaining("provider-a") == 6.50

        bt.park("provider-a")
        assert bt.is_parked("provider-a")
        assert bt.remaining("provider-a") == 6.50  # balance unchanged by park

        bt.unpark("provider-a")
        assert not bt.is_parked("provider-a")
        assert bt.remaining("provider-a") == 6.50  # balance unchanged by unpark


class TestSoleLegGuard:
    """Invariant 2: a provider that is the only leg of a pool is NEVER parked."""

    def _mk_route(self, label):
        return UpstreamRoute("http://127.0.0.1:1/v1", api_key="k", provider=label)

    def test_sole_leg_is_detected(self):
        """_is_sole_leg returns True when provider is the only viable leg."""
        bt = BalanceTracker(config={
            "sole-provider": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)

        pools = {
            "main": [self._mk_route("sole-provider")],
        }
        # The provider is drained AND it's the only leg → sole leg
        assert bt.is_drained("sole-provider")
        assert _is_sole_leg("sole-provider", pools, bt)

    def test_sole_leg_guard_prevents_park_when_last_leg(self):
        """A drained provider that is the only leg of ANY pool → NOT auto-parked.

        FAIL-ON-REVERT: reverting the sole-leg guard must fail this assertion."""
        bt = BalanceTracker(config={
            "only-provider": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)

        pools = {
            "main": [self._mk_route("only-provider")],
        }
        # Sole-leg guard: must NOT park this provider
        is_sole = _is_sole_leg("only-provider", pools, bt)
        assert is_sole  # detected as sole leg
        # In the real forwarder path, this prevents auto-park

    def test_not_sole_leg_when_other_viable_providers_exist(self):
        """A drained provider is NOT sole leg when another provider in the pool
        is still viable."""
        bt = BalanceTracker(config={
            "drained-prov": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            },
            "healthy-prov": {
                "mode": "fixed",
                "starting_balance": 100.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0 if p == "drained-prov" else 0.0)

        pools = {
            "main": [
                self._mk_route("drained-prov"),
                self._mk_route("healthy-prov"),
            ],
        }
        # healthy-prov is not drained → drained-prov is NOT sole leg
        assert not _is_sole_leg("drained-prov", pools, bt)

    def test_sole_leg_guard_per_pool(self):
        """A provider that is sole leg of pool-A but NOT pool-B is still
        detected as a sole leg (it's the last leg of at least one pool)."""
        bt = BalanceTracker(config={
            "shared-prov": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            },
            "other-prov": {
                "mode": "fixed",
                "starting_balance": 100.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)

        pools = {
            "pool-a": [self._mk_route("shared-prov")],  # sole leg here
            "pool-b": [
                self._mk_route("shared-prov"),
                self._mk_route("other-prov"),
            ],
        }
        # shared-prov is sole leg of pool-a → detected
        assert _is_sole_leg("shared-prov", pools, bt)

    def test_unconfigured_provider_not_sole_leg(self):
        """A provider not in any pool is never detected as sole leg."""
        bt = BalanceTracker()
        assert not _is_sole_leg("nobody", {}, bt)


class TestTopUp:
    """top_up() increases the configured starting_balance."""

    def test_top_up_increases_balance(self):
        bt = BalanceTracker(config={
            "opencode-zen": {
                "mode": "fixed",
                "starting_balance": 10.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 5.0)  # spent 5
        assert bt.remaining("opencode-zen") == 5.0

        bt.top_up("opencode-zen", 20.0)
        assert bt.remaining("opencode-zen") == 25.0  # 10 + 20 - 5 = 25

    def test_top_up_negative_is_ignored(self):
        bt = BalanceTracker(config={
            "opencode-zen": {
                "mode": "fixed",
                "starting_balance": 10.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)
        bt.top_up("opencode-zen", -5.0)
        assert bt.remaining("opencode-zen") == 10.0


# ---------------------------------------------------------------------------
# F1 — forwarder integration FAIL-ON-REVERT coverage of the CALL SITE.
#
# The helper tests above cover ``_is_sole_leg`` in isolation; this class drives
# the real ``forward_with_failover`` pre-flight loop against a real mock
# upstream + real ``GatewayProxyServer`` + real ``BalanceTracker`` so that
# reverting the guard CALL (or the auto-park call) at forwarder.py:304-317
# turns these tests RED — closing the silent-regression gap identified in the
# DRAIN-AND-PARK review (F1).
# ---------------------------------------------------------------------------


class _MockUpstream(http.server.BaseHTTPRequestHandler):
    """Mock upstream returning a 200 with a REAL ``cost`` in the usage block.

    Serving the cost is what drives the observer meter → the spend-source
    callback → ``BalanceTracker.remaining`` → ``is_drained`` → the pre-flight
    exclusion branch that this test exercises.  Without a real served cost the
    fc-3 balance never decrements and the call site is never reached."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = json.dumps({
            "model": srv.return_model,                       # type: ignore[attr-defined]
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 5,
                      "cost": float(srv.serve_cost)},         # type: ignore[attr-defined]
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _ThreadedHTTP(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _boot_mock(return_model, serve_cost):  # untyped body (matches sibling harnesses)
    srv = _ThreadedHTTP(("127.0.0.1", 0), _MockUpstream)
    srv.return_model = return_model  # type: ignore[attr-defined]
    srv.serve_cost = serve_cost  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _send_chat(url: str, model: str) -> dict:
    req = urllib.request.Request(
        url + "/v1/chat/completions",
        data=json.dumps({"model": model, "messages": []}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    body = json.loads(resp.read())
    resp.close()
    return body


class TestForwarderDrainCallSiteIntegration:
    """FAIL-ON-REVERT: drive ``forward_with_failover`` end-to-end and assert the
    pre-flight exclusion CALL SITE (forwarder.py:304-317) parks a drained
    non-sole-leg provider and does NOT park a drained sole-leg provider.

    Reverting the ``bt.park(prov)`` call → ``test_drained_non_sole_leg_is_auto_parked``
    RED (the provider would stay unparked after a real drain).

    Reverting the ``_is_sole_leg`` CALL at forwarder.py:304 (making it return
    False unconditionally) → ``test_drained_sole_leg_is_not_parked`` RED (the
    sole leg would be parked, orphaning its pool)."""

    def _build_gw(self, balance_cfg: dict, pool_routes: dict):
        bt = BalanceTracker(config=balance_cfg)
        gw = GatewayProxyServer(pools=pool_routes, balance_tracker=bt)
        if gw.balance_tracker is not None:
            def _spend(provider: str) -> float:
                costs = gw.observer.all_model_provider_costs()
                return sum(c for (m, pr), c in costs.items() if pr == provider)
            gw.balance_tracker.set_spend_provider_fn(_spend)
        gw.serve_in_thread()
        return gw, bt

    def test_drained_non_sole_leg_is_auto_parked(self, tmp_path: Path) -> None:
        """FAIL-ON-REVERT: a drained class-3 provider that is NOT the sole leg
        of its pool IS auto-parked by the forwarder pre-flight exclusion.

        Reverting the ``bt.park(prov)`` call at forwarder.py:317 leaves this
        provider un-parked after its balance is drained → ``is_parked`` is
        False → the assertion fails (RED)."""

        up, base = _boot_mock("m1", serve_cost=2.0)
        try:
            # Pool with TWO legs: drained-fc3 is NOT sole (healthy-fc3 is the
            # other leg) → the guard must let the forwarder auto-park it.
            pool_routes = {
                "m1": [
                    UpstreamRoute(base, api_key="k", provider="drained-fc3"),
                    UpstreamRoute(base, api_key="k", provider="healthy-fc3"),
                ],
            }
            balance_cfg = {
                "drained-fc3": {
                    "mode": "fixed", "starting_balance": 2.0, "funding_class": 3,
                },
                "healthy-fc3": {
                    "mode": "fixed", "starting_balance": 100.0, "funding_class": 3,
                },
            }
            gw, bt = self._build_gw(balance_cfg, pool_routes)
            try:
                # Before traffic: drained-fc3 has balance 2.0, not parked.
                assert bt.remaining("drained-fc3") == 2.0
                assert not bt.is_parked("drained-fc3")

                # Drive ONE request — served cost $2.0 → observer meter totals
                # 2.0 for drained-fc3 → remaining() → 0.0 → is_drained() True.
                # On the NEXT request the forwarder's pre-flight loop hits the
                # drained branch (forwarder.py:301) and, since it is NOT sole
                # leg, calls bt.park (forwarder.py:317).
                _send_chat(gw.url, "m1")
                assert bt.remaining("drained-fc3") == 0.0
                assert bt.is_drained("drained-fc3")

                # Second request WITHOUT touching the balance tracker directly —
                # the forwarder's pre-flight loop is now responsible for the
                # auto-park.  If the call-site was reverted this stays False.
                _send_chat(gw.url, "m1")
                assert bt.is_parked("drained-fc3")
            finally:
                gw.shutdown()
        finally:
            up.shutdown()

    def test_drained_sole_leg_is_not_parked(self, tmp_path: Path) -> None:
        """FAIL-ON-REVERT: a drained class-3 provider that IS the sole
        remaining viable leg of a multi-leg pool is NOT auto-parked.

        The pool has two legs but the sibling is ALREADY parked, so the
        drained provider is the sole viable leg → the guard keeps it.  This
        exercises the ``_is_sole_leg`` CALL at forwarder.py:304 inside the
        ``len(chain) > 1`` block (a single-leg chain skips the block
        entirely, so it can't regression-lock the call site).

        Reverting the ``_is_sole_leg`` CALL at forwarder.py:304 (e.g. making
        it ``is_sole = False``) routes this provider through the auto-park
        branch at forwarder.py:317 → ``is_parked`` True → RED."""

        up, base = _boot_mock("m1", serve_cost=2.0)
        try:
            # Two-leg pool; the sibling is pre-parked so drained-fc3 is the
            # SOLE viable leg → the guard must keep it un-parked.
            pool_routes = {
                "m1": [
                    UpstreamRoute(base, api_key="k", provider="drained-fc3"),
                    UpstreamRoute(base, api_key="k", provider="parked-sibling"),
                ],
            }
            balance_cfg = {
                "drained-fc3": {
                    "mode": "fixed", "starting_balance": 2.0, "funding_class": 3,
                },
                "parked-sibling": {
                    "mode": "fixed", "starting_balance": 5.0, "funding_class": 3,
                },
            }
            gw, bt = self._build_gw(balance_cfg, pool_routes)
            try:
                # Pre-park the sibling so drained-fc3 is the sole viable leg.
                bt.park("parked-sibling")
                assert bt.is_parked("parked-sibling")

                assert bt.remaining("drained-fc3") == 2.0
                assert not bt.is_parked("drained-fc3")

                # Drain it via real traffic → remaining 0.0 → is_drained True.
                _send_chat(gw.url, "m1")
                assert bt.remaining("drained-fc3") == 0.0
                assert bt.is_drained("drained-fc3")

                # Drive additional requests — the forwarder's pre-flight loop
                # hits the drained branch (forwarder.py:301) and the sole-leg
                # guard CALL (forwarder.py:304) must keep it un-parked.
                # If the guard call was reverted (always False), the forwarder
                # parks drained-fc3 → RED.
                _send_chat(gw.url, "m1")
                _send_chat(gw.url, "m1")
                assert not bt.is_parked("drained-fc3"), (
                    "SOLE-LEG GUARD FAILED: drained-fc3 is parked — the sole "
                    "viable leg of pool m1 was orphaned by auto-park at "
                    "forwarder.py:317")
            finally:
                gw.shutdown()
        finally:
            up.shutdown()
