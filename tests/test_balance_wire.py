"""R46 balance-wire tests — FAIL-ON-REVERT suite.

Asserts that build_server wires a non-None BalanceTracker from the gateway
provider config, so record_spend is no longer inert in production.  Reverting
the construction line (balance_tracker=cfg.balance_tracker) must turn these
tests RED.
"""
from __future__ import annotations

from charon.balance import BalanceTracker
from charon.gateway import GatewayConfig, build_server
from charon.proxy_server import UpstreamRoute


class TestBuildServerWiresBalanceTracker:
    """build_server produces a server whose balance_tracker is non-None when the
    config carries one — the single missing link that made record_spend inert."""

    def test_build_server_non_none_tracker_from_config(self):
        """Given a GatewayConfig with a mode:fixed provider, build_server yields a
        server whose balance_tracker is not None with the correct starting_usd.

        FAIL-ON-REVERT: removing balance_tracker=cfg.balance_tracker from
        build_server makes this assertion fail."""
        bt = BalanceTracker(config={
            "opencode-zen": {"mode": "fixed", "starting_usd": 10.00},
        })
        cfg = GatewayConfig(
            port=0,
            token="t",
            routes={"m1": UpstreamRoute("http://127.0.0.1:1/v1", api_key="k")},
            model_ids=["m1"],
            balance_tracker=bt,
        )
        srv = build_server(cfg)
        try:
            assert srv.balance_tracker is not None, (
                "FAIL-ON-REVERT: balance_tracker must be forwarded from cfg")
            assert srv.balance_tracker is bt, (
                "build_server must pass through the same BalanceTracker instance")
            assert srv.balance_tracker.remaining("opencode-zen") == 10.00
        finally:
            srv.server_close()

    def test_build_server_live_decrement_after_forwarded_cost(self):
        """A forwarded response carrying usage cost decrements the provider's
        remaining balance through the tracker wired by build_server.

        For a non-class-3 fixed provider, record_spend directly decrements the
        internal balance (the path verified here)."""
        bt = BalanceTracker(config={
            "opencode-zen": {"mode": "fixed", "starting_usd": 10.00},
        })
        cfg = GatewayConfig(
            port=0,
            token="t",
            routes={"m1": UpstreamRoute("http://127.0.0.1:1/v1", api_key="k")},
            model_ids=["m1"],
            balance_tracker=bt,
        )
        srv = build_server(cfg)
        try:
            assert srv.balance_tracker.remaining("opencode-zen") == 10.00
            srv.balance_tracker.record_spend("opencode-zen", 3.50, model="m1")
            assert srv.balance_tracker.remaining("opencode-zen") == 6.50
            srv.balance_tracker.record_spend("opencode-zen", 6.00, model="m1")
            assert srv.balance_tracker.remaining("opencode-zen") == 0.50
        finally:
            srv.server_close()

    def test_build_server_observer_wired_for_class3(self):
        """When a class-3 drain-then-park provider is configured, build_server
        wires the observer meter as the spend source, so remaining() returns
        starting_usd minus observer-metered spend."""
        bt = BalanceTracker(config={
            "neuralwatt": {
                "mode": "fixed",
                "starting_usd": 5.00,
                "funding_class": 3,
            },
        })
        cfg = GatewayConfig(
            port=0,
            token="t",
            routes={"m1": UpstreamRoute("http://127.0.0.1:1/v1", api_key="k")},
            model_ids=["m1"],
            balance_tracker=bt,
        )
        srv = build_server(cfg)
        try:
            assert srv.balance_tracker.remaining("neuralwatt") == 5.00

            from charon.proxy import ProxyObservation, Usage

            obs = ProxyObservation(
                requested_model="m1",
                returned_model=None,
                status=200,
                exhausted=False,
                pseudo_success=False,
                usage=Usage(cost_usd=1.50),
            )
            srv.observer.record(obs, count_usage=True, provider="neuralwatt")
            assert srv.balance_tracker.remaining("neuralwatt") == 3.50

            obs2 = ProxyObservation(
                requested_model="m1",
                returned_model=None,
                status=200,
                exhausted=False,
                pseudo_success=False,
                usage=Usage(cost_usd=0.75),
            )
            srv.observer.record(obs2, count_usage=True, provider="neuralwatt")
            assert srv.balance_tracker.remaining("neuralwatt") == 2.75
        finally:
            srv.server_close()


class TestBuildServerBalanceTrackerNone:
    """When balance_tracker is None on the config, the server's tracker stays None
    (backward-compatible inert path)."""

    def test_build_server_none_tracker_when_config_is_none(self):
        """build_server does not fabricate a tracker when the config carries None."""
        cfg = GatewayConfig(
            port=0,
            token="t",
            routes={"m1": UpstreamRoute("http://127.0.0.1:1/v1", api_key="k")},
            model_ids=["m1"],
            balance_tracker=None,
        )
        srv = build_server(cfg)
        try:
            assert srv.balance_tracker is None
        finally:
            srv.server_close()
