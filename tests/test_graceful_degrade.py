"""FAIL-ON-REVERT tests for GRACEFUL-DEGRADE — three North Star behaviors:

  1. RATE-LIMIT AS BACKPRESSURE (THROTTLE): when only one viable provider
     remains and it is rate-limited, the session is THROTTLED (queued/slowed)
     to its Retry-After instead of erroring.
  2. ALERT ON IMPACT: when routing degrades (throttled last-resort, OR a
     prepaid leg hits zero), the operator is NOTIFIED via the degradation
     callback with the provider-to-refill.
  3. AUTO-RECOVER ON REFILL: park on exhaustion, restore credit, probe passes
     → next request routes back with no manual reconfig.
     FUNDING-CLASS-AWARE (shared taxonomy R11 DRAIN-THEN-PARK):
       fc=1 (free-recurring) / fc=2 (flat-sub) → auto-rearm on poll recovery
       fc=3 (prepaid) → re-arm ONLY on operator top_up()
       no funding_class → auto-rearm on poll recovery (backward-compat)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from charon.balance import BalanceTracker, DegradationState
from charon.failover import backpressure_delay, classify_routing_health, emit_degradation_alert
from charon.pools import PoolEntry
from charon.router import StaticRouter

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _mk_entry(agent: str = "opencode", model: str = "test-model",
              free: bool = False, cost_rank: int = 10) -> PoolEntry:
    return PoolEntry(
        agent=agent, model=model, cost_tier="ptk", cost_rank=cost_rank,
        code_safe=True, free=free,
    )


def _mk_pool(*entries: PoolEntry) -> list[PoolEntry]:
    return list(entries)


# ---------------------------------------------------------------------------
# Behavior 1: RATE-LIMIT AS BACKPRESSURE (THROTTLE)
# ---------------------------------------------------------------------------

class TestRateLimitAsBackpressure:
    """FAIL-ON-REVERT: throttle must serve the rate-limited provider, not fail."""

    def test_classify_normal_when_viable_candidates_exist(self):
        """NORMAL when at least one viable candidate exists."""
        assert classify_routing_health(viable_candidates=2,
                                        rate_limited_candidates=0) == "normal"
        assert classify_routing_health(viable_candidates=1,
                                        rate_limited_candidates=1) == "normal"

    def test_classify_throttled_when_only_rate_limited_remain(self):
        """THROTTLED when zero viable but at least one rate-limited candidate."""
        assert classify_routing_health(viable_candidates=0,
                                        rate_limited_candidates=1) == "throttled"
        assert classify_routing_health(viable_candidates=0,
                                        rate_limited_candidates=3) == "throttled"

    def test_classify_degraded_when_nothing_remains(self):
        """DEGRADED when zero viable AND zero rate-limited candidates."""
        assert classify_routing_health(viable_candidates=0,
                                        rate_limited_candidates=0) == "degraded"

    def test_backpressure_delay_clamps_to_range(self):
        """Throttle delay is 1..60s, clamping both ends."""
        assert backpressure_delay(0.5) == 1.0
        assert backpressure_delay(5.0) == 5.0
        assert backpressure_delay(120.0) == 60.0
        assert backpressure_delay(-1.0) == 1.0

    def test_backpressure_delay_respects_retry_after(self):
        """A standard Retry-After (e.g. 30s) is passed through."""
        assert backpressure_delay(30.0) == 30.0

    def test_rate_limit_tracking_in_balance_tracker(self):
        """record_rate_limit + is_rate_limited + seconds_remaining cycle."""
        bt = BalanceTracker()
        assert not bt.is_rate_limited("prov-a")

        bt.record_rate_limit("prov-a", 30.0)
        assert bt.is_rate_limited("prov-a")
        remaining = bt.rate_limit_seconds_remaining("prov-a")
        assert 0 < remaining <= 30.0

    def test_rate_limit_expires(self):
        """An expired rate-limit window is cleaned up lazily."""
        fake_now = [100.0]

        class ClockedTracker(BalanceTracker):
            def __init__(self):
                super().__init__()
                self._now = lambda: fake_now[0]

        bt = ClockedTracker()
        bt.record_rate_limit("prov-a", 10.0)  # expires at 110.0
        assert bt.is_rate_limited("prov-a")

        fake_now[0] = 111.0  # past expiry
        assert not bt.is_rate_limited("prov-a")
        assert bt.rate_limit_seconds_remaining("prov-a") == 0.0

    def test_record_rate_limit_none_clears(self):
        """retry_after_s=None clears the rate-limit."""
        bt = BalanceTracker()
        bt.record_rate_limit("prov-a", 30.0)
        assert bt.is_rate_limited("prov-a")
        bt.record_rate_limit("prov-a", None)
        assert not bt.is_rate_limited("prov-a")


# ---------------------------------------------------------------------------
# Behavior 2: ALERT ON IMPACT
# ---------------------------------------------------------------------------

class TestAlertOnImpact:
    """FAIL-ON-REVERT: degradation must fire the operator callback."""

    def test_degradation_callback_fires_on_throttled_alert(self):
        """A THROTTLED alert fires the wired callback with provider + reason."""
        bt = BalanceTracker()
        alerts: list[tuple[str, str]] = []

        def _collect(provider: str, reason: str) -> None:
            alerts.append((provider, reason))

        bt.set_degradation_callback(_collect)
        bt.notify_throttled("rate-limited-prov")
        assert len(alerts) == 1
        assert alerts[0][0] == "rate-limited-prov"
        assert "throttled" in alerts[0][1].lower() or "refill" in alerts[0][1]

    def test_degradation_callback_fires_on_exhausted_alert(self):
        """An EXHAUSTED alert fires the callback with provider + reason."""
        bt = BalanceTracker()
        alerts: list[tuple[str, str]] = []

        def _collect(provider: str, reason: str) -> None:
            alerts.append((provider, reason))

        bt.set_degradation_callback(_collect)
        bt.notify_exhausted("drained-prov")
        assert len(alerts) == 1
        assert alerts[0][0] == "drained-prov"
        assert "refill" in alerts[0][1]

    def test_no_callback_no_crash(self):
        """No callback wired → alerts are silent no-ops (money path safe)."""
        bt = BalanceTracker()
        bt.notify_throttled("p")   # must not raise
        bt.notify_exhausted("p")   # must not raise

    def test_callback_exception_does_not_break_money_path(self):
        """A crashing callback does not propagate — money path is protected."""
        bt = BalanceTracker()

        def _crash(_provider: str, _reason: str) -> None:
            raise RuntimeError("alert sink is down")

        bt.set_degradation_callback(_crash)
        bt.notify_throttled("p")    # must not raise
        bt.notify_exhausted("p")    # must not raise

    def test_emit_degradation_alert_throttled_routes_to_notify_throttled(self):
        """emit_degradation_alert with reason='throttled' calls notify_throttled."""
        bt = BalanceTracker()
        alerts: list[str] = []

        def _collect(provider: str, _reason: str) -> None:
            alerts.append(provider)

        bt.set_degradation_callback(_collect)
        emit_degradation_alert(bt, "prov-x", "throttled")
        assert alerts == ["prov-x"]

    def test_emit_degradation_alert_exhausted_routes_to_notify_exhausted(self):
        """emit_degradation_alert with reason='exhausted' calls notify_exhausted."""
        bt = BalanceTracker()
        alerts: list[str] = []

        def _collect(provider: str, _reason: str) -> None:
            alerts.append(provider)

        bt.set_degradation_callback(_collect)
        emit_degradation_alert(bt, "prov-y", "exhausted")
        assert alerts == ["prov-y"]


# ---------------------------------------------------------------------------
# Behavior 3: AUTO-RECOVER ON REFILL (funding-class-aware)
# ---------------------------------------------------------------------------

class TestAutoRecoverOnRefill:
    """FAIL-ON-REVERT: each funding class's re-arm path must be asserted."""

    # -- fc=3 prepaid: re-arm ONLY on operator top_up() ---------------

    def test_fc3_prepaid_does_not_auto_unpark_on_poll_recovery(self):
        """FAIL-ON-REVERT: a parked fc=3 poll provider must NOT auto-rearm on
        poll recovery — it requires explicit top_up()."""
        bt = BalanceTracker(config={
            "openrouter": {
                "mode": "poll",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-test",
                "funding_class": 3,
            }
        })
        bt.park("openrouter")
        assert bt.is_parked("openrouter")

        body = json.dumps({"data": {"credits": 50.0}}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            remaining = bt.remaining("openrouter")

        assert remaining == 50.0
        assert bt.is_parked("openrouter"), (
            "fc=3 prepaid must NOT auto-rearm on poll recovery — "
            "requires explicit top_up()")

    def test_fc3_prepaid_rearms_on_top_up(self):
        """FAIL-ON-REVERT: a parked fc=3 provider re-arms when the operator
        tops up — the top-up IS the health probe."""
        bt = BalanceTracker(config={
            "opencode-zen": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)
        bt.park("opencode-zen")
        assert bt.is_parked("opencode-zen")

        bt.top_up("opencode-zen", 10.0)
        assert not bt.is_parked("opencode-zen"), (
            "fc=3 prepaid must re-arm on operator top_up()")
        assert bt.counters().get("auto_unpark", 0) == 1

    # -- fc=1 / fc=2: auto-rearm on poll recovery --------------------

    def test_fc1_free_recurring_auto_unparks_on_poll_recovery(self):
        """FAIL-ON-REVERT: fc=1 auto-rearms on poll recovery."""
        bt = BalanceTracker(config={
            "nanogpt": {
                "mode": "poll",
                "base_url": "https://api.nanogpt.ai",
                "api_key": "sk-test",
                "funding_class": 1,
            }
        })
        bt.park("nanogpt")
        assert bt.is_parked("nanogpt")

        body = json.dumps({"balance": 5.0}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            remaining = bt.remaining("nanogpt")

        assert remaining == 5.0
        assert not bt.is_parked("nanogpt"), (
            "fc=1 free-recurring must auto-rearm on poll recovery")

    def test_fc2_flat_sub_auto_unparks_on_poll_recovery(self):
        """FAIL-ON-REVERT: fc=2 auto-rearms on poll recovery."""
        bt = BalanceTracker(config={
            "nanogpt": {
                "mode": "poll",
                "base_url": "https://api.nanogpt.ai",
                "api_key": "sk-test",
                "funding_class": 2,
            }
        })
        bt.park("nanogpt")
        assert bt.is_parked("nanogpt")

        body = json.dumps({"balance": 7.0}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            remaining = bt.remaining("nanogpt")

        assert remaining == 7.0
        assert not bt.is_parked("nanogpt"), (
            "fc=2 flat-sub must auto-rearm on poll recovery")

    def test_fc4_payg_auto_unparks_on_poll_recovery(self):
        """FAIL-ON-REVERT: fc=4 auto-rearms on poll recovery."""
        bt = BalanceTracker(config={
            "deepseek": {
                "mode": "poll",
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-test",
                "funding_class": 4,
            }
        })
        bt.park("deepseek")
        assert bt.is_parked("deepseek")

        body = json.dumps({"balance": {"total_remaining": 3.0}}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            remaining = bt.remaining("deepseek")

        assert remaining == 3.0
        assert not bt.is_parked("deepseek"), (
            "fc=4 PAYG must auto-rearm on poll recovery")

    # -- no funding class: backward-compat auto-rearm -----------------

    def test_no_funding_class_auto_unparks_on_poll_recovery(self):
        """Backward-compat: unclassified poll provider auto-rearms."""
        bt = BalanceTracker(config={
            "openrouter": {
                "mode": "poll",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-test",
            }
        })
        bt.park("openrouter")
        assert bt.is_parked("openrouter")

        body = json.dumps({"data": {"credits": 12.34}}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            remaining = bt.remaining("openrouter")

        assert remaining == 12.34
        assert not bt.is_parked("openrouter"), (
            "unclassified poll provider must auto-rearm on poll recovery")

    # -- top_up does NOT re-arm non-fc-3 providers -------------------

    def test_top_up_does_not_unpark_non_fc3(self):
        """top_up() on a non-fc-3 provider does not auto-unpark (only fc=3
        prepaid gets the auto-recover on top-up)."""
        bt = BalanceTracker(config={
            "provider": {
                "mode": "fixed",
                "starting_balance": 5.0,
                "funding_class": 1,
            }
        })
        bt.park("provider")
        assert bt.is_parked("provider")
        bt.top_up("provider", 10.0)
        assert bt.is_parked("provider"), (
            "top_up() must NOT auto-unpark non-fc-3 providers")

    def test_top_up_negative_is_ignored_no_unpark(self):
        """Negative top_up is a no-op and does not re-arm."""
        bt = BalanceTracker(config={
            "provider": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            }
        })
        bt.park("provider")
        bt.top_up("provider", -5.0)
        assert bt.is_parked("provider")

    def test_zero_amount_top_up_no_op(self):
        """Zero-amount top_up is a no-op."""
        bt = BalanceTracker(config={
            "provider": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            }
        })
        bt.park("provider")
        bt.top_up("provider", 0.0)
        assert bt.is_parked("provider")

    # -- force_poll also respects funding-class-aware re-arm ---------

    def test_force_poll_fc3_does_not_auto_unpark(self):
        """force_poll on a parked fc=3 poll provider does NOT auto-rearm."""
        bt = BalanceTracker(config={
            "openrouter": {
                "mode": "poll",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-test",
                "funding_class": 3,
            }
        })
        bt.park("openrouter")
        assert bt.is_parked("openrouter")

        body = json.dumps({"data": {"credits": 20.0}}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            result = bt.force_poll("openrouter")

        assert result == 20.0
        assert bt.is_parked("openrouter"), (
            "fc=3 force_poll must NOT auto-rearm — prepaid requires top_up()")

    # -- record_exhaustion → park → top_up → re-arm cycle -----------

    def test_full_rearm_cycle_record_exhaustion_park_top_up_unpark(self):
        """End-to-end: record_exhaustion parks, top_up re-arms."""
        bt = BalanceTracker(config={
            "prepaid-key": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)
        assert not bt.is_parked("prepaid-key")

        bt.record_exhaustion("prepaid-key")
        assert bt.is_parked("prepaid-key")
        assert bt.counters().get("auto_park", 0) == 1

        bt.top_up("prepaid-key", 15.0)
        assert not bt.is_parked("prepaid-key"), (
            "fc=3 prepaid must re-arm on top_up after record_exhaustion park")
        assert bt.counters().get("auto_unpark", 0) == 1


# ---------------------------------------------------------------------------
# Park-aware routing integration (router.py)
# ---------------------------------------------------------------------------

class TestParkAwareRouting:
    """FAIL-ON-REVERT: parked pool entry keys must be excluded from routing."""

    def test_route_pool_excludes_parked_keys(self):
        """route_pool() skips entries whose key is in router.parked_keys."""
        e1 = _mk_entry(agent="a", model="m1")
        e2 = _mk_entry(agent="b", model="m2")
        pool = _mk_pool(e1, e2)
        router = StaticRouter(pools={"test": pool})
        router.parked_keys = {e1.key}

        result = router.route_pool("test")
        assert result.key == e2.key, (
            "parked entry must be excluded from route_pool()")

    def test_route_pool_parked_plus_exclude_merged(self):
        """parked_keys and per-call exclude are merged correctly."""
        e1 = _mk_entry(agent="a", model="m1")
        e2 = _mk_entry(agent="b", model="m2")
        e3 = _mk_entry(agent="c", model="m3")
        pool = _mk_pool(e1, e2, e3)
        router = StaticRouter(pools={"test": pool})
        router.parked_keys = {e1.key}

        result = router.route_pool("test", exclude={e2.key})
        assert result.key == e3.key, (
            "parked_keys + exclude must both be honored")

    def test_route_pool_all_parked_raises(self):
        """When all entries are parked, route_pool raises (clean exhausted)."""
        e1 = _mk_entry(agent="a", model="m1")
        pool = _mk_pool(e1)
        router = StaticRouter(pools={"test": pool})
        router.parked_keys = {e1.key}

        import pytest
        with pytest.raises(RuntimeError, match="pool exhausted"):
            router.route_pool("test")

    def test_default_parked_keys_is_empty(self):
        """A fresh StaticRouter starts with empty parked_keys."""
        router = StaticRouter()
        assert router.parked_keys == set()


# ---------------------------------------------------------------------------
# DegradationState enum
# ---------------------------------------------------------------------------

class TestDegradationState:
    def test_enum_values_are_distinct(self):
        assert DegradationState.NORMAL is not DegradationState.THROTTLED
        assert DegradationState.THROTTLED is not DegradationState.DEGRADED
        assert DegradationState.NORMAL is not DegradationState.DEGRADED
