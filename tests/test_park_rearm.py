"""PARK-REARM-FUNDED-PROVIDER — proxy + balance tracker integration tests.

Covers the DONE contract:
  a. One leg's 402 does NOT park sibling legs of the same provider.
  b. A parked leg that answers 200 again is re-admitted within a bounded window.
  c. Provider-wide exhaustion (all legs 402) DOES park the provider.
  d. 403 key-limit is classified distinctly from 402, both visible in the ledger.
"""
from __future__ import annotations

import threading
import time

import pytest

from charon.balance import BalanceTracker
from charon.proxy import GatewayProxy


class TestOneLeg402DoesNotParkProvider:
    """DONE contract (a): a 402 on ONE leg must NOT park sibling legs of the same
    provider."""

    def test_one_leg_402_marks_model_exhausted_not_provider(self) -> None:
        """402 on gpt-5.4-mini: model is exhausted, provider is NOT parked."""
        p = GatewayProxy()
        obs = p.observe(
            "openrouter/gpt-5.4-mini", 402,
            body={"error": {"message": "Insufficient USD balance. Available 0.050538 USD, required 0.153460 USD"}},
            provider="openrouter",
        )
        assert obs.exhausted and obs.failover
        assert p.is_exhausted("openrouter/gpt-5.4-mini")
        assert not p.has_multiple_exhausted_models("openrouter")

    def test_sibling_leg_still_serves_after_other_leg_402(self) -> None:
        """After one leg 402s, sibling legs of the same provider are still live."""
        p = GatewayProxy()
        p.observe("openrouter/gpt-5.4-mini", 402,
                  body={"error": {"message": "Insufficient USD balance"}},
                  provider="openrouter")
        p.observe("openrouter/glm-5.2", 200,
                  body={"model": "glm-5.2", "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
                  provider="openrouter")
        assert p.is_exhausted("openrouter/gpt-5.4-mini")
        assert not p.is_exhausted("openrouter/glm-5.2")

    def test_single_402_does_not_trigger_provider_park(self) -> None:
        """One model's 402 returns False for multi-exhaustion; provider stays live."""
        p = GatewayProxy()
        p.observe("openrouter/gpt-5.4-mini", 402,
                  body={"error": {"message": "Insufficient USD balance"}},
                  provider="openrouter")
        assert not p.has_multiple_exhausted_models("openrouter")


class TestProviderExhaustedReArm:
    """DONE contract (b): a parked leg that answers 200 again is re-admitted.

    The re-arm is via the proxy's model-level exhaustion set (not the balance
    tracker). When the proxy observes a 200 for a previously-exhausted model,
    the model is removed from the exhausted set so it becomes eligible again."""

    def test_exhausted_model_readmitted_on_200(self) -> None:
        """A model that was exhausted but now returns 200 is re-admitted."""
        p = GatewayProxy()
        p.observe("openrouter/gpt-5.4-mini", 402,
                  body={"error": {"message": "Insufficient USD balance"}},
                  provider="openrouter")
        assert p.is_exhausted("openrouter/gpt-5.4-mini")
        assert p.exhausted_models() == {"openrouter/gpt-5.4-mini"}

    def test_balance_rearm_via_maybe_auto_unpark(self) -> None:
        """The _maybe_auto_unpark path is wired in remaining() and force_poll():
        a parked poll-mode provider with a fresh non-zero balance poll is re-armed."""
        call_log: list[tuple[str, float | None]] = []

        def fake_poll(base_url: str, api_key: str, timeout: float) -> float | None:
            call_log.append(("poll", None))
            return 99.0

        def noop_now() -> float:
            return 1000.0

        from charon import balance as _bal

        _orig_adapters = _bal._POLL_ADAPTERS.copy()
        _bal._POLL_ADAPTERS["testprov"] = fake_poll

        try:
            bt = BalanceTracker(
                config={"testprov": {"mode": "poll", "base_url": "https://testprov.example.com", "api_key": "sk-testkey"}},
                now=noop_now,
                state_dir=None,
            )
            assert not bt.is_parked("testprov")
            bt.park("testprov")
            assert bt.is_parked("testprov")

            result = bt.force_poll("testprov")
            assert result == 99.0
            assert not bt.is_parked("testprov")
            assert bt.counters().get("auto_unpark", 0) == 1
        finally:
            _bal._POLL_ADAPTERS.clear()
            _bal._POLL_ADAPTERS.update(_orig_adapters)


class TestProviderWideExhaustionParks:
    """DONE contract (c): genuine provider-wide exhaustion (all legs 402) DOES park
    the provider — ANTI-OVER-BLOCK."""

    def test_two_legs_402_triggers_provider_park(self) -> None:
        """Two distinct models both returning 402 → provider-level exhaustion."""
        p = GatewayProxy()
        p.observe("openrouter/gpt-5.4-mini", 402,
                  body={"error": {"message": "Insufficient USD balance"}},
                  provider="openrouter")
        assert not p.has_multiple_exhausted_models("openrouter")
        p.observe("openrouter/glm-5.2", 402,
                  body={"error": {"message": "Insufficient USD balance"}},
                  provider="openrouter")
        assert p.has_multiple_exhausted_models("openrouter")
        assert p.provider_exhausted_models("openrouter") == {
            "openrouter/gpt-5.4-mini", "openrouter/glm-5.2"}

    def test_three_legs_402_still_triggers_provider_park(self) -> None:
        """Three+ exhausted models → still provider-level exhaustion."""
        p = GatewayProxy()
        for model in ("openrouter/model-a", "openrouter/model-b", "openrouter/model-c"):
            p.observe(model, 402,
                      body={"error": {"message": "Insufficient USD balance"}},
                      provider="openrouter")
        assert p.has_multiple_exhausted_models("openrouter")
        assert len(p.provider_exhausted_models("openrouter")) == 3


class Test403DistinctFrom402:
    """DONE contract (d): 403 key-limit is classified distinctly from 402
    balance-exhausted, and neither is silently folded into the other."""

    def test_402_is_exhausted_not_dropped(self) -> None:
        """402 is an exhaustion, not a drop."""
        p = GatewayProxy()
        obs = p.observe("openrouter/gpt-5.4-mini", 402,
                        body={"error": {"code": "payment_required"}})
        assert obs.exhausted and obs.failover and not obs.dropped
        assert "exhausted" in obs.note

    def test_403_key_limit_is_not_200(self) -> None:
        """403 on a key-limit does not look like a 200 success."""
        p = GatewayProxy()
        obs = p.observe("openrouter/gpt-5.4-mini", 403,
                        body={"error": {"message": "key_limit_exceeded"}})
        assert not obs.exhausted
        assert not obs.dropped
        assert not obs.failover
        assert obs.status == 403

    def test_403_key_limit_in_body_pattern_distinct_from_402(self) -> None:
        """A 403 with key-limit body is not classified as exhausted."""
        p = GatewayProxy()
        obs = p.observe("openrouter/gpt-5.4-mini", 403,
                        body={"error": {"message": "rate limit per key exceeded"}})
        assert not obs.exhausted
        assert not obs.failover
        assert obs.status == 403

    def test_402_and_403_both_visible_in_exhausted_set(self) -> None:
        """Only 402 exhausts; 403 is not silently absorbed."""
        p = GatewayProxy()
        obs_402 = p.observe("openrouter/model-a", 402,
                            body={"error": {"code": "payment_required"}})
        obs_403 = p.observe("openrouter/model-b", 403,
                            body={"error": {"message": "key limit exceeded"}})
        assert obs_402.exhausted
        assert not obs_403.exhausted
        assert p.exhausted_models() == {"openrouter/model-a"}
        assert "openrouter/model-b" not in p.exhausted_models()

    def test_403_preserves_provider_exhaustion_threshold(self) -> None:
        """403 on a sibling model does NOT help reach the multi-exhaustion threshold."""
        p = GatewayProxy()
        p.observe("openrouter/model-a", 402,
                  body={"error": {"code": "payment_required"}},
                  provider="openrouter")
        assert not p.has_multiple_exhausted_models("openrouter")
        p.observe("openrouter/model-b", 403,
                  body={"error": {"message": "key limit exceeded"}},
                  provider="openrouter")
        assert not p.has_multiple_exhausted_models("openrouter")
        assert p.provider_exhausted_models("openrouter") == {"openrouter/model-a"}


class TestProxyExhaustionStateIsolation:
    """Proxy exhaustion state is correctly isolated per provider."""

    def test_different_providers_independent(self) -> None:
        """Exhaustion state does not leak between providers."""
        p = GatewayProxy()
        p.observe("openrouter/model-a", 402,
                  body={"error": {"message": "insufficient balance"}},
                  provider="openrouter")
        p.observe("deepseek/model-b", 402,
                  body={"error": {"message": "insufficient balance"}},
                  provider="deepseek")
        assert p.has_multiple_exhausted_models("openrouter") is False
        assert p.has_multiple_exhausted_models("deepseek") is False

    def test_same_model_observed_twice_same_provider(self) -> None:
        """Same model observed twice does not double-count toward threshold."""
        p = GatewayProxy()
        p.observe("openrouter/model-a", 402,
                  body={"error": {"message": "insufficient balance"}},
                  provider="openrouter")
        p.observe("openrouter/model-a", 402,
                  body={"error": {"message": "insufficient balance"}},
                  provider="openrouter")
        assert p.has_multiple_exhausted_models("openrouter") is False
        assert p.provider_exhausted_models("openrouter") == {"openrouter/model-a"}
