"""Tests for the balance tracker module."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from charon.balance import BalanceTracker, _poll_deepseek, _poll_nanogpt, _poll_openrouter


class TestUnconfiguredProviderInert:
    """An unconfigured provider is completely inert — no drain, no spend, no drain state."""

    def test_remaining_returns_none_for_unconfigured(self):
        bt = BalanceTracker()
        assert bt.remaining("nonexistent") is None

    def test_should_drain_false_for_unconfigured(self):
        bt = BalanceTracker()
        assert bt.should_drain("nonexistent") is False

    def test_is_drained_false_for_unconfigured(self):
        bt = BalanceTracker()
        assert bt.is_drained("nonexistent") is False

    def test_record_spend_noop_for_unconfigured(self):
        bt = BalanceTracker()
        bt.record_spend("nonexistent", 5.0)  # should not raise


class TestFixedBalanceDecrement:
    """Fixed-mode providers start with operator-configured USD, decrement by spend."""

    def test_initial_balance_from_config(self):
        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 10.00}}
        )
        assert bt.remaining("opencode-zen") == 10.0

    def test_record_spend_decrements_balance(self):
        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 10.00}}
        )
        bt.record_spend("opencode-zen", 3.50)
        assert bt.remaining("opencode-zen") == 6.50
        bt.record_spend("opencode-zen", 6.0)
        assert bt.remaining("opencode-zen") == 0.50

    def test_record_spend_floors_at_zero(self):
        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 1.00}}
        )
        bt.record_spend("opencode-zen", 10.0)
        assert bt.remaining("opencode-zen") == 0.0

    def test_should_drain_true_when_positive(self):
        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 5.00}}
        )
        assert bt.should_drain("opencode-zen") is True

    def test_should_drain_false_when_zero(self):
        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 0.01}}
        )
        bt.record_spend("opencode-zen", 0.01)
        assert bt.remaining("opencode-zen") == 0.0
        assert bt.should_drain("opencode-zen") is False

    def test_is_drained_default_floor_zero(self):
        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 0.01}}
        )
        bt.record_spend("opencode-zen", 0.01)
        assert bt.is_drained("opencode-zen") is True

    def test_is_drained_custom_floor(self):
        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 2.00}}
        )
        assert bt.is_drained("opencode-zen", floor=3.0) is True
        assert bt.is_drained("opencode-zen", floor=1.0) is False

    def test_negative_spend_is_ignored(self):
        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 5.00}}
        )
        bt.record_spend("opencode-zen", -1.0)
        assert bt.remaining("opencode-zen") == 5.0  # negative spend is ignored

    def test_record_spend_noop_for_poll_provider(self):
        bt = BalanceTracker(
            config={
                "deepseek": {
                    "mode": "poll",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "sk-test",
                }
            }
        )
        bt.record_spend("deepseek", 10.0)
        assert True


class TestShouldDrainDrainTransitions:
    """should_drain and is_drained reflect the balance state edge-to-edge."""

    def test_drain_to_skip_transition(self):
        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 1.00}}
        )
        assert bt.should_drain("opencode-zen") is True
        assert bt.is_drained("opencode-zen") is False
        bt.record_spend("opencode-zen", 0.90)
        assert bt.should_drain("opencode-zen") is True
        bt.record_spend("opencode-zen", 0.10)
        assert bt.remaining("opencode-zen") == 0.0
        assert bt.should_drain("opencode-zen") is False
        assert bt.is_drained("opencode-zen") is True

    def test_drain_false_when_not_tracked(self):
        bt = BalanceTracker()
        assert bt.should_drain("any-provider") is False


class TestPollAdapterParsing:
    """Each poll adapter parse function returns correct USD from mock JSON."""

    def test_deepseek_parse_total_remaining(self):
        body = json.dumps({"balance": {"total_remaining": 42.50}}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            result = _poll_deepseek("https://api.deepseek.com/v1", "sk-test", 20.0)
            assert result == 42.50

    def test_deepseek_parse_total_balance_fallback(self):
        body = json.dumps({"balance": {"total_balance": 7.33}}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            result = _poll_deepseek("https://api.deepseek.com/v1", "sk-test", 20.0)
            assert result == 7.33

    def test_deepseek_no_balance_dict_returns_none(self):
        body = json.dumps({"data": "no balance key"}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            result = _poll_deepseek("https://api.deepseek.com/v1", "sk-test", 20.0)
            assert result is None

    def test_openrouter_parse_credits(self):
        body = json.dumps({"data": {"credits": 55.00}}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            result = _poll_openrouter("https://openrouter.ai/api/v1", "sk-test", 20.0)
            assert result == 55.00

    def test_openrouter_no_data_returns_none(self):
        body = json.dumps({"not_data": {}}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            result = _poll_openrouter("https://openrouter.ai/api/v1", "sk-test", 20.0)
            assert result is None

    def test_nanogpt_parse_balance(self):
        body = json.dumps({"balance": 3.75}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            result = _poll_nanogpt("https://nano-gpt.com/api/v1", "sk-test", 20.0)
            assert result == 3.75

    def test_poll_adapter_handles_http_error(self):
        import urllib.error

        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.side_effect = urllib.error.URLError("timeout")
            result = _poll_deepseek("https://api.deepseek.com/v1", "sk-test", 20.0)
            assert result is None

    def test_poll_adapter_handles_non_numeric_balance(self):
        body = json.dumps({"balance": {"total_remaining": "twelve"}}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            result = _poll_deepseek("https://api.deepseek.com/v1", "sk-test", 20.0)
            assert result is None


class TestForcePoll:
    """force_poll() sync-polls a provider; counters track success/error."""

    def test_force_poll_not_poll_mode_returns_none(self):
        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 5.00}}
        )
        assert bt.force_poll("opencode-zen") is None

    def test_force_poll_unconfigured_returns_none(self):
        bt = BalanceTracker()
        assert bt.force_poll("nonexistent") is None

    def test_force_poll_counts_success(self):
        body = json.dumps({"balance": {"total_remaining": 100.0}}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            bt = BalanceTracker(
                config={
                    "deepseek": {
                        "mode": "poll",
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": "sk-test",
                    }
                }
            )
            result = bt.force_poll("deepseek")
            assert result == 100.0
            assert bt.counters().get("poll_success", 0) >= 1

    def test_force_poll_counts_error(self):
        import urllib.error

        with patch(
            "charon.balance._POLL_ADAPTERS",
            {"deepseek": MagicMock(side_effect=urllib.error.URLError("timeout"))},
        ):
            bt = BalanceTracker(
                config={
                    "deepseek": {
                        "mode": "poll",
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": "sk-test",
                    }
                }
            )
            result = bt.force_poll("deepseek")
            assert result is None
            assert bt.counters().get("poll_error", 0) >= 1


class TestConfigure:
    """Runtime config update via configure()."""

    def test_configure_add_provider(self):
        bt = BalanceTracker()
        bt.configure(
            "nanogpt",
            "poll",
            base_url="https://nano-gpt.com/api/v1",
            api_key="sk-test",
        )
        assert bt.remaining("nanogpt") is None
        assert bt.should_drain("nanogpt") is False

    def test_configure_fixed_starting_usd(self):
        bt = BalanceTracker()
        bt.configure("opencode-zen", "fixed", starting_usd=20.00)
        assert bt.remaining("opencode-zen") == 20.0
        assert bt.should_drain("opencode-zen") is True

    def test_configure_overwrites_previous(self):
        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 10.00}}
        )
        bt.configure("opencode-zen", "fixed", starting_usd=50.00)
        assert bt.remaining("opencode-zen") == 50.0


class TestCounterUnconfiguredProvider:
    """Per-reason counters are tracked."""

    def test_counters_initially_empty(self):
        bt = BalanceTracker()
        assert bt.counters() == {}

    def test_force_poll_success_counter(self):
        body = json.dumps({"balance": {"total_remaining": 99.0}}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            bt = BalanceTracker(
                config={
                    "deepseek": {
                        "mode": "poll",
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": "sk-test",
                    }
                }
            )
            bt.force_poll("deepseek")
            assert bt.counters().get("poll_success") == 1


class TestThreadSafety:
    """Concurrent record_spend calls don't corrupt the balance."""

    def test_concurrent_record_spend(self):
        import threading

        bt = BalanceTracker(
            config={"opencode-zen": {"mode": "fixed", "starting_usd": 100.00}}
        )
        errors = []

        def spend_cents():
            for _ in range(100):
                try:
                    bt.record_spend("opencode-zen", 0.01)
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=spend_cents) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert bt.remaining("opencode-zen") >= 0.0
        assert bt.remaining("opencode-zen") <= 100.0


class TestPollerBrowserUA:
    """P5: every balance poller must send the shared browser-like UA so a
    Cloudflare-fronted balance endpoint (error 1010 → 403) does not silently
    corrupt the drain signal. The UA must be the ONE shared constant, never the
    old non-browser ``charon-proxy/0.1`` and never a library default."""

    def _captured_ua(self, poll_fn, base, key):
        body = json.dumps({}).encode()
        mock = MagicMock()
        mock.read.return_value = body
        with patch("urllib.request.build_opener") as bo:
            bo.return_value.open.return_value = mock
            poll_fn(base, key, 20.0)
            req = bo.return_value.open.call_args[0][0]
        # urllib normalizes header keys to title-case with the rest lowercased
        return req.get_header("User-agent")

    def test_deepseek_poller_sends_shared_browser_ua(self):
        from charon.netutil import BROWSER_UA

        ua = self._captured_ua(_poll_deepseek, "https://api.deepseek.com/v1", "sk-x")
        assert ua == BROWSER_UA
        assert ua != "charon-proxy/0.1"
        assert not ua.lower().startswith("python-urllib")

    def test_openrouter_poller_sends_shared_browser_ua(self):
        from charon.netutil import BROWSER_UA

        ua = self._captured_ua(_poll_openrouter, "https://openrouter.ai/api/v1", "sk-x")
        assert ua == BROWSER_UA
        assert ua != "charon-proxy/0.1"

    def test_nanogpt_poller_sends_shared_browser_ua(self):
        from charon.netutil import BROWSER_UA

        ua = self._captured_ua(_poll_nanogpt, "https://nano-gpt.com/api/v1", "sk-x")
        assert ua == BROWSER_UA
        assert ua != "charon-proxy/0.1"
