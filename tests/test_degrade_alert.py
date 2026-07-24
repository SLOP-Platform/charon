"""Tests for the degrade-alert module.

Fail-on-revert: a simulated park/last-resort transition emits the alert;
revert → no alert → RED.
"""
from __future__ import annotations

import unittest

from charon.balance import BalanceTracker
from charon.degrade_alert import DegradeAlert


class TestLastResortAlert(unittest.TestCase):
    """alert_last_resort surfaces pool-thinning when the last leg serves."""

    def test_log_message_contains_provider_model_and_failover_count(self):
        da = DegradeAlert()
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_last_resort(
                provider="prov-a", model="gpt-4", failover_count=2)

        self.assertEqual(len(cm.output), 1)
        line = cm.output[0]
        self.assertIn("LAST-RESORT", line)
        self.assertIn("prov-a", line)
        self.assertIn("gpt-4", line)
        self.assertIn("2 failovers", line)
        self.assertIn("pool thinning", line)

    def test_reason_appended_when_provided(self):
        da = DegradeAlert()
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_last_resort(
                provider="prov-b", model="claude-3", failover_count=3,
                reason="throttled")

        self.assertEqual(len(cm.output), 1)
        self.assertIn("(throttled)", cm.output[0])

    def test_counter_increments(self):
        da = DegradeAlert()
        da.alert_last_resort(provider="p", model="m", failover_count=1)
        da.alert_last_resort(provider="q", model="m", failover_count=0)
        self.assertEqual(da.counters["last_resort"], 2)


class TestPrepaidZeroAlert(unittest.TestCase):
    """alert_prepaid_zero surfaces a silent park of a drain-then-park
    provider."""

    def test_log_message_contains_provider_and_spill(self):
        da = DegradeAlert()
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_prepaid_zero(
                provider="openrouter", model="gpt-4o", spill_to="deepseek")

        self.assertEqual(len(cm.output), 1)
        line = cm.output[0]
        self.assertIn("PREPAID-LEG-ZERO", line)
        self.assertIn("openrouter", line)
        self.assertIn("spilled to deepseek", line)
        self.assertIn("gpt-4o", line)

    def test_no_spill_omitted_from_message(self):
        da = DegradeAlert()
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_prepaid_zero(provider="openrouter")

        self.assertEqual(len(cm.output), 1)
        self.assertNotIn("spilled to", cm.output[0])

    def test_counter_increments(self):
        da = DegradeAlert()
        da.alert_prepaid_zero(provider="p")
        da.alert_prepaid_zero(provider="q", spill_to="r")
        self.assertEqual(da.counters["prepaid_zero"], 2)


class TestPoolTooThinAlert(unittest.TestCase):
    """alert_pool_too_thin escalates loudly when all routes are excluded or
    every provider is exhausted."""

    def test_log_message_contains_model_and_reason(self):
        da = DegradeAlert()
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_pool_too_thin(model="gpt-4", total=5)

        self.assertEqual(len(cm.output), 1)
        line = cm.output[0]
        self.assertIn("POOL-TOO-THIN", line)
        self.assertIn("gpt-4", line)
        self.assertIn("all routes excluded", line)
        self.assertIn("5 routes", line)

    def test_all_providers_exhausted_reason(self):
        da = DegradeAlert()
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_pool_too_thin(
                model="claude-3", total=3,
                reason="all providers exhausted")

        self.assertEqual(len(cm.output), 1)
        self.assertIn("all providers exhausted", cm.output[0])

    def test_counter_increments(self):
        da = DegradeAlert()
        da.alert_pool_too_thin(model="m")
        da.alert_pool_too_thin(model="n", total=2)
        self.assertEqual(da.counters["pool_too_thin"], 2)


class TestFailOnRevert(unittest.TestCase):
    """Fail-on-revert: a simulated park/last-resort transition emits the
    alert; revert → no alert → RED."""

    def test_last_resort_transition_emits_alert(self):
        """Simulate a last-resort transition: alert fires."""
        da = DegradeAlert()
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_last_resort(
                provider="prov-a", model="gpt-4", failover_count=3,
                reason="throttled")
        self.assertEqual(len(cm.output), 1)
        self.assertIn("LAST-RESORT", cm.output[0])
        self.assertIn("prov-a", cm.output[0])
        self.assertIn("throttled", cm.output[0])
        self.assertEqual(da.counters["last_resort"], 1)

    def test_revert_last_resort_no_alert_fired(self):
        """Revert: no call → no alert → counters are zero."""
        da = DegradeAlert()
        self.assertEqual(da.counters.get("last_resort", 0), 0)
        self.assertEqual(da.counters.get("prepaid_zero", 0), 0)
        self.assertEqual(da.counters.get("pool_too_thin", 0), 0)

    def test_prepaid_zero_transition_emits_alert(self):
        """Simulate a prepaid-leg-zero transition: alert fires."""
        da = DegradeAlert()
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_prepaid_zero(
                provider="openrouter", model="gpt-4o",
                spill_to="deepseek")
        self.assertEqual(len(cm.output), 1)
        self.assertIn("PREPAID-LEG-ZERO", cm.output[0])
        self.assertIn("openrouter", cm.output[0])
        self.assertIn("spilled to deepseek", cm.output[0])
        self.assertEqual(da.counters["prepaid_zero"], 1)

    def test_revert_prepaid_zero_no_alert_fired(self):
        """Revert: no call → prepaid_zero counter is zero."""
        da = DegradeAlert()
        self.assertEqual(da.counters.get("prepaid_zero", 0), 0)

    def test_pool_too_thin_transition_emits_alert(self):
        """Simulate a pool-too-thin transition: alert fires."""
        da = DegradeAlert()
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_pool_too_thin(
                model="gpt-4", total=4,
                reason="all providers exhausted")
        self.assertEqual(len(cm.output), 1)
        self.assertIn("POOL-TOO-THIN", cm.output[0])
        self.assertIn("gpt-4", cm.output[0])
        self.assertIn("all providers exhausted", cm.output[0])
        self.assertEqual(da.counters["pool_too_thin"], 1)

    def test_revert_pool_too_thin_no_alert_fired(self):
        """Revert: no call → pool_too_thin counter is zero."""
        da = DegradeAlert()
        self.assertEqual(da.counters.get("pool_too_thin", 0), 0)


class TestBalanceTrackerIntegration(unittest.TestCase):
    """DegradeAlert reads the live funding_class from BalanceTracker."""

    def test_prepaid_zero_reads_funding_class_from_live_tracker(self):
        bt = BalanceTracker(config={
            "openrouter": {
                "mode": "fixed",
                "starting_usd": 10.0,
                "funding_class": 3,
            }
        })
        da = DegradeAlert(balance_tracker=bt)
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_prepaid_zero(
                provider="openrouter", model="gpt-4o",
                spill_to="deepseek")
        self.assertIn("fc=3", cm.output[0])

    def test_prepaid_zero_unknown_fc_when_no_tracker(self):
        da = DegradeAlert()  # no balance tracker
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_prepaid_zero(provider="openrouter")
        self.assertIn("fc=?", cm.output[0])

    def test_prepaid_zero_unknown_fc_when_provider_not_configured(self):
        bt = BalanceTracker()
        da = DegradeAlert(balance_tracker=bt)
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_prepaid_zero(provider="nonexistent")
        self.assertIn("fc=?", cm.output[0])


class TestNonBlockingGuarantee(unittest.TestCase):
    """Alerts must never change routing or billing — log-only, no exception
    propagation."""

    def test_alert_never_raises(self):
        da = DegradeAlert()
        da.alert_last_resort(provider="p", model="m", failover_count=1)
        da.alert_prepaid_zero(provider="p")
        da.alert_pool_too_thin(model="m")

    def test_alert_with_empty_strings_does_not_raise(self):
        da = DegradeAlert()
        da.alert_last_resort(provider="", model="", failover_count=0)
        da.alert_prepaid_zero(provider="", model="", spill_to="")
        da.alert_pool_too_thin(model="", total=0, reason="")

    def test_counter_is_idempotent_snapshot(self):
        da = DegradeAlert()
        c1 = da.counters
        c2 = da.counters
        self.assertIsNot(c1, c2)  # each call returns a new dict
        self.assertEqual(c1, c2)


class TestLoggerIsolation(unittest.TestCase):
    """Alerts use the charon.degrade_alert logger — isolated from other
    charon loggers."""

    def test_logger_name_is_dedicated(self):
        da = DegradeAlert()
        with self.assertLogs("charon.degrade_alert", level="WARNING") as cm:
            da.alert_last_resort(provider="p", model="m", failover_count=1)
        self.assertTrue(cm.output[0].startswith("WARNING:charon.degrade_alert"))

    def test_other_loggers_do_not_capture_alert(self):
        da = DegradeAlert()
        # Capture only a different logger; the alert goes to
        # charon.degrade_alert and should NOT appear here.
        with self.assertRaises(AssertionError):
            with self.assertLogs("charon.forwarder", level="WARNING"):
                da.alert_last_resort(provider="p", model="m", failover_count=1)
